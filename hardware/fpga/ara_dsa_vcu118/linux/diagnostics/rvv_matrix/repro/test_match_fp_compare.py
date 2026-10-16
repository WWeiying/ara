import unittest
from match_fp_compare import compare


class ComparisonTests(unittest.TestCase):
    detail = ('RVV_FP_COMPARE_DETAIL op=0 seed=0 vl=4 mask=0 sticky=0 '
              'vstart=1 expected_flags=0 actual_flags=16 errors=1')

    def result(self, detail=None):
        return dict(status='failed', exit_code=1, output=detail or self.detail)

    def test_same_flag_symptom(self):
        result = compare(self.result(), self.result(), self.detail)
        self.assertTrue(result['confirmed'])
        self.assertFalse(result['internal_rtl_root_cause_proven'])
        self.assertFalse(result['vector_data_equivalence_proven'])

    def test_count_not_used_as_proof(self):
        self.assertTrue(compare(self.result(), self.result(self.detail.replace('errors=1','errors=4')),
                                self.detail)['confirmed'])
        line = self.detail.replace('actual_flags=16', 'actual_flags=0')
        self.assertFalse(compare(self.result(line), self.result(line), line)['confirmed'])

    def test_wrong_flags_or_trigger(self):
        for old, new in [('actual_flags=16','actual_flags=17'), ('vl=4','vl=8'),
                         ('vstart=1','vstart=0'), ('vstart=1 ',''),
                         ('expected_flags=0','expected_flags=1')]:
            self.assertFalse(compare(self.result(), self.result(self.detail.replace(old,new)),
                                     self.detail)['confirmed'])

    def test_crash_missing_or_duplicate_detail(self):
        for result in [dict(self.result(), exit_code=139), self.result('FAIL errors=1'),
                       self.result(self.detail+'\n'+self.detail),
                       self.result(self.detail+' actual_flags=16')]:
            self.assertFalse(compare(self.result(), result, self.detail)['confirmed'])


if __name__ == '__main__':
    unittest.main()
