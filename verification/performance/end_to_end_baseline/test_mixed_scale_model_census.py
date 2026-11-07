import struct
import unittest

from mixed_scale_model_census import half_expand, eligible, count_scales


class ScaleCensus(unittest.TestCase):
    def test_all_finite_half_expansions_against_standard_binary16(self):
        for half in range(65536):
            if (half>>10)&31==31: continue
            standard=struct.unpack('<I',struct.pack('<f',struct.unpack('<e',struct.pack('<H',half))[0]))[0]
            self.assertEqual(half_expand(half),standard)

    def test_numerical_admission_edges(self):
        for sign in (0,0x80000000):
            self.assertTrue(eligible(0x3f800000|sign,0x3f800000))
            self.assertFalse(eligible(0x3f800000,0x33800000))
            self.assertTrue(eligible(0x3f800000,0x33800000,True))
        for a,w in ((0,0x3f800000),(1,0x3f800000),(0x7f800000,0x3f800000),
                    (0x7fc00000,0x3f800000),(0x3f800000,0),(0x3f800000,0x3f800001),
                    (0x7f000000,0x47000000),(0x00800000,0x33800000)):
            self.assertFalse(eligible(a,w,True))

    def test_dynamic_weighting_includes_affine_min(self):
        q4=bytearray(144);struct.pack_into('<HH',q4,0,0x3c00,1)
        r=count_scales(q4,[[0x3f800000],[0x40000000]],1,1,'Q4_K')
        self.assertEqual((r['scale_mul'],r['normal_admitted'],r['expanded_admitted']), (4,2,4))
        for bad in (q4[:-1],q4+q4):
            with self.assertRaises(ValueError):count_scales(bad,[[0x3f800000]],1,1,'Q4_K')


if __name__=='__main__':unittest.main()
