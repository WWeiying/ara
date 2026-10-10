import unittest
import struct
import build_gap113_payload_full8 as b


class Full8Tests(unittest.TestCase):
    def test_shape_substitutions(self):
        body,oracle,assembly=b.templates()
        self.assertIn('c->m == 8 && c->n == 8',body)
        self.assertIn('bits[64]',oracle)
        self.assertIn('m!=8 || n!=8',oracle)
        self.assertEqual(assembly.count('8, 0x0eb5045b'),2)

    def test_substitution_ambiguity(self):
        for source in ('', 'x x'):
            with self.assertRaises(ValueError):b.replace_one(source,'x','y')

    def test_patterns_and_independent_unpack(self):
        scales=set();quants=set();high_masks=set()
        for phase in (0,1):
            w,a,gold=b.fixture(phase);w=w[64+12*phase:944+12*phase];a=a[68:2404]
            expected=[]
            for c in range(8):
                qs=[struct.unpack('b',a[32+8*i+c:33+8*i+c])[0] for i in range(256)]
                self.assertEqual(len(set(qs)),256)
                for g in range(16):
                    self.assertEqual(sum(qs[16*g:16*g+16]),struct.unpack_from('<h',a,2080+16*g+2*c)[0])
                for r in range(8):
                    block=w[110*r:110*(r+1)];dot=0
                    high_masks.update(block[:32])
                    for i in range(256):
                        section,slot=divmod(i//16,4)
                        scale=((block[96+(section%2)*4+slot]>>(4*(section//2)))&15)|(((block[104+slot]>>(2*section))&3)<<4)
                        packet,lane=divmod(i,32)
                        q=(block[32+32*(packet//4)+lane]>>(2*(packet%4)))&3
                        if not (block[lane]>>packet)&1:q-=4
                        scales.add(scale);quants.add(q);dot+=(scale-32)*q*qs[i]
                    expected.append(struct.unpack('<I',struct.pack('<f',dot))[0])
            self.assertEqual(gold,expected)
        self.assertEqual(scales,set(range(64)))
        self.assertEqual(quants,set(range(-4,4)))
        self.assertEqual(high_masks,set(range(256)))

    def test_phase_rejects(self):
        for phase in (-1,2,True):
            with self.assertRaises(ValueError):b.fixture(phase)

    def test_nonduplicate_sources(self):
        self.assertNotEqual(b.APP,b.OLD)
        self.assertNotEqual(b.fixture(0)[:2],b.fixture(1)[:2])


if __name__=='__main__':unittest.main()
