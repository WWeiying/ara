import unittest
from classify_fp_compare import classify, parse


class RawComparisonTests(unittest.TestCase):
    case=dict(name='rvv_detail_fp_compare_restart_e16_m1',
              measured_stimulus=dict(vl=8,vstart=4))

    def output(self,byte=91):
        return ('RVV_FP_COMPARE_RAW cap=8 returned_vstart=0 actual_flags=16 guard_before=91 guard_after=91\n'
                f'RVV_FP_COMPARE_BYTE index=0 actual={byte}\n')

    def classify(self,byte,case=None):
        return classify(case or self.case,
            dict(status='failed',exit_code=1,output=self.output(byte)),
            dict(passed=True,exit_code=0,output=self.output()))

    def test_prestart_bit_error_is_explicit(self):
        result=self.classify(90)
        self.assertEqual(result['prestart_mismatches'],[dict(element=0,expected=1,actual=0)])
        self.assertFalse(result['original_failure_equivalence_proven'])

    def test_active_or_tail_bits_not_used_as_prestart_evidence(self):
        self.assertEqual(self.classify(91^128)['prestart_mismatches'],[])

    def test_start_at_vl_preserves_entire_destination(self):
        case=dict(self.case,measured_stimulus=dict(vl=4,vstart=4))
        self.assertEqual(self.classify(91^128,case)['prestart_mismatches'],
                         [dict(element=7,expected=0,actual=1)])

    def test_alias_or_incomplete_output_rejected(self):
        with self.assertRaises(ValueError):
            self.classify(90,dict(self.case,name='rvv_detail_fp_compare_alias_v0_e16_m1'))
        for output in (self.output().splitlines()[0],self.output()+'RVV_FP_COMPARE_BYTE index=0 actual=91\n'):
            with self.assertRaises(ValueError):parse(output)


if __name__=='__main__':
    unittest.main()
