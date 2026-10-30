"""Capture validation tests using explicit synthetic tensors, not model evidence."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
import capture_host as r
from test_layout import fixture


def write_fixture(root,kind):
    block = root/'decode/block'
    block.mkdir(parents=True)
    def tensor(name,meta,data):
        (block/(name+'.json')).write_text(json.dumps(meta))
        (block/(name+'.bin')).write_bytes(data)
    tensor('attn_q_input-0',dict(type='f32',shape=[128,1,12,1],nbytes=6144),bytes(6144))
    tensor('kqv_out-0',dict(type='f32',shape=[1536,1,1,1],nbytes=6144),bytes(6144))
    mask = b'\0\0'*65+b'\0\xfc'*63
    tensor('attn_mask_input-0',dict(type='f16',shape=[128,1,1,1],nbytes=256),mask)
    for name,fmt in (('attn_k_input-0',kind),('attn_v_input-0','q8_0')):
        meta,data = fixture(fmt,False)
        tensor(name,meta,data)
    return block


class CaptureTests(unittest.TestCase):
    def test_both_formats_and_no_normalization(self):
        for kind in ('q8_0','q4_0'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                block = write_fixture(root,kind)
                before = {str(p):r.digest(p) for p in block.iterdir()}
                result = r.validate_capture(root,kind)
                self.assertEqual(result['visible_tokens'],65)
                self.assertEqual(result['views']['attn_k_input-0']['type'],kind)
                self.assertEqual(before,{str(p):r.digest(p) for p in block.iterdir()})
                with self.assertRaises(ValueError):
                    r.validate_capture(root,'q4_0' if kind == 'q8_0' else 'q8_0')

    def test_nonfinite_reference_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            block = write_fixture(root,'q8_0')
            (block/'kqv_out-0.bin').write_bytes(struct.pack('<I',0x7fc00000)+bytes(6140))
            with self.assertRaisesRegex(ValueError,'Nonfinite'):
                r.validate_capture(root,'q8_0')


if __name__ == '__main__':
    unittest.main()
