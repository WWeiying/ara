import json
from pathlib import Path
import shutil
import tempfile
import unittest

import audit_capture as audit


class CaptureAuditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = audit.DEFAULT / audit.CAPTURES['decode'][0]
        self.dest = self.root / self.source.name
        self.dest.mkdir()
        for name in ('result.json', 'source-pins.json', 'ffn_norm-0_f32.bin',
                     'ffn_gate.bin', 'ffn_up.bin'):
            shutil.copyfile(self.source / name, self.dest / name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid(self):
        self.assertEqual(audit.audit(self.root, 'decode')['captured_n'], 128)

    def test_corrupt_weight_rejected(self):
        path = self.dest / 'ffn_up.bin'
        data = bytearray(path.read_bytes())
        data[100] ^= 1
        path.write_bytes(data)
        with self.assertRaises(ValueError):
            audit.audit(self.root, 'decode')

    def test_wrong_shape_rejected(self):
        path = self.dest / 'result.json'
        result = json.loads(path.read_text())
        result['activation']['rows'] = 4
        path.write_text(json.dumps(result))
        with self.assertRaises(ValueError):
            audit.audit(self.root, 'decode')


if __name__ == '__main__':
    unittest.main()
