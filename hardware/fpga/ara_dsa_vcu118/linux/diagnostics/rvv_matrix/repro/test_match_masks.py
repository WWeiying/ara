import unittest
from match_masks import compare


class MatchTests(unittest.TestCase):
    def record(self):
        return dict(status='failed', exit_code=1, output=(
            'RVV_MASK_BIT seed=0 op=0 vl=8 mask=0 vstart=4 element=2 active=0 old=0 expected=0 actual=1\n'
            'RVV_MASK_FIRST seed=0 op=0 vl=8 mask=0 vstart=4 returned_vstart=0 errors=1 guard_before=91 guard_after=91\n'))

    def test_exact_symptom(self):
        self.assertTrue(compare(self.record(), self.record())['confirmed'])

    def test_different_element_or_guard_not_equivalent(self):
        r = self.record()
        for old, new in [('element=2','element=3'), ('guard_after=91','guard_after=0'),
                         ('returned_vstart=0','returned_vstart=4'), ('errors=1','errors=2')]:
            self.assertFalse(compare(r, dict(r, output=r['output'].replace(old, new)))['confirmed'])

    def test_incomplete_or_ambiguous_rejected(self):
        r = self.record()
        for output in [r['output'].replace(' guard_after=91',''), r['output']*2]:
            with self.assertRaises(ValueError):
                compare(r, dict(r, output=output))


if __name__ == '__main__':
    unittest.main()
