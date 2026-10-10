import struct
import unittest
import build_qbs_payload_matrix4 as b


class TestFixture(unittest.TestCase):
    def test_independent_q6_unpack_matches_logical_coefficients(self):
        for phase in range(4):
            w,a,g=b.fixture(phase);start=64+b.WP[phase]
            for r in range(8):
                row=w[start+210*r:start+210*(r+1)]
                for i in range(256):
                    half=i//128;quarter=(i%128)//32;lane=i%32
                    q=((row[64*half+32*(quarter&1)+lane]>>(4 if quarter>=2 else 0))&15)|(((row[128+32*half+lane]>>(2*quarter))&3)<<4)
                    self.assertEqual(q-32,b.quant(r,i))
                self.assertEqual([v if v<128 else v-256 for v in row[192:208]],[b.scale(r,g) for g in range(16)])
                self.assertEqual(row[208:210],b'\x00\x3c')
    def test_static_guards_and_full_frame(self):
        for phase in range(4):
            w,a,g=b.fixture(phase);ws=64+b.WP[phase];s=64+b.AP[phase]
            self.assertEqual(w[:ws],bytes([0xa5])*ws);self.assertEqual(w[ws+1680:],bytes([0xa5])*(2048-ws-1680))
            self.assertEqual(a[:s],bytes([0x5a])*s);self.assertEqual(len(b.expected_frame(phase)),4096)
            frame=b.expected_frame(phase)
            for reg in list(range(8))+list(range(16,32)):
                self.assertEqual(frame[128*reg:128*(reg+1)],b.seed_bytes()[128*reg:128*(reg+1)])
    def test_bsums_and_full64_golden(self):
        for phase in range(4):
            w,a,g=b.fixture(phase);s=64+b.AP[phase];self.assertEqual(len(g),64)
            for c in range(8):
                for group in range(16):
                    self.assertEqual(struct.unpack_from('<h',a,s+2080+16*group+2*c)[0],sum(b.activation(phase,c,i) for i in range(16*group,16*group+16)))
    def test_only_four_jobs(self):
        with self.assertRaises(ValueError):b.fixture(4)


if __name__=='__main__':unittest.main()
