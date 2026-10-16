import unittest
from reduce_whole import reduce, TOOLS


class WholeReductionTests(unittest.TestCase):
    def test_original_call_and_byte_oracle_remain_exact(self):
        source=(TOOLS/'whole_oracle.c').read_text()
        first=source.index('            for(unsigned i=0;i<1024;++i)')
        last=source.index('            ++cases;')
        for prefix in (False,True):
            small=reduce(source,prefix)
            self.assertIn(source[first:last],small)
            self.assertEqual(small.count('functions[op]('),1)
        self.assertIn('for(unsigned st=1;st<2;++st)',reduce(source))
        self.assertIn('seed==0 && op==16 && mode==1 && st==1',reduce(source,True))
        self.assertIn('selected_done:',reduce(source,True))


if __name__=='__main__':
    unittest.main()
