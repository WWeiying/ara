import unittest

from audit_x32_v2 import audit_layout


class LayoutAuditTests(unittest.TestCase):
    def test_q4_and_q6_inverse(self):
        for profile,size,fields in (
            (1,144,((0,2,2),(2,2,2),(4,12,1),(16,128,1))),
            (2,210,((208,2,2),(192,16,1),(0,128,1),(128,64,1)))):
            rows,kb = 64,8
            original = bytes((i*37+i//size*13+i//(size*kb))%256 for i in range(rows*kb*size))
            packed = bytearray()
            for group in range(0,rows,32):
                for b in range(kb):
                    for offset,length,width in fields:
                        for item in range(0,length,width):
                            for row in range(group,group+32):
                                start = (row*kb+b)*size+offset+item
                                packed.extend(original[start:start+width])
            self.assertTrue(audit_layout(profile,rows,kb,original,packed)['recovered_original_bit_exact'])
            packed[513] ^= 1
            with self.assertRaises(ValueError):
                audit_layout(profile,rows,kb,original,packed)

    def test_dimensions_and_unqualified_format(self):
        with self.assertRaises(ValueError):
            audit_layout(1,31,8,b'',b'')
        with self.assertRaises(ValueError):
            audit_layout(9,32,8,b'',b'')


if __name__ == '__main__':
    unittest.main()
