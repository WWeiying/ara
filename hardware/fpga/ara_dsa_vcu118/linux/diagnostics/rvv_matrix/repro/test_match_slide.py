import unittest
from match_slide import compare, details

LINE='RVV_PERMUTE_DETAIL op=12 seed=0 scalar=511 vl=512 mask=0 element=511 expected=185 actual=91'


class MatchTests(unittest.TestCase):
    def test_restart_position_must_match(self):
        line=LINE+' vstart=1'
        result=dict(status='failed',exit_code=1,output=line)
        self.assertTrue(compare(result,result,line)['confirmed'])
        self.assertFalse(compare(result,dict(result,output=LINE),line)['confirmed'])
        self.assertFalse(compare(result,dict(result,output=LINE+' vstart=0'),line)['confirmed'])

    def test_exact_tuple(self):
        result=dict(status='failed',exit_code=1,output=LINE+'\n')
        self.assertTrue(compare(result,result,LINE)['confirmed'])
        for changed in (LINE.replace('actual=91','actual=0'),
                        LINE.replace('scalar=511','scalar=255'),
                        LINE.replace('mask=0','mask=2')):
            self.assertFalse(compare(result,dict(result,output=changed),LINE)['confirmed'])

    def test_pass_or_stall_is_not_same_numerical_failure(self):
        result=dict(status='failed',exit_code=1,output=LINE)
        self.assertFalse(compare(result,dict(result,status='stalled'),LINE)['confirmed'])
        self.assertFalse(compare(result,dict(result,exit_code=0),LINE)['confirmed'])

    def test_partial_or_duplicated_detail_rejected(self):
        for line in ('RVV_PERMUTE_DETAIL op=12',LINE+' actual=91'):
            with self.assertRaises(ValueError):
                details(line)


if __name__=='__main__':
    unittest.main()
