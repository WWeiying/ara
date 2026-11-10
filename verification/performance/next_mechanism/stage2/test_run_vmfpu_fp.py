#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('full_fp_gate', HERE / 'run_vmfpu_fp.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def good_log(**changes):
    row = dict(native=5, writes=5, flags=5, nv=1, grant_stalls=40, native_held=12,
               pv_held=40, pv_acquires=2, pv_releases=2, pv_returns=2, borrowed=24,
               returned=24, red_tokens=1, red_completes=1)
    row.update(changes)
    return 'STAGE2_VMFPU_FP_PASS ' + ' '.join(f'{k}={row[k]}' for k in gate.FIELDS) + '\n'


class FullFpGateTests(unittest.TestCase):
    def test_exact_terminal(self):
        self.assertEqual(gate.check(good_log())['native'], 5)

    def test_missing_duplicate_and_fatal(self):
        for log in ('', good_log()*2, good_log()+'Fatal: failed\n', 'Error-[SE]\n'+good_log()):
            with self.subTest(log=log), self.assertRaises(ValueError):
                gate.check(log)

    def test_counter_mutations(self):
        for key in ('native', 'writes', 'flags', 'nv', 'pv_acquires', 'pv_releases',
                    'pv_returns', 'borrowed', 'returned', 'red_tokens', 'red_completes'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                gate.check(good_log(**{key: 0}))

    def test_held_valid_and_late_grant_required(self):
        for key in ('native_held', 'pv_held', 'grant_stalls'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                gate.check(good_log(**{key: 0}))

    def test_extra_reordered_fields(self):
        for log in (good_log().replace('writes=5', 'writes=5 extra=1'),
                    good_log().replace('native=5 writes=5', 'writes=5 native=5')):
            with self.assertRaises(ValueError):
                gate.check(log)

    def test_dependency_selection_not_live(self):
        frozen = str(gate.FROZEN / 'hardware/deps/fpu_div_sqrt_mvp/hdl/control_mvp.sv')
        live = '/home/wangwy/openproject/ara_dsa/hardware/deps/fpu_div_sqrt_mvp/dirty.sv'
        selected = gate.dependencies(frozen+'\n'+live+'\n'+frozen+'\n')
        self.assertIn('hardware/deps/fpu_div_sqrt_mvp/hdl/control_mvp.sv', selected)
        self.assertFalse(any('dirty.sv' in rel for rel in selected))
        self.assertEqual(len(selected), len(set(selected)))
        self.assertEqual(selected[-1], 'hardware/src/lane/vmfpu.sv')

    def test_missing_divider_rejected(self):
        with self.assertRaises(ValueError):
            gate.dependencies('/live/unaccepted.sv\n')

    def test_pin_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'source'
            path.write_text('first')
            pins = {str(path): gate.sha(path)}
            gate.verify(pins)
            path.write_text('changed')
            with self.assertRaises(ValueError):
                gate.verify(pins)

    def test_arbitration_truth_table(self):
        for native in (False, True):
            for pv in (False, True):
                for qbs in (False, True):
                    native_fire = native
                    pv_fire = pv and not native
                    qbs_fire = qbs and not native and not pv
                    self.assertLessEqual(sum((native_fire, pv_fire, qbs_fire)), 1)
                    self.assertEqual(native_fire or pv_fire or qbs_fire, native or pv or qbs)

    def test_production_arbitration_and_drain_contract(self):
        rtl = (gate.ROOT / 'hardware/src/lane/vmfpu.sv').read_text()
        ready = rtl.split('mfpu_ready_o      =', 1)[1].split(';', 1)[0]
        admission = rtl.split('if (!resident_owned_q && !qbs_mul_owned &&', 1)[1].split('begin', 1)[0]
        self.assertNotIn('qbs_mul_requested', ready + admission)
        pv_ready = rtl.split('assign resident_acquire_ready_o =', 1)[1].split(';', 1)[0]
        self.assertNotIn('qbs_mul_requested', pv_ready)
        self.assertIn('native_drained && vdiv_in_ready', pv_ready)
        drain = rtl.split('assign native_drained =', 1)[1].split(';', 1)[0]
        for token in ('mfpu_state_q == NO_REDUCTION', '!sldu_mfpu_valid_q',
                      '!fpu_red_complete_o', 'native_fp_drained'):
            self.assertIn(token, drain)
        self.assertNotIn('ready', drain)
        fp = rtl.split('assign native_fp_drained =', 1)[1].split(';', 1)[0]
        for token in ('!vfpu_busy', '!bulk_out_valid', '!fflags_ex_valid_d', 'reduction_fflags_q'):
            self.assertIn(token, fp)


if __name__ == '__main__':
    unittest.main()
