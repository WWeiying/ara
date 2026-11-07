from pathlib import Path
import unittest

from mixed_scale_model_census import eligible
from run_mixed_scale_expanded import PARENT, WRAPPER, sources


class ExpandedScale(unittest.TestCase):
    def test_reciprocal_exponent_recoding_exact_domain(self):
        for ea in range(256):
            for ew in range(256):
                for low in (0,1):
                    a=(ea<<23)|0x12345; w=(ew<<23)|0x246000|low
                    recode=103<=ew<=112 and 10<ea<255
                    ar=(a&0x807fffff)|((ea-10)<<23) if recode else a
                    wr=(w&0x807fffff)|((ew+10)<<23) if recode else w
                    self.assertEqual(eligible(ar,wr),eligible(a,w,True))
                    if recode:
                        self.assertEqual(((ar>>23)&255)+((wr>>23)&255),ea+ew)
                        self.assertEqual((ar^a)&0x807fffff,0)
                        self.assertEqual((wr^w)&0x807fffff,0)

    def test_actual_successor_sources_preserve_core(self):
        c=(PARENT/'src/mixed_scale_oracle.c').read_text()
        tb=(PARENT/'src/qbs_mixed_scale_tb.sv').read_text()
        a,b,edits=sources(c,tb)
        self.assertEqual(len(edits),5)
        self.assertIn('qbs_fp16_f32_scale #',b)
        self.assertIn('cases==112071',b)
        self.assertIn('fraction<1024',a)
        self.assertIn('qbs_mixed_scale #',WRAPPER.read_text())
        for wrong_c,wrong_tb in (('',tb),(c+c,tb),(c,''),(c,tb+tb)):
            with self.assertRaises(ValueError):sources(wrong_c,wrong_tb)


if __name__=='__main__':unittest.main()
