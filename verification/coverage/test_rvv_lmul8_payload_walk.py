import unittest
import rvv_lmul8_payload_walk as p

class Model(unittest.TestCase):
    def test_all_walking_bits(self):
        source=p.expected(1,'source')
        values=[int.from_bytes(source[16+8*i:24+8*i],'little') for i in range(128)]
        self.assertEqual(values[:64],[1<<i for i in range(64)])
        self.assertEqual(values[64:],[p.MASK^(1<<i) for i in range(64)])
    def test_full_guard(self):
        for cell in range(2):
            for kind in ('source','shift','narrow','wide'):
                data=p.expected(cell,kind)
                self.assertEqual(len(data),1056)
                self.assertEqual(data[:16],bytes([0xa5])*16)
                self.assertEqual(data[-16:],bytes([0xa5])*16)
    def test_narrow_wide(self):
        for cell,count in enumerate((64,128)):
            n=p.expected(cell,'narrow');w=p.expected(cell,'wide')
            for i in range(count):
                self.assertEqual(n[16+4*i:20+4*i],w[16+8*i:20+8*i])
                self.assertEqual(w[20+8*i:24+8*i],bytes(4))
    def test_mask_tail(self):
        for cell,vl in enumerate((3,33,1024)):
            b=p.control_expected(cell)
            self.assertEqual(b[16+vl:1040],bytes(1024-vl))
            self.assertEqual(b[16:1040:2],bytes(512))
    def test_reject_empty_trace(self):
        with self.assertRaises(ValueError):p.validate([],{'tohost':0x80001000},'')
    def test_check_total(self):
        self.assertEqual(p.CHECKS,2*(132*4+9)+3*(1056*2+128+3))

if __name__=='__main__':unittest.main()
