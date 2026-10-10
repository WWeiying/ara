import json
import struct
import unittest
import build_qbs_payload_toggle_alt762 as b


def unpack(w,a):
    gold=[]
    for c in range(8):
        assert struct.unpack_from('<I',a,4*c)[0]==0x3f800000
        vals=[struct.unpack_from('b',a,32+8*i+c)[0] for i in range(256)]
        for g in range(16):assert sum(vals[16*g:16*g+16])==struct.unpack_from('<h',a,2080+16*g+2*c)[0]
        for r in range(8):
            row=w[110*r:110*(r+1)];assert struct.unpack_from('<H',row,108)[0]==0x3c00
            total=0
            for i in range(256):
                section,slot=divmod(i//16,4)
                scale=((row[96+(section%2)*4+slot]>>(4*(section//2)))&15)|(((row[104+slot]>>(2*section))&3)<<4)
                packet,lane=divmod(i,32);q=(row[32+32*(packet//4)+lane]>>(2*(packet%4)))&3
                if not (row[lane]>>packet)&1:q-=4
                total+=(scale-32)*q*vals[i]
            gold.append(struct.unpack('<I',struct.pack('<f',total))[0])
    return gold


class PayloadTest(unittest.TestCase):
    def test_independent_encoded_oracle(self):
        for p in (0,1):
            w,a,g=b.fixture(p);self.assertEqual(unpack(w[64+12*p:944+12*p],a[68:2404]),g)

    def test_all_contexts_each_pending_boundary_flips(self):
        for p in (0,1):
            for c in range(8):
                for residue in (30,31,32,33):
                    values=[b.activation_byte(p,c,(residue+32*g)%256) for g in range(8)]
                    self.assertEqual(set(values),{0x55,0xaa})
                    self.assertTrue(all((x^y)==255 for x,y in zip(values,values[1:])))

    def test_phase_complement_all256(self):
        for c in range(8):
            self.assertTrue(all(b.activation_byte(0,c,i)^b.activation_byte(1,c,i)==255 for i in range(256)))

    def test_native_bsum_corruption_rejected(self):
        w,a,_=b.fixture(0);a=bytearray(a[68:2404]);a[2080]^=1
        with self.assertRaises(AssertionError):unpack(w[64:944],a)

    def test_scale_corruption_rejected(self):
        w,a,_=b.fixture(1);a=bytearray(a[68:2404]);a[0]^=1
        with self.assertRaises(AssertionError):unpack(w[76:956],a)

    def test_guards_and_extents(self):
        for p in (0,1):
            w,a,g=b.fixture(p);self.assertEqual((len(w),len(a),len(g)),(1024,2496,64))
            self.assertEqual(w[:64+12*p],bytes([0xa5])*(64+12*p));self.assertEqual(a[:68],bytes([0x5a])*68)
            self.assertEqual(a[2404:],bytes([0x5a])*92)

    def test_bounds_failclosed(self):
        for args in ((2,0,0),(0,8,0),(0,0,256),(False,0,0)):
            with self.assertRaises(ValueError):b.activation_byte(*args)

    def test_exact_static_target_not_high_capacity_claim(self):
        t=json.loads(b.TARGET.read_bytes())
        self.assertEqual(sum(len(r['missing_serialized_coordinates']) for x in t['scopes'].values()
                             for r in x['pure_data_missing']),32)
        self.assertFalse(t['candidate']['simulator_launched'])


if __name__=='__main__':unittest.main()
