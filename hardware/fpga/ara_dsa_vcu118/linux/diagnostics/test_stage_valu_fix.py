import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import stage_valu_fix as stage


class StagingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "old"
        self.target = self.root / "new"
        self.source.mkdir()
        self.old = hashlib.sha256(b"old valu").hexdigest()
        self.new = self.root / "valu.sv"
        self.new.write_bytes(b"fixed valu")
        self.sha = hashlib.sha256(self.new.read_bytes()).hexdigest()
        files = {stage.VALU: b"old valu", "manifest.json": b"{}",
                 "scripts/sources.tcl": b"# original constraints unchanged"}
        rows = []
        for name, data in files.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            rows.append(f"{hashlib.sha256(data).hexdigest()}  {name}\n")
        (self.source / "SHA256SUMS").write_text("".join(rows))
        helper = Path(__file__).resolve().parents[3] / "vcu118/sync.py"
        spec = importlib.util.spec_from_file_location("fpga_sync", helper)
        self.sync = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.sync)

    def run_stage(self):
        with patch.object(stage, "BASELINE", self.old):
            stage.stage(self.source, self.target, self.new, self.sha, self.sync)

    def test_clone_only_sealed_inputs(self):
        (self.source / "old_build.dcp").write_bytes(b"not copied")
        self.run_stage()
        self.assertEqual((self.source / stage.VALU).read_bytes(), b"old valu")
        self.assertEqual((self.target / stage.VALU).read_bytes(), b"fixed valu")
        self.assertFalse((self.target / "old_build.dcp").exists())
        self.assertEqual(self.sync.read_hashes(self.target)[stage.VALU], self.sha)
        with self.assertRaises(RuntimeError):
            self.run_stage()

    def test_changed_source_rejected_before_copy(self):
        (self.source / "manifest.json").write_text("changed")
        with self.assertRaises(RuntimeError):
            self.run_stage()
        self.assertFalse(self.target.exists())

    def test_wrong_fix_rejected(self):
        self.new.write_bytes(b"unexpected")
        with self.assertRaises(RuntimeError):
            self.run_stage()
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
