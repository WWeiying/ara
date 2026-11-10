#!/usr/bin/env python3
import struct
import unittest

import run_capture


def fixture():
    rows = ['STAGE2_CAPTURE_TOKENS count=40 ids=' + ','.join(map(str, range(40)))]
    for name in ('attn_norm-0', 'ffn_norm-0'):
        rows.append(f'STAGE2_CAPTURE_SHAPE source={name} k=2048 rows=8 tokens=40 type=f32')
        for row in range(8):
            value = struct.unpack('<I', struct.pack('<f', float(row+1)))[0]
            for offset in range(0, 2048, 16):
                rows.append(f'STAGE2_CAPTURE_DATA source={name} row={row} offset={offset} bits=' +
                            f'{value:08x}'*16)
    rows.append('STAGE2_CAPTURE_DONE tensors=2 rows=8 stop=before_first_ffn_projection')
    return '\n'.join(rows)


class CaptureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = fixture()

    def test_complete(self):
        values = run_capture.parse(self.text, list(range(40)))
        self.assertEqual({key: len(value) for key, value in values.items()},
                         {'attn_norm-0': 65536, 'ffn_norm-0': 65536})

    def test_missing_chunk(self):
        text = self.text.replace('STAGE2_CAPTURE_DATA source=attn_norm-0 row=0 offset=0',
                                 'NOT_CAPTURE_DATA source=attn_norm-0 row=0 offset=0', 1)
        with self.assertRaises(ValueError):
            run_capture.parse(text, list(range(40)))

    def test_duplicate_chunk(self):
        text = self.text.replace('row=0 offset=16', 'row=0 offset=0', 1)
        with self.assertRaises(ValueError):
            run_capture.parse(text, list(range(40)))

    def test_wrong_tokens(self):
        with self.assertRaises(ValueError):
            run_capture.parse(self.text, list(reversed(range(40))))

    def test_nonfinite(self):
        text = self.text.replace('bits=3f800000', 'bits=7fc00000', 1)
        with self.assertRaises(ValueError):
            run_capture.parse(text, list(range(40)))


if __name__ == '__main__':
    unittest.main()
