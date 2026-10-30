"""Synthetic layout tests; fixtures are not captured model data."""
import copy
import struct
import unittest
import layout as r


def fixture(kind, interleaved):
    block = r.BLOCK_BYTES[kind]
    row = 4*block
    capacity,heads = 128,2
    token_stride = row*heads if interleaved else row
    head_stride = row if interleaved else row*capacity
    data = bytearray(b'\xff'*(row*capacity*heads))
    for head in range(heads):
        for token in range(65):
            start = head*head_stride+token*token_stride
            for b in range(4):
                struct.pack_into('<H',data,start+b*block,0x3c00)
    return dict(type=kind,shape=[128,capacity,heads,1],
        strides=[block,token_stride,head_stride,len(data)],nbytes=len(data)),bytes(data)


class LayoutTests(unittest.TestCase):
    def test_actual_block_geometry_and_interleaving(self):
        for kind in r.BLOCK_BYTES:
            for interleaved in (False,True):
                meta,data = fixture(kind,interleaved)
                result = r.inspect(meta,data,65)
                self.assertEqual(result['tight_rows_per_head'],not interleaved)
                self.assertEqual(len(result['candidate_read_ranges']),130)
                self.assertEqual(result['visible_payload_bytes'],130*4*r.BLOCK_BYTES[kind])
                self.assertFalse(result['numerical_accepted'])
                self.assertEqual(data,fixture(kind,interleaved)[1])
                # Uninitialized hidden scales are deliberately never read.
                with self.assertRaisesRegex(ValueError,'Nonfinite'):
                    r.inspect(meta,data,66)

    def test_bad_type_shape_stride_and_extent(self):
        meta,data = fixture('q8_0',False)
        changes = [('type','f16'),('shape',[127,128,2,1]),('shape',[128,128,2,2]),
                   ('strides',[1,136,17408,34816]),('strides',[34,136,136,34816]),
                   ('strides',[34,10,17408,34816]),('nbytes',len(data)-1)]
        for field,value in changes:
            bad = copy.deepcopy(meta)
            bad[field] = value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                r.inspect(bad,data,65)
        for visible in (0,129,True):
            with self.assertRaises(ValueError):
                r.inspect(meta,data,visible)

    def test_prefix_and_holes(self):
        self.assertEqual(r.prefix_length(b'\0\0'*65+b'\0\xfc'*63),65)
        for data in (b'',b'\0',b'\0\xfc'*3,b'\0\0\0\xfc\0\0',b'\0\x80',b'\0\x3c'):
            with self.subTest(data=data),self.assertRaises(ValueError):
                r.prefix_length(data)


if __name__ == '__main__':
    unittest.main()
