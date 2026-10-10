import copy
import unittest
import admit_qbs_min_slot15_761 as a


class Native761(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qual = a.life.read_bound(a.QUAL/'qualification.json',a.QUAL_SHA)

    def test_actual_scope(self): a.contract(self.qual)

    def test_missing_gold_false_isa_wrong_stage_rejected(self):
        for key,value in [('stage','aux'),('baseline',746),('checks',True),('CSR_values',23),
                          ('full_scalar_ISA_verified',True),('uvm_check_report_pass',True)]:
            altered = copy.deepcopy(self.qual); altered[key]=value
            with self.assertRaises(ValueError): a.contract(altered)

    def test_wrong_target_rejected(self):
        altered = copy.deepcopy(self.qual); altered['targets'][0]['index']=279
        with self.assertRaises(ValueError): a.contract(altered)

    def test_wrong_gain_rejected(self):
        altered = copy.deepcopy(self.qual); altered['raw_delta']['fsm']=14
        with self.assertRaises(ValueError): a.contract(altered)

    def test_actual_full8_native_bytes_and_labels(self):
        audits = a.life.read_bound(a.QUAL/'epoch-audits.json',self.qual['output_pins'][str(a.QUAL/'epoch-audits.json')])
        normalized = a.normalized_bindings(audits[1])
        self.assertEqual(normalized['native_active_bytes'],512)
        self.assertEqual([b['backend_vl'] for b in normalized['bindings']],[256,256])
        self.assertEqual([b['backend_vl'] for b in audits[1]['bindings']],[160,160])


if __name__ == '__main__': unittest.main()
