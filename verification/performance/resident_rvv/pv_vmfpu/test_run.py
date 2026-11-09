import unittest
from pathlib import Path
import importlib.util
import hashlib
import json
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('pv_vmfpu_run', HERE/'run.py')
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


class RunnerTest(unittest.TestCase):
    def test_bench_only_changes_arithmetic_endpoint(self):
        original = (HERE.parent/'pv_unit/tb.sv').read_text()
        adapted = run.adapt_bench(original)
        restored = adapted.replace('resident_vmfpu_adapter #(\n', 'fpnew_opgroup_fmt_slice #(\n')
        restored = restored.replace('.borrow_busy_i(busy), ', '')
        restored = restored.replace('borrowed_fpu.finish_gate();\n    $finish;', '$finish;')
        restored = restored.replace('task automatic reset_all;\n',
                                    'task automatic reset_all;\n    @(negedge clk);\n')
        self.assertEqual(original, restored)

    def test_adapter_rejects_duplicate_or_unknown_bench(self):
        original = (HERE.parent/'pv_unit/tb.sv').read_text()
        for wrong in (original*2, original.replace('fpnew_opgroup_fmt_slice', 'other')):
            with self.assertRaises(ValueError):
                run.adapt_bench(wrong)

    def test_list_exact_replacement(self):
        source = '/frozen/hardware/src/lane/vmfpu.sv'
        result = run.filelist('+define+X\n'+source+'\n', Path('/candidate.sv'), {source: 'abc'})
        self.assertEqual(result, '+define+X\n/candidate.sv\n')

    def test_only_soc_testbench_excluded(self):
        rtl = '/frozen/hardware/src/lane/vmfpu.sv'
        tb = '/frozen/hardware/tb/ara_tb.sv'
        dep = '/frozen/hardware/deps/fpnew/src/fpnew_top.sv'
        result = run.filelist('\n'.join([rtl, tb, dep]), Path('/candidate.sv'),
                              {p: 'abc' for p in (rtl, tb, dep)})
        self.assertEqual(result, '/candidate.sv\n'+dep+'\n')

    def test_list_rejects_unpinned_and_duplicates(self):
        source = '/frozen/hardware/src/lane/vmfpu.sv'
        for text, pins in [(source+'\n', {}), ((source+'\n')*2, {source: 'abc'}),
                           ('-f /other\n', {})]:
            with self.assertRaises(ValueError):
                run.filelist(text, Path('/candidate.sv'), pins)

    def test_missing_coverage_is_not_pass(self):
        good = ('VMFPU_OWNER_COVERAGE native_done=4 acquires=2 releases=1 native_stalls=3 private_stalls=4 '
                'acquire_collisions=1 miter_cycles=10 native_grant_stalls=3 native_flag_events=1 '
                'reset_owned=1 native_fma=1 native_mul=1 native_div=1 native_max=1 '
                'native_accepted=5 native_cancelled=1 private_issued=2 private_returned=1 private_cancelled=1\n')
        self.assertEqual(run.check_owner(good)['acquires'], 2)
        for text in ('', good*2, good.replace('private_stalls=4', 'private_stalls=0'),
                     good.replace('native_accepted=5', 'native_accepted=6')):
            with self.assertRaises(ValueError):
                run.check_owner(text)

    def test_baseline_only_changes_module_name(self):
        text = 'module vmfpu import ara_pkg::*;\nendmodule : vmfpu\n'
        self.assertEqual(run.baseline_module(text).replace('vmfpu_baseline', 'vmfpu'), text)
        with self.assertRaises(ValueError):
            run.baseline_module(text*2)
        with self.assertRaises(ValueError):
            run.baseline_module(text.replace('endmodule : vmfpu', 'endmodule'))

    def test_historical_helper_recovered_without_waiving_rtl(self):
        content = b'original helper\n'
        expected = hashlib.sha256(content).hexdigest()
        source = str(run.ROOT/'verification/performance/chain_profile/build_soc.py')
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base/'build.json').write_text(json.dumps({'revision': 'f'*40}))
            reports = {}
            helper = SimpleNamespace(sha=lambda name: 'changed',
                                     save=lambda path, value: reports.update({path.name: value}))
            with patch.object(run, 'BASE', base), patch.object(run.subprocess, 'check_output', return_value=content):
                pins = run.baseline_pins(helper, {source: expected}, base, base)
            self.assertEqual(pins[str(base/'historical_build_soc.py')], expected)
            self.assertEqual(pins[source], 'changed')
            self.assertFalse(reports['historical-provenance.json']['original_manifest_matches_current_paths'])
            with patch.object(run, 'BASE', base):
                with self.assertRaisesRegex(ValueError, 'Frozen source/dependency drift'):
                    run.baseline_pins(helper, {'/source/rtl.sv': expected}, base, base)

    def test_wrong_historical_content_is_rejected(self):
        source = str(run.ROOT/'verification/performance/chain_profile/build_soc.py')
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base/'build.json').write_text(json.dumps({'revision': 'f'*40}))
            helper = SimpleNamespace(sha=lambda name: 'changed')
            with patch.object(run, 'BASE', base), patch.object(run.subprocess, 'check_output', return_value=b'wrong'):
                with self.assertRaisesRegex(ValueError, 'Cannot reconstruct'):
                    run.baseline_pins(helper, {source: 'a'*64}, base, base)

    def test_changed_filelist_cannot_be_repinned(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'sources.f'
            source.write_text('+define+ORIGINAL\n')
            helper = SimpleNamespace(sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest())
            pins = {str(source): helper.sha(source)}
            source.write_text('+define+CHANGED\n')
            with self.assertRaisesRegex(ValueError, 'Input changed before snapshot'):
                run.copy_pinned(helper, source, Path(directory)/'copy.f', pins, {})

    def test_accepted_copy_keeps_expected_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'tb.sv'
            source.write_text('accepted bench\n')
            helper = SimpleNamespace(sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest())
            accepted = {str(source): helper.sha(source)}
            pins = {}
            run.copy_pinned(helper, source, Path(directory)/'copy.sv', pins, accepted)
            self.assertEqual(pins, accepted)
            with self.assertRaisesRegex(ValueError, 'Conflicting existing'):
                run.copy_pinned(helper, source, Path(directory)/'copy.sv', {str(source): 'wrong'}, accepted)


if __name__ == '__main__':
    unittest.main()
