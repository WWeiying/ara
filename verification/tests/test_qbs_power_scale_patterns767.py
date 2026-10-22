import math
import struct
import unittest
import qbs_power_scale_patterns767 as p
from test_qbs_payload_residual4_766 import decoded


class PowerScale(unittest.TestCase):
    def test_native_weight_and_activation_values(self):
        for phase in range(4):
            w,a,gold=p.fixture(phase)
            for ctx in range(8):
                self.assertEqual(sorted(p.activation(phase,ctx,i) for i in range(256)),list(range(-128,128)))
                for row in range(8):
                    b=w[64+p.SIZE[phase]*row:64+p.SIZE[phase]*(row+1)]
                    for i in range(256):
                        value=decoded(1 if phase<2 else 3,b,i)
                        expected=p.scale(phase,row,i//16)*p.quant(phase,row,i)-(0 if phase<2 else p.minimum(phase,row,i//16))
                        self.assertEqual(value,expected)
                    dot,aux=p.integer_pair(phase,row,ctx)
                    expected=math.ldexp(float(dot-aux),p.WE[(row+phase)%8]+p.AE[(ctx+phase)%8])
                    self.assertEqual(gold[8*ctx+row],int.from_bytes(struct.pack('<f',expected),'little'))

    def test_each_pipeline_operation_exact_and_normal(self):
        for phase in range(4):
            for row in range(8):
                for ctx in range(8):
                    dot,aux=p.integer_pair(phase,row,ctx);e=p.WE[(row+phase)%8]+p.AE[(ctx+phase)%8]
                    for n,power in [(dot,0),(aux,0),(1,e),(dot,e),(aux,e),(dot-aux,e)]:
                        bits=p.exact32(n,power)
                        if n:self.assertTrue(0<(bits>>23)&255<255)
                        self.assertEqual(struct.unpack('<f',struct.pack('<I',bits))[0],math.ldexp(n,power))

    def test_positive_normal_scales_and_exponent_bit_entropy(self):
        weight=[(e+15)<<10 for e in p.WE];act=[(e+127)<<23 for e in p.AE]
        for x in weight:self.assertTrue(0<(x>>10)&31<31 and x>>15==0 and x&1023==0)
        for x in act:self.assertTrue(0<(x>>23)&255<255 and x>>31==0 and x&0x7fffff==0)
        for bit in range(5):self.assertEqual({x>>(10+bit)&1 for x in weight},{0,1})
        for bit in range(8):self.assertEqual({x>>(23+bit)&1 for x in act},{0,1})

    def test_unsafe_or_rounded_gold_rejected(self):
        for n,power in [(2**24+1,0),(1,-127),(1,128),(True,0)]:
            with self.assertRaises(ValueError):p.exact32(n,power)

    def test_preservation_and_full_source_extent(self):
        for phase in range(4):
            w,a,_=p.fixture(phase);self.assertEqual((len(w),len(a)),(2048,2496))
            image=p.frame(phase);seed=p.previous.base.seed_bytes()
            destinations={1024+128*c+i for c in range(8) for i in range(32)}
            self.assertTrue(all(image[i]==seed[i] for i in range(4096) if i not in destinations))


if __name__=='__main__':unittest.main()
