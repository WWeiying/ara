"""Tool-free regression of synthesis preparation guards (never invokes DC)."""
import copy
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('flow', HERE / 'flow.py')
flow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flow)


class PreparationTests(unittest.TestCase):
    def defines(self, profile='full'):
        return dict(flow.PROFILES[profile], NR_LANES='4', VLEN='1024',
                    ARIANE_ACCELERATOR_PORT='1', SYNTHESIS=None,
                    TARGET_SYNTHESIS=None, TARGET_SRAM_MC=None, HPDCACHE_ASSERT_OFF=None)

    def test_dc_portability_semantics(self):
        # Every register index and supported integer group alignment.
        for reg in range(32):
            for bits in (1, 2, 3):
                self.assertEqual(any((reg >> i) & 1 for i in range(bits)),
                                 (reg & ((1 << bits) - 1)) != 0)
        # Each possible single missing boxing bit, all ones/zeros, every format.
        for flen in (32, 64):
            values = [0, (1 << flen) - 1]
            values += [((1 << flen) - 1) ^ (1 << i) for i in range(flen)]
            for width in (8, 16, 32, 64):
                for value in values:
                    old = all((value >> i) & 1 for i in range(width, flen))
                    new = all(i < width or ((value >> i) & 1) for i in range(flen))
                    self.assertEqual(old, new)
        with self.assertRaises(ValueError):
            flow.repair_unboxed_loop('unexpected implementation')

    def test_profiles(self):
        for name in flow.PROFILES:
            flow.validate_defines(self.defines(name), name)
        self.assertNotIn('ARA_RED_RCE_INT', flow.PROFILES['baseline'])
        for name in flow.PROFILES:
            if name == 'original_30c6971b':
                self.assertEqual(flow.PROFILES[name], {})
                continue
            self.assertEqual(flow.PROFILES[name]['ARA_RED_RCE_SLDU_BUFFER'], '1')
            self.assertEqual(flow.PROFILES[name]['ARA_RED_RCE_ALU_RESULT_DEPTH'], '4')
            self.assertEqual(flow.PROFILES[name]['ARA_RED_RCE_FP_RESULT_DEPTH'], '4')

    def test_original_csr_overlay(self):
        original = '      fflags_valid  : |fflags_ex_valid_i,\n      default : \'0\n'
        result = flow.original_csr_overlay(original)
        self.assertIn('fp_csr_busy   : !ara_idle_i || ara_req_valid_o || acc_req_i.req_valid ||', result)
        self.assertIn('state_q != NORMAL_OPERATION', result)
        with self.assertRaises(ValueError):
            flow.original_csr_overlay(result)
        with self.assertRaises(ValueError):
            flow.original_csr_overlay('unknown')

    def test_disabled_ifdef_must_be_absent(self):
        d = self.defines('baseline')
        d['ARA_RED_RCE_INT'] = '0'
        with self.assertRaises(ValueError):
            flow.validate_defines(d, 'baseline')

    def test_shared_ordered_dependencies(self):
        for field, value in [('ARA_RED_SHARED_ORDERED_UNITS', '3'),
                             ('ARA_RED_ORDERED_SCALAR_ADD', None),
                             ('ARA_RED_ORDERED_OUTPUT_REG', None)]:
            d = self.defines('full_area_shared1')
            if value is None:
                del d[field]
            else:
                d[field] = value
            candidate = {k: v for k, v in d.items() if k.startswith('ARA_RED_')}
            with patch.dict(flow.PROFILES, {'invalid_candidate': candidate}):
                with self.assertRaises(ValueError):
                    flow.validate_defines(d, 'invalid_candidate')

    def test_shared_forward_requires_chain(self):
        d = self.defines('full_area_local')
        del d['ARA_RED_CHAIN_BYPASS_4LANE']
        candidate = {k: v for k, v in d.items() if k.startswith('ARA_RED_')}
        with patch.dict(flow.PROFILES, {'invalid_candidate': candidate}):
            with self.assertRaises(ValueError):
                flow.validate_defines(d, 'invalid_candidate')

    def test_reject_simulation_or_geometry(self):
        for k, v in [('IDEAL_DISPATCHER', '1'), ('TARGET_NOTSYNTHESIS', None),
                     ('VLEN', '2048'), ('ARA_QBS_ENABLE', '1')]:
            d = self.defines(); d[k] = v
            with self.assertRaises(ValueError):
                flow.validate_defines(d, 'full')

    def test_macro_mode_required(self):
        d = self.defines(); del d['TARGET_SRAM_MC']
        with self.assertRaises(ValueError):
            flow.validate_defines(d, 'full')

    def test_source_order_and_dedup(self):
        d, inc, src = flow.entries('+define+A=1\n+define+A=1\n/inc/math_pkg.sv\n/inc/mod.sv\n/inc/mod.sv\n')
        self.assertEqual(d, {'A': '1'})
        self.assertEqual([p.name for p in src], ['math_pkg.sv', 'mod.sv'])
        self.assertEqual(flow.entries(flow.render(d, inc, src)), (d, inc, src))

    def test_reject_conflicting_macros(self):
        with self.assertRaises(ValueError):
            flow.entries('+define+VLEN=1024\n+define+VLEN=2048\n')

    def test_reject_nested_filelists(self):
        with self.assertRaises(ValueError):
            flow.entries('-f /old/build.f\n')

    def test_report_rejects_prepared_without_eda(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            flow.write_json(out / 'status.json', {'state': 'PREPARED'})
            with patch.object(flow, 'check', return_value={}), self.assertRaises(ValueError):
                flow.report(out)

    def test_run_rejects_reuse_before_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); (out / 'console.log').write_text('old attempt')
            with patch.object(flow, 'check', return_value={}), patch.object(flow.subprocess, 'run') as runner:
                with self.assertRaises(ValueError):
                    flow.run(out)
                runner.assert_not_called()

    def test_tcl_and_shell_syntax(self):
        # info complete parses braces/quotes only; it never evaluates DC commands.
        for p in (HERE / 'templates').iterdir():
            if p.name == 'run.cmd':
                subprocess.run(['bash', '-n', str(p)], check=True)
            else:
                program = 'set f [open {' + str(p) + '}]; set s [read $f]; close $f\nif {![info complete $s]} {exit 1}\n'
                subprocess.run(['tclsh'], input=program, text=True, check=True)


if __name__ == '__main__':
    unittest.main()
