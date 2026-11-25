import copy
import json
import unittest
import akv_basic_recovery_v1 as m


class BasicPolicyTests(unittest.TestCase):
    def setUp(self):
        self.a=json.loads((m.CAPTURE/'activity-audit.json').read_text())

    def test_actual_memory_path_admitted(self):
        self.assertEqual(m.basic_activity(self.a)['cycles'],41411)

    def test_critical_x_not_waived(self):
        self.a['signals']['dispatcher']['unknown_ticks']=1
        with self.assertRaises(ValueError):m.basic_activity(self.a)

    def test_active_payload_not_waived(self):
        self.a['active_payload_unknown_samples']=1
        with self.assertRaises(ValueError):m.basic_activity(self.a)

    def test_other_rejection_not_waived(self):
        self.a['reasons'].append('Critical control X/Z time: clock')
        with self.assertRaises(ValueError):m.basic_activity(self.a)

    def test_no_target_not_waived(self):
        self.a['signals']['pc']['values']={}
        with self.assertRaises(ValueError):m.basic_activity(self.a)


if __name__=='__main__':unittest.main()
