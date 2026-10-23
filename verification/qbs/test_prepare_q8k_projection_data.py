import struct
import unittest
from prepare_q8k_projection_data import q4_values,q8_rows


class TestProjectionData(unittest.TestCase):
    def test_q4_nibbles_and_minima(self):
        block=struct.pack("<ee",0.5,0.25)+bytes([1]*4+[2]*4+[0x21]*4)+bytes([0xa3]*128)
        result=q4_values(block)
        self.assertEqual(len(result),256)
        self.assertEqual(result[:32],[1.0]*32)
        self.assertEqual(result[32:64],[4.5]*32)
        self.assertEqual(result[128:160],[1.0]*32)
        self.assertEqual(result[160:192],[4.5]*32)

    def test_q8_interleave_and_sums(self):
        raw=struct.pack("<4f",1,2,3,4)+struct.pack("<1024b",*([1,2,-3,-4]*256))+struct.pack("<64h",*([16,32,-48,-64]*16))
        rows=q8_rows(raw,256)
        self.assertEqual(rows,[[1]*256,[4]*256,[-9]*256,[-16]*256])
        with self.assertRaises(ValueError):q8_rows(raw[:-1],256)
        raw=raw[:-2]+b"\0\0"
        with self.assertRaises(ValueError):q8_rows(raw,256)

    def test_q4_high_scale_bits(self):
        # First four bytes carry the high scale bits for groups 4..7;
        # bytes 4..7 carry their high minimum bits.
        block=struct.pack("<ee",1.0,1.0)+bytes([0xc0]*8+[0xf0]*4)+bytes([0x11]*128)
        values=q4_values(block)
        self.assertEqual(values[:128],[0.0]*128)
        self.assertEqual(values[128:],[48.0-63.0]*128)

    def test_wrong_geometry(self):
        with self.assertRaises(ValueError):q4_values(bytes(143))
        with self.assertRaises(ValueError):q8_rows(bytes(1168),255)


if __name__ == "__main__":unittest.main()
