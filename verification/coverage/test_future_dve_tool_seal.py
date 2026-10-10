"""Offline files and synthetic /proc records only; never launches DVE."""
import copy
import os
from pathlib import Path
import tempfile
import unittest

import future_dve_tool_seal as s


class ToolSealTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="future-dve-seal-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.wrapper = self.root / "vcs/bin/dve"
        self.binary = self.root / "vcs/gui/dve/linux64/bin/dve.exe"
        for path, data in ((self.wrapper, b"#!/bin/sh\n"), (self.binary, b"\x7fELF\x02\x01" + b"\0" * 58)):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(0o755)
        self.proc = self.root / "proc"
        boot = self.proc / "sys/kernel/random/boot_id"
        boot.parent.mkdir(parents=True)
        boot.write_text(s.boot_id())
        self.seal = s.prepare(self.wrapper, environment={"VCS_HOME": str(self.root / "vcs")})
        self.tick = self.seal["created_boottime_ns"] * self.seal["ticks_per_second"] // 1_000_000_000 + 2
        self.make_process(100, 1, self.tick)
        self.make_process(101, 100, self.tick + 1)
        (self.proc / "101/exe").symlink_to(self.binary)

    def make_process(self, pid, parent, tick):
        path = self.proc / str(pid)
        path.mkdir(exist_ok=True)
        fields = ["S", str(parent)] + ["0"] * 17 + [str(tick)]
        (path / "stat").write_text(str(pid) + " (dve process (nested)) " + " ".join(fields))

    def launch(self):
        return s.bind_launch(self.seal, 100, proc=self.proc)

    def test_real_binary_sealed_and_runtime_witness_completed(self):
        self.assertEqual(self.seal["tools"]["dve_executable"]["resolved"], str(self.binary))
        launch = self.launch()
        record = s.witness(self.seal, launch, 101, proc=self.proc)
        (self.proc / "100/stat").unlink()
        (self.proc / "100").rmdir()
        result = s.finish(self.seal, launch, [record], 0, proc=self.proc)
        self.assertTrue(record["runtime_identity_verified"])
        self.assertFalse(result["application_approval"])
        self.assertFalse(result["retrospective_capture_qualification"])

    def test_missing_or_script_binary_is_not_wrapper_only_seal(self):
        self.binary.unlink()
        with self.assertRaises((ValueError, FileNotFoundError)):
            s.prepare(self.wrapper)
        self.binary.write_bytes(b"#!/bin/sh\n")
        self.binary.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "ELF"):
            s.prepare(self.wrapper)

    def test_posthoc_process_predating_seal_rejected(self):
        self.make_process(100, 1, self.tick - 100)
        with self.assertRaisesRegex(ValueError, "predates"):
            self.launch()

    def test_wrong_actual_executable_rejected(self):
        launch = self.launch()
        (self.proc / "101/exe").unlink()
        (self.proc / "101/exe").symlink_to(self.wrapper)
        with self.assertRaisesRegex(ValueError, "real DVE"):
            s.witness(self.seal, launch, 101, proc=self.proc)

    def test_binary_mutation_and_same_bytes_replacement_rejected(self):
        original = self.binary.read_bytes()
        self.binary.write_bytes(original + b"changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            s.recheck(self.seal)
        self.binary.unlink()
        self.binary.write_bytes(original)
        self.binary.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "changed"):
            s.recheck(self.seal)

    def test_pid_reuse_foreign_lineage_and_foreign_boot_rejected(self):
        launch = self.launch()
        self.make_process(100, 1, self.tick + 100)
        with self.assertRaisesRegex(ValueError, "Root PID"):
            s.witness(self.seal, launch, 101, proc=self.proc)
        self.make_process(100, 1, self.tick)
        self.make_process(101, 0, self.tick + 1)
        with self.assertRaisesRegex(ValueError, "descendant"):
            s.witness(self.seal, launch, 101, proc=self.proc)
        (self.proc / "sys/kernel/random/boot_id").write_text("foreign")
        with self.assertRaisesRegex(ValueError, "boot"):
            self.launch()

    def test_no_witness_failure_or_still_running_cannot_finish(self):
        launch = self.launch()
        with self.assertRaisesRegex(ValueError, "No live"):
            s.finish(self.seal, launch, [], 0, proc=self.proc)
        record = s.witness(self.seal, launch, 101, proc=self.proc)
        with self.assertRaisesRegex(ValueError, "succeed"):
            s.finish(self.seal, launch, [record], 1, proc=self.proc)
        with self.assertRaisesRegex(ValueError, "still running"):
            s.finish(self.seal, launch, [record], 0, proc=self.proc)

    def test_modified_seal_rejected(self):
        changed = copy.deepcopy(self.seal)
        changed["tools"]["dve_executable"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "prelaunch"):
            s.recheck(changed)


if __name__ == "__main__":
    unittest.main()
