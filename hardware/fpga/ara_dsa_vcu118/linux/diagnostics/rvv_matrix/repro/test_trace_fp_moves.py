import unittest
import copy
from trace_fp_moves import instrument, measured_trial, shape_capacity, TOOLS
from reduce_fp_moves import single_trial


class TraceMovesTests(unittest.TestCase):
    def test_legal_shape_capacity(self):
        self.assertEqual(shape_capacity('e32_m2'), 64)
        self.assertEqual(shape_capacity('e16_mf2'), 32)
        self.assertEqual(shape_capacity('e64_m8'), 128)
        for shape in ('e32_mf8', 'e8_m1', 'e16_m3', 'e64_mf2'):
            with self.assertRaises(ValueError):shape_capacity(shape)

    def test_preserves_call_and_oracle(self):
        source = (TOOLS / 'fp_move_oracle.c').read_text()
        traced = instrument(source)
        call = 'unsigned long status=functions[op](a,&scalar_bits,output+1,vl,cap,mask,control,&scalar_result);'
        self.assertEqual(traced.count(call), 1)
        self.assertLess(traced.index('RVV_MOVE_BEGIN'), traced.index(call))
        self.assertGreater(traced.index('RVV_MOVE_RETURN'), traced.index(call))
        start = '        if((uint32_t)status || (status>>32)!=sticky)++errors;'
        self.assertEqual(source[source.index(start):], traced[traced.index(start):])
        self.assertIn('if(syscall3(29,1,0x5409,1))', traced)
        self.assertEqual(traced.count('seed==0 && scalar==0 && invalid==0 && op==2'), 2)

    def test_rejects_changed_call(self):
        with self.assertRaises(ValueError):
            instrument('unknown source')

    def test_measured_trial_requires_stall_identity(self):
        name = 'rvv_trace_fp_move_restart_e16_mf2'
        case = dict(name=name, sha256='elf')
        a = dict(identity=dict(frequency_hz=50), live=dict(run_id=1, flags=0),
                 watchdog_snapshot=False, core=dict(cycles=100, retired=1, trap_count=0, last_pc=4, head_pc=8))
        b = copy.deepcopy(a); b['core']['cycles'] = 300
        report = dict(inputs=dict(cases=[case]), results=[dict(name=name, status='stalled',
            output='RVV_MOVE_BEGIN seed=0 scalar=0 invalid_box=0 op=2 vl=32 mask=0 sticky=0 vstart=16 cap=32 completed=642')],
            progress_diagnosis=dict(name=name, stalled=True, snapshots=[a, b]))
        fields = measured_trial(report, dict(cases=[case]))
        self.assertEqual(fields['vstart'], 16)
        report32 = copy.deepcopy(report)
        name32 = 'rvv_trace_fp_move_restart_e32_m1'
        report32['inputs']['cases'][0]['name'] = name32
        report32['results'][0]['name'] = name32
        report32['progress_diagnosis']['name'] = name32
        manifest32 = dict(cases=[dict(name=name32, sha256='elf')])
        self.assertEqual(measured_trial(report32, manifest32, 'e32_m1'), fields)
        with self.assertRaises(ValueError):
            measured_trial(report32, manifest32, 'e32_mf8')
        code = instrument(single_trial((TOOLS / 'fp_move_oracle.c').read_text(), fields))
        self.assertIn('unsigned vl=32;', code)
        self.assertIn('unsigned start=16;', code)
        report['results'][0]['status'] = 'running'
        with self.assertRaises(ValueError):
            measured_trial(report, dict(cases=[case]))
        report['results'][0]['status'] = 'stalled'
        b['live']['run_id'] = 2
        with self.assertRaises(ValueError):
            measured_trial(report, dict(cases=[case]))


if __name__ == '__main__':
    unittest.main()
