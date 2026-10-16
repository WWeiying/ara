import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ethernet"))
import freeze_ara_build as freeze


class FreezeTests(unittest.TestCase):
    def test_freeze_profiles_with_mock_vendor_inputs(self):
        for profile in ("host_ethernet", "dual_ddr_ethernet"):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                package = root / "source"
                (package / "software").mkdir(parents=True)
                for name in ("eth_fast_load.py", "eth_load.py"):
                    (package / "software" / name).write_text("# mock sender\n")
                (package / "SHA256SUMS").write_text("".join(
                    f"{freeze.digest(path)}  software/{path.name}\n"
                    for path in sorted((package / "software").iterdir())))
                bd, xsa, elf, metadata = [root / name for name in ("bd", "xsa", "elf", "metadata")]
                bd.write_text(json.dumps({"design": {"design_info": {
                    "name": "loader_bd", "tool_version": "2020.1"}}}))
                with zipfile.ZipFile(xsa, "w") as archive:
                    archive.writestr("loader_bd.hwh", "<mock/>")
                elf.write_bytes(b"mock firmware")
                metadata.write_text(json.dumps([
                    {"Path": name, "Hash": freeze.digest(path)} for name, path in
                    (("loader_no_bitstream.xsa", xsa), ("fast_probe.elf", elf))]))
                output = root / "snapshot"
                with patch.object(freeze, "validate_firmware"), patch.object(freeze, "check_xsa"), \
                        patch.object(freeze.subprocess, "run") as run:
                    result = freeze.freeze(package, bd, xsa, elf, metadata, output, profile=profile)
                self.assertEqual(result["profile"], profile)
                self.assertFalse(result["board_validated"])
                self.assertEqual(run.call_count, 2)
                self.assertTrue(freeze.package_inputs(output / "package"))

    def test_package_inventory_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "rtl.sv"
            payload.write_text("original")
            inventory = root / "SHA256SUMS"
            row = f"{freeze.digest(payload)}  rtl.sv\n"
            inventory.write_text(row)
            self.assertEqual(freeze.package_inputs(root), {"rtl.sv": payload})
            inventory.write_text(row * 2)
            with self.assertRaisesRegex(ValueError, "inventory mismatch"):
                freeze.package_inputs(root)
            inventory.write_text(row)
            payload.write_text("changed")
            with self.assertRaisesRegex(ValueError, "inventory mismatch"):
                freeze.package_inputs(root)
            inventory.write_text("")
            with self.assertRaisesRegex(ValueError, "Empty package"):
                freeze.package_inputs(root)

    def test_invalid_profile_rejected_before_inputs(self):
        with self.assertRaisesRegex(ValueError, "Unsupported frozen profile"):
            freeze.freeze(None, None, None, None, None, None, profile="baseline")

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
