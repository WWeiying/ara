"""Coordinate/mask tests; one read-only check of the genuine local capture."""
import struct
import unittest
import prefill_slice_data as r


class SliceTests(unittest.TestCase):
    def test_coordinate_ramp(self):
        blobs = {name:bytes(spec[3]) for name,spec in r.SHAPES.items()}
        blobs['attn_q_input-0'] = b''.join(struct.pack('<I',i) for i in range(64*64*9))
        blobs['kqv_out-0'] = b''.join(struct.pack('<I',i) for i in range(576*64))
        blobs['attn_mask_input-0'] = b''.join(struct.pack('<H',0 if i <= t else 0xfc00)
                                             for t in range(64) for i in range(256))
        sliced = r.crop(blobs)
        for h in range(9):
            for t in range(4):
                for d in range(64):
                    self.assertEqual(struct.unpack_from('<I',sliced['query'],(h*256+t*64+d)*4)[0],
                                     h*4096+(32+t)*64+d)
        self.assertEqual(struct.unpack_from('<I',sliced['golden'],0)[0],32*576)
        self.assertEqual(struct.unpack_from('<I',sliced['golden'],9212)[0],36*576-1)
        bad = dict(blobs,**{'attn_mask_input-0':bytes(32768)})
        with self.assertRaisesRegex(ValueError,'causal mask'):
            r.crop(bad)

    def test_real_capture(self):
        sliced,pins = r.load()
        self.assertEqual(len(sliced['query']),9216)
        self.assertEqual(len(sliced['golden']),9216)
        self.assertGreaterEqual(len(pins),11)


if __name__ == '__main__':
    unittest.main()
