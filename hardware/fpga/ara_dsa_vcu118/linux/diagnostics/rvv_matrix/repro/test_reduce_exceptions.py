import unittest
from pathlib import Path
from reduce_exceptions import reduce


class ReductionTests(unittest.TestCase):
    def test_only_trial_loops_change(self):
        source=(Path(__file__).parents[1]/'exception_oracle.c').read_text()
        for scenario in (0,1,2,3,5):
            changed=reduce(source,scenario)
            marker='        for(unsigned i=0;i<130;++i)'
            self.assertEqual(source[source.index(marker):],changed[changed.index(marker):])
            self.assertIn(f'unsigned scenario={scenario};scenario<{scenario+1}',changed)
        with self.assertRaises(ValueError):
            reduce(source,4)


if __name__ == '__main__':
    unittest.main()
