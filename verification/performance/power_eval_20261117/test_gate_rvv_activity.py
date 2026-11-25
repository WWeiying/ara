import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('rvv_gate_test',HERE/'gate_rvv_activity.py')
w=importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


class GateActivityTests(unittest.TestCase):
    def test_complete_windows_are_bounded(self):
        for first,last in ((36725,41017),(216301,224798),(59758,81142)):
            w.validate_window(first,last)
        for first,last in ((0,10),(3,2),(1,40000),(2,3)):
            with self.assertRaises(ValueError):w.validate_window(first,last)

    def test_unknown_dispatcher_blocks_admission_not_physical_count(self):
        rows={1:(0,['python3','/x/inputs/precheck_unknown.py','execute','--output','/x']),
              2:(1,['/rtl/simv']),3:(0,['/gate/simv'])}
        snap=w.capacity(rows,own=3)
        self.assertFalse(snap['launch_allowed'])
        self.assertEqual(snap['actual_other_simv'],[2])
        rows={i:(0,['/image/simv']) for i in range(1,5)}
        self.assertFalse(w.capacity(rows)['launch_allowed'])

    def test_common_all_on_identity_never_rewritten(self):
        self.assertEqual(w.g.GATE.name,'power_gate_build_20261117_all_on_01')
        self.assertEqual(w.GATE.name,'power_gate_build_20261117_baseline_02')
        self.assertEqual(w.g.MAX_SLOTS,4)

    def test_native_eof_is_complete_without_fabricated_dumpoff(self):
        vcd='''$timescale 1ps $end
$scope module ara_tb $end
$scope module dut $end
$scope module i_ara_soc $end
$var wire 1 ! clk_i $end
$upscope $end
$upscope $end
$upscope $end
$enddefinitions $end
#100000
$dumpvars
0!
$end
#100500
1!
#101000
0!
#101500
1!
#102000
0!
'''
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'wave.vcd'
            path.write_text(vcd)
            result=w.eof.inspect_vcd(path,100000,102000,2)
            self.assertTrue(result['eof_at_selected_end'])
            self.assertFalse(result['textual_dumpoff_present'])
            self.assertEqual(path.read_text(),vcd)
            path.write_text(vcd.rstrip())
            with self.assertRaises(ValueError):w.eof.inspect_vcd(path,100000,102000,2)

    def test_unauthorized_worker_cannot_execute(self):
        with self.assertRaises(ValueError):w.execute(Path('/tmp/not-frozen'),'',False)


if __name__=='__main__':unittest.main()
