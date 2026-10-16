import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ethernet"))
import freeze_ara_build as freeze


class FreezeTests(unittest.TestCase):
    def test_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "file").write_text("data")
            self.assertEqual(freeze.checked_relative(root, "file"), root / "file")
            for name in ("../file", "/file", "C:/file", "a\\b", "missing"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    freeze.checked_relative(root, name)

    def test_mismatched_firmware_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xsa = root / "xsa"
            xsa.write_bytes(b"changed")
            metadata = root / "inputs.json"
            metadata.write_text(json.dumps([{"Path": "C:\\loader_no_bitstream.xsa", "Hash": "0" * 64}]))
            output = root / "out"
            with self.assertRaisesRegex(ValueError, "metadata mismatch"):
                freeze.freeze(root, root / "bd", xsa, root / "elf", metadata, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
