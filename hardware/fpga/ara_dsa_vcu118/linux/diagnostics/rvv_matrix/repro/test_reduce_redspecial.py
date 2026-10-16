import unittest
from pathlib import Path
from reduce_redspecial import reduce, SELECTOR


class ReductionTests(unittest.TestCase):
    def test_original_fixture_indexing_preserved(self):
        source=(Path(__file__).parents[1]/'fp_reduction_oracle.c').read_text()
        changed=reduce(source)
        self.assertEqual(changed.replace(SELECTOR,''),source)
        self.assertLess(changed.index('index++'),changed.index(SELECTOR))
        self.assertLess(changed.index('for(unsigned sticky='),changed.index(SELECTOR))

    def test_drift_rejected(self):
        with self.assertRaises(ValueError):reduce('missing')


if __name__=='__main__':unittest.main()
