import unittest
from pathlib import Path
import prepare_fpu_reset_matrix as m


class Matrix(unittest.TestCase):
    def fixture(self,sew):
        v={('g75_result',0):679,('g75_result',4):0,('num_failed',0):0,('tohost',0):1}
        for i in range(512):v['fpar_vrf',8*i]=0x123456789abcdef0 if i<128 else m.GOLD[sew][i//128-1]
        for i,x in enumerate((8192//sew,{16:11,32:19,64:27}[sew],0,0,33)):v['fpar_csr',8*i]=x
        return v
    def test_three_complete(self):
        for sew in m.GOLD:
            v=self.fixture(sew);m.oracle(lambda n,o=0,size=8:v.get((n,o)),sew)
    def test_corrupt_full_vrf(self):
        for sew in m.GOLD:
            v=self.fixture(sew);v['fpar_vrf',511*8]^=1
            with self.assertRaises(ValueError):m.oracle(lambda n,o=0,size=8:v.get((n,o)),sew)
    def test_wrong_rounding(self):
        v=self.fixture(64);v['fpar_csr',32]=32
        with self.assertRaises(ValueError):m.oracle(lambda n,o=0,size=8:v.get((n,o)),64)
    def test_independent_dyadic_rounding(self):
        for sew,mant,bias in ((16,10,15),(32,23,127),(64,52,1023)):
            raw=((bias-2)<<mant)|((1<<(mant+2))//3-(1<<mant))
            packed=sum(raw<<(i*sew) for i in range(64//sew))
            self.assertEqual(packed,m.GOLD[sew][2])
    def test_precise_stage_codes(self):
        self.assertEqual(m.STAGES,{'RF':(4,12),'EX1':(5,7),'EX2':(6,8),'WB_REQ':(7,15)})
    def test_no_run_entry(self):
        text=Path(m.__file__).read_text()
        self.assertNotIn('life.run(',text)
        self.assertNotIn('force ',text)


if __name__=='__main__':unittest.main()
