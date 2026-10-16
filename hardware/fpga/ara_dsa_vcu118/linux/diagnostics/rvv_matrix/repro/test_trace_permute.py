import unittest
from pathlib import Path
from trace_permute import instrument, isolate


class TraceTests(unittest.TestCase):
    def test_isolation_does_not_change_fixture(self):
        source=(Path(__file__).parents[1]/'permutation_oracle.c').read_text()
        selector='            if(!(seed==0 && op==16 && s==0 && l==4 && mode==0 && trial==1))continue;\n'
        self.assertEqual(isolate(source).replace(selector,''),source)
        with self.assertRaises(ValueError):isolate('missing')

    def test_original_preserved(self):
        source=(Path(__file__).parents[1]/'permutation_oracle.c').read_text()
        changed=instrument(source)
        before=changed.index('            text("RVV_PERMUTE_BEGIN')
        target=changed.index('            if(functions[op]')
        after=changed.index('            text("RVV_PERMUTE_RETURN')
        end=changed.index('            for(unsigned i=0;i<cap;++i){',after)
        self.assertEqual(changed[:before]+changed[target:after]+changed[end:],source)
        with self.assertRaises(ValueError):
            instrument('no target')


if __name__=='__main__':
    unittest.main()
