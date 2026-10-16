import unittest
from pathlib import Path
from reduce_gather import reduce


class GatherTests(unittest.TestCase):
    def test_only_selector_added(self):
        source=(Path(__file__).parents[1]/'permutation_oracle.c').read_text()
        for op in (0,1,2,3,20):
            selector=f'            if(!(seed==0 && op=={op} && s==0 && l==2 && mode==0 && trial==0))continue;\n'
            self.assertEqual(reduce(source,op).replace(selector,''),source)

    def test_source_drift_rejected(self):
        with self.assertRaises(ValueError):reduce('missing',0)


if __name__=='__main__':unittest.main()
