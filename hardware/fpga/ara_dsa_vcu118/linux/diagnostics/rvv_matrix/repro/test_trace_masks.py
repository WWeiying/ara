import unittest
from trace_masks import instrument, TOOLS


class MaskTraceTests(unittest.TestCase):
    def test_preserves_original_loop_order_and_target_arguments(self):
        source=(TOOLS/'mask_oracle.c').read_text()
        changed=instrument(source)
        for line in source.splitlines():
            if 'for(' in line:
                self.assertIn(line,changed)
        call='functions[raw_op](a,b,output+1,vl,cap,predicate,start)'
        self.assertEqual(changed.count(call),1)
        self.assertIn('RVV_MASK_BIT seed=',changed)
        self.assertIn('if(errors) {',changed)
        self.assertIn('goto probe_done;',changed)
        self.assertLess(changed.index(call),changed.index('RVV_MASK_BIT seed='))
        start=source.index('                unsigned active=')
        end=source.index('                } else if(op==18 || op==19)')
        self.assertIn(source[start:end],changed)


if __name__=='__main__':unittest.main()
