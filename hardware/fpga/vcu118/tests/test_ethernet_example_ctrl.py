import hashlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_ethernet_example_ctrl as check


class BundleTests(unittest.TestCase):
    def bundle(self, members=None):
        members = members or {"example/imports/ctrl.v": b"module ctrl; endmodule\n"}
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            for name, data in members.items():
                archive.writestr(name, data)
        raw = stream.getvalue()
        return raw, {"archive_sha256": hashlib.sha256(raw).hexdigest(), "files": [
            {"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in members.items()]}

    def test_verified_members(self):
        raw, manifest = self.bundle()
        with patch.object(check, "SOURCES", {"ctrl.v": manifest["files"][0]["sha256"]}):
            self.assertEqual(check.verify_bundle(raw, manifest)["example/imports/ctrl.v"],
                             b"module ctrl; endmodule\n")

    def test_bad_hash_length_and_members(self):
        for field in ("archive", "hash", "length", "missing", "duplicate"):
            raw, manifest = self.bundle()
            if field == "archive":
                manifest["archive_sha256"] = "0" * 64
            elif field == "hash":
                manifest["files"][0]["sha256"] = "0" * 64
            elif field == "length":
                manifest["files"][0]["bytes"] += 1
            elif field == "missing":
                manifest["files"] = []
            else:
                manifest["files"] *= 2
            with self.subTest(field=field), self.assertRaises(ValueError):
                check.verify_bundle(raw, manifest)

    def test_unreviewed_source(self):
        raw, manifest = self.bundle()
        with patch.object(check, "SOURCES", {"ctrl.v": "0" * 64}), self.assertRaisesRegex(ValueError, "Unreviewed"):
            check.verify_bundle(raw, manifest)

    def test_unsafe_names(self):
        for name in ("../ctrl.v", "/ctrl.v", "C:/ctrl.v", "example\\ctrl.v"):
            raw, manifest = self.bundle({name: b"data"})
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Unsafe"):
                check.verify_bundle(raw, manifest)

    def test_size_limit(self):
        raw, manifest = self.bundle({"large": b"x" * (4 * 1024 * 1024 + 1)})
        with self.assertRaisesRegex(ValueError, "exceeds"):
            check.verify_bundle(raw, manifest)

    def test_commit_is_not_shell_or_revision_expression(self):
        with patch.object(check.subprocess, "check_output") as call:
            self.assertEqual(check.main(["--commit", "HEAD:evidence.zip"]), 1)
            call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
