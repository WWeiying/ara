import unittest
import prepare_half_fma_finite as m


class FiniteGold(unittest.TestCase):
    def test_exact_fused_cancellation(self):
        for rm in (0,1):
            self.assertEqual(m.fused(0x3c01,0x3bfe,0xbc00,rm),(0x8010,0))
            self.assertEqual(m.fused(0xbc01,0x3bfe,0x3c00,rm),(0x0010,0))

    def test_tie_single_round_flags(self):
        self.assertEqual(m.fused(0x3c00,0x3c00,0x1000,0),(0x3c00,1))
        self.assertEqual(m.fused(0x3c00,0x3c00,0x1000,1),(0x3c00,1))

    def test_exact_dyadics(self):
        self.assertEqual(m.fused(0x3e00,0x4000,0xbc00,0),(0x4000,0))

    def test_unsupported_input_and_rounding_rejected(self):
        for args in ((0x7c00,0,0,0),(0,0,0,2)):
            with self.assertRaises(ValueError):m.fused(*args)

    def values(self):
        _,vrf,csr=m.gold(); d={('g75_result',0):2900,('g75_result',4):0,('num_failed',0):0,('tohost',0):1}
        d.update({('hfm_vrf',(p*512+i)*8):x for p,row in enumerate(vrf) for i,x in enumerate(row)})
        d.update({('hfm_csr',(p*5+i)*8):x for p,row in enumerate(csr) for i,x in enumerate(row)})
        return d

    def test_complete_oracle(self):
        d=self.values();m.oracle(lambda n,o=0,size=8:d.get((n,o)))

    def test_corrupt_full_vrf_tail_mask_flags_frm_terminal_rejected(self):
        for key in (('hfm_vrf',0),('hfm_vrf',(3*512+24*16+15)*8),
                    ('hfm_vrf',(2*512+24*16)*8),('hfm_csr',4*8),
                    ('hfm_csr',9*8),('num_failed',0),('tohost',0)):
            d=self.values();d[key]^=1
            with self.assertRaises(ValueError):m.oracle(lambda n,o=0,size=8:d.get((n,o)))

    def test_missing_full_vrf_rejected(self):
        d=self.values();del d['hfm_vrf',16376]
        with self.assertRaises(ValueError):m.oracle(lambda n,o=0,size=8:d.get((n,o)))

    def test_scope_and_no_division_or_reset(self):
        text=m.APP.read_text()
        self.assertIn('vfmacc.vv',text);self.assertNotIn('vfdiv',text);self.assertNotIn('rst_n',text)
        inputs,vrf,csr=m.gold()
        self.assertEqual([x[0] for x in csr],[64,64,64,31])
        self.assertEqual([x[4] for x in csr],[1,33,1,1])
        self.assertEqual(len(vrf),4)


if __name__=='__main__':unittest.main()
