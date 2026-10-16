import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import zipfile
import hashlib

SCRIPT = Path(__file__).resolve().parents[1] / "ethernet/prepare_ara_integration.py"
spec = importlib.util.spec_from_file_location("prepare_ara_integration", SCRIPT)
prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)


class PreparationTest(unittest.TestCase):
    def test_reserved_and_crossing_ranges(self):
        for start, size in ((0xFEFF0000, 8), (0xFEFEFFF8, 16),
                            (0xFF000000, 8), (0xFFFF0000, 8),
                            (0x100000000, 8), (0x7FFFFFF8, 16)):
            with self.subTest(start=hex(start)):
                with self.assertRaises(ValueError):
                    prep.validate_image(SimpleNamespace(segments=[
                        SimpleNamespace(address=start, size=size)]))
        prep.validate_image(SimpleNamespace(segments=[
            SimpleNamespace(address=0xFEFEFFF8, size=8)]))

    def test_real_smoke_snapshot_and_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "plan"
            report = prep.prepare(prep.SOFTWARE / "host_smoke.elf", [], output)
            self.assertEqual(report["payload_bytes_including_bss"], 4800)
            self.assertFalse(report["launch_allowed"])
            self.assertFalse(report["hardware_validated"])
            with zipfile.ZipFile(output / "sources.zip") as archive:
                for item in report["sources"]:
                    self.assertEqual(hashlib.sha256(archive.read(item["path"])).hexdigest(),
                                     item["sha256"])
            with self.assertRaises(FileExistsError):
                prep.prepare(prep.SOFTWARE / "host_smoke.elf", [], output)

    def test_real_image_raw_overlap_and_reserved_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "data.bin"
            raw.write_bytes(bytes(16))
            for address in (0x80000000, 0xFEFEFFF8, 0xFFFF0000):
                output = Path(directory) / hex(address)
                with self.assertRaises(ValueError):
                    prep.prepare(prep.SOFTWARE / "host_smoke.elf", [(address, raw)], output)
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
