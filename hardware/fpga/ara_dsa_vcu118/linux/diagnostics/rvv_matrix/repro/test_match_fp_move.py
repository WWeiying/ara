import unittest
from match_fp_move import compare


class SymptomTests(unittest.TestCase):
    detail = 'RVV_FP_MOVE_DETAIL op=4 seed=0 scalar=0 invalid_box=0 vl=2 mask=0 sticky=0 vstart=1 actual_flags=0 errors=1'
    classification = ('RVV_FP_MOVE_CLASSIFY returned_vstart=0 first_bad_element=0 '
        'expected_bits=91 actual_bits=0 scalar_expected=7 scalar_actual=7 guard_before=91 guard_after=91')

    def result(self, classification=True):
        return dict(status='failed', exit_code=1,
                    output=self.detail+'\n'+(self.classification+'\n' if classification else ''))

    def test_explicit_matching_data(self):
        self.assertTrue(compare(self.result(False), self.result(), self.result(), self.detail)['confirmed'])

    def test_error_count_alone_is_insufficient(self):
        self.assertFalse(compare(self.result(False), self.result(False), self.result(), self.detail)['confirmed'])

    def test_different_value_not_equivalent(self):
        reduced = self.result()
        reduced['output'] = reduced['output'].replace('actual_bits=0', 'actual_bits=1')
        self.assertFalse(compare(self.result(False), self.result(), reduced, self.detail)['confirmed'])

    def test_crash_is_not_same_numerical_failure(self):
        reduced = dict(self.result(), exit_code=139)
        self.assertFalse(compare(self.result(False), self.result(), reduced, self.detail)['confirmed'])


if __name__ == '__main__':
    unittest.main()
