import importlib.util
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('rvv_priority_successor_test',HERE/'gate_rvv_activity_v2.py')
s=importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class PriorityTests(unittest.TestCase):
    def test_q8_gls_and_controller_have_priority_not_dc_followers(self):
        text='''power-dc-20261117-q8-baseline-follow-01.service loaded active running DC
power-gls-20261117-baseline-q8-capture-04.service loaded active running capture
power-gls-20261117-baseline-q8-serial-wait-01.service loaded active running chain
power-gls-20261117-baseline-rvv-activity-02.service loaded active running own
'''
        self.assertEqual(s.filter_q8_gls(text),[
            'power-gls-20261117-baseline-q8-capture-04.service',
            'power-gls-20261117-baseline-q8-serial-wait-01.service'])
        self.assertEqual(s.filter_q8_gls('power-dc-q8.service loaded active running DC\n'),[])

    def test_no_kernel_or_slot_gate_changes(self):
        self.assertEqual(s.b.sha(HERE/'gate_rvv_activity.py'),s.BASE_SHA)
        self.assertEqual(s.b.g.MAX_SLOTS,4)
        self.assertEqual(s.b.g.GATE.name,'power_gate_build_20261117_all_on_01')
        self.assertEqual(s.b.GATE.name,'power_gate_build_20261117_baseline_02')
        s.b.validate_window(59758,81142)


if __name__=='__main__':unittest.main()
