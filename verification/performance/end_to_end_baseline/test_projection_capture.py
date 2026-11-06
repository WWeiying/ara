import struct
from pathlib import Path
import tempfile
import unittest

from check_projection_capture import check
from run_projection_capture_v3 import dependency_pin, TOOLCHAIN


def fixture():
    text = 'PROJECTION_CAPTURE_TOKENS count=40 ids='+','.join(map(str, range(40)))+'\n'
    text += 'PROJECTION_CAPTURE_SHAPE source=attn_norm-0 k=2048 rows=4 tokens=40 type=f32\n'
    for row in range(4):
        for offset in range(0, 2048, 16):
            bits = ''.join(f'{struct.unpack("<I", struct.pack("<f", row+offset+i+0.5))[0]:08x}' for i in range(16))
            text += f'PROJECTION_CAPTURE_DATA row={row} offset={offset} bits={bits}\n'
    return text+'PROJECTION_CAPTURE_DONE bytes=32768 stop=before_first_projection performance=not_measured\n'


class ProjectionCaptureTests(unittest.TestCase):
    def test_new_inputs_only_within_toolchain_and_old_pins_take_precedence(self):
        header = TOOLCHAIN/'riscv64-buildroot-linux-gnu/sysroot/usr/include/stdc-predef.h'
        self.assertIsNone(dependency_pin(header, {}))
        self.assertEqual(dependency_pin(header, {str(header): 'previous-sha'}), 'previous-sha')
        with tempfile.NamedTemporaryFile() as f:
            with self.assertRaises(ValueError): dependency_pin(Path(f.name), {})

    def test_payload_and_little_endian(self):
        payload, metadata = check(fixture())
        self.assertEqual(len(payload), 32768)
        self.assertEqual(struct.unpack('<f', payload[:4])[0], 0.5)
        self.assertEqual(struct.unpack('<f', payload[8192:8196])[0], 1.5)
        self.assertFalse(metadata['complete_model_executed'])

    def test_reject_truncation_duplicate_and_bad_shape(self):
        text = fixture()
        for broken in (text[:-10], text.replace('k=2048', 'k=1024'), text+text,
                       text.replace('row=1 offset=0', 'row=0 offset=0'),
                       text.replace('3f000000', '7fc00000', 1),
                       text.replace('bits=', 'bits=0', 1),
                       text+'PROJECTION_CAPTURE_FAIL reason=test\n'):
            with self.assertRaises(ValueError): check(broken)


if __name__ == '__main__': unittest.main()
