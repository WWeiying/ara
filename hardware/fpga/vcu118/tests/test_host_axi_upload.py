#!/usr/bin/env python3
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import host_axi_upload as upload


class UploadTests(unittest.TestCase):
    def fixture(self, root):
        software = root / "software"
        netlist = software / "axi_netlists/run01"
        netlist.mkdir(parents=True)
        for name in upload.NETLIST_FILES:
            (netlist / name).write_text("fixture\n", encoding="utf-8")
        (netlist / "inspection.json").write_text('{"collected":true}', encoding="utf-8-sig")
        (netlist / "axi_netlist.rpt").write_text("SIZE arsize bits=???\nINSPECTION_COMPLETE\n")
        (netlist / "large.dcp").write_text("never upload")
        (netlist / "design.bit").write_text("never upload")
        mapping = software / "burst_maps/run01/run"
        (mapping / "transport").mkdir(parents=True)
        (mapping / "map.json").write_text('{"regions":[],"error":"partial collection"}')
        (mapping / "transport/transport.jsonl").write_text('{"checked":true}\n')
        return software, netlist, mapping

    def test_allowlist_archive_hashes_and_partial_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, netlist, mapping = self.fixture(root)
            files = upload.evidence_files(netlist, mapping)
            upload.package(files, root, {"diagnostic_only": True})
            manifest = json.loads((root / "manifest.json").read_text())
            with zipfile.ZipFile(root / "evidence.zip") as bundle:
                self.assertEqual(len(bundle.namelist()), 9)
                self.assertFalse(any(name.endswith((".bit", ".dcp")) for name in bundle.namelist()))
                self.assertIn("error", json.loads(bundle.read("burst_map/map.json")))
                for entry in manifest["files"]:
                    data = bundle.read(entry["path"])
                    self.assertEqual(len(data), entry["bytes"])
                    self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])
            self.assertEqual(hashlib.sha256((root / "evidence.zip").read_bytes()).hexdigest(),
                             manifest["archive_sha256"])

    def test_missing_netlist_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, netlist, _ = self.fixture(Path(tmp))
            (netlist / "i_read_unit.v").unlink()
            with self.assertRaisesRegex(ValueError, "Required evidence"):
                upload.evidence_files(netlist, None)

    def test_incomplete_inspection_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, netlist, _ = self.fixture(Path(tmp))
            (netlist / "inspection.json").write_text('{"collected":false}')
            with self.assertRaisesRegex(ValueError, "incomplete"):
                upload.evidence_files(netlist, None)

    def test_missing_completion_marker_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, netlist, _ = self.fixture(Path(tmp))
            (netlist / "axi_netlist.rpt").write_text("partial report")
            with self.assertRaisesRegex(ValueError, "INSPECTION_COMPLETE"):
                upload.evidence_files(netlist, None)

    def test_limits_reject_oversize(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, netlist, _ = self.fixture(root)
            with patch.object(upload, "MAX_INPUT_BYTES", 1):
                with self.assertRaisesRegex(ValueError, "128 MiB"):
                    upload.evidence_files(netlist, None)
            files = upload.evidence_files(netlist, None)
            with patch.object(upload, "MAX_ARCHIVE_BYTES", 1):
                with self.assertRaisesRegex(ValueError, "48 MiB"):
                    upload.package(files, root, {})

    def test_real_git_push_does_not_touch_user_branch_index_or_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "user checkout with spaces"
            work.mkdir()
            software, _, _ = self.fixture(work)
            upload.git(work, "init", "-q")
            (work / "existing.txt").write_text("original")
            upload.git(work, "add", "existing.txt")
            upload.git(work, "-c", "user.name=Test", "-c", "user.email=test@localhost",
                       "-c", "commit.gpgsign=false", "commit", "-qm", "original")
            (work / "existing.txt").write_text("user staged change")
            upload.git(work, "add", "existing.txt")
            (work / "existing.txt").write_text("additional unstaged change")
            (work / "untracked.txt").write_text("private data")
            bare = root / "remote.git"
            bare.mkdir()
            upload.git(bare, "init", "--bare", "-q")
            upload.git(work, "remote", "add", "origin", str(bare))
            before = [upload.git(work, *cmd) for cmd in
                      (("rev-parse", "HEAD"), ("symbolic-ref", "HEAD"),
                       ("status", "--porcelain"), ("diff", "--cached"), ("diff",))]
            bundle_dir = root / "isolated bundle"
            bundle_dir.mkdir()
            output = io.StringIO()
            with patch.object(upload.tempfile, "mkdtemp", return_value=str(bundle_dir)), \
                 contextlib.redirect_stdout(output):
                self.assertEqual(upload.main(["--software", str(software), "--push"]), 0)
            branch = next(line.split()[1] for line in output.getvalue().splitlines()
                          if line.startswith("UPLOADED_BRANCH"))
            self.assertTrue(branch.startswith("fpga-evidence/axi-"))
            self.assertEqual(upload.git(bare, "ls-tree", "--name-only", branch).splitlines(),
                             ["evidence.zip", "manifest.json"])
            after = [upload.git(work, *cmd) for cmd in
                     (("rev-parse", "HEAD"), ("symbolic-ref", "HEAD"),
                      ("status", "--porcelain"), ("diff", "--cached"), ("diff",))]
            self.assertEqual(before, after)
            self.assertEqual((work / "untracked.txt").read_text(), "private data")

    def test_push_failure_is_not_success_and_retains_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            software, _, _ = self.fixture(root)
            bundle = root / "bundle"
            bundle.mkdir()
            output, errors = io.StringIO(), io.StringIO()
            with patch.object(upload, "git", return_value="fixture"), \
                 patch.object(upload, "publish", side_effect=RuntimeError("push rejected")), \
                 patch.object(upload.tempfile, "mkdtemp", return_value=str(bundle)), \
                 contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                self.assertEqual(upload.main(["--software", str(software), "--push"]), 1)
            self.assertNotIn("UPLOADED_BRANCH", output.getvalue())
            self.assertIn("Local evidence retained", errors.getvalue())
            self.assertTrue((bundle / "evidence.zip").is_file())

    def test_default_packages_without_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            software, _, _ = self.fixture(root)
            bundle = root / "bundle"
            bundle.mkdir()
            with patch.object(upload, "git", return_value="fixture"), \
                 patch.object(upload, "publish") as publish, \
                 patch.object(upload.tempfile, "mkdtemp", return_value=str(bundle)), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(upload.main(["--software", str(software)]), 0)
            publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
