import unittest
from pathlib import Path
from reduce_fpwide import reduce


class ReductionTests(unittest.TestCase):
    def test_preserves_body_and_oracle(self):
        source = (Path(__file__).parents[1]/'reduction_oracle.c').read_text()
        small = reduce(source)
        marker = '            unsigned vl=lengths[l];'
        self.assertEqual(source[source.index(marker):], small[small.index(marker):])
        self.assertIn('unsigned lengths[]={0};', small)
        self.assertIn('for(unsigned op=0;op<1;++op)', small)
        self.assertIn('seed<1', small)
        with self.assertRaises(ValueError):
            reduce(source.replace('mode<4', 'mode<3'))


if __name__ == '__main__':
    unittest.main()
