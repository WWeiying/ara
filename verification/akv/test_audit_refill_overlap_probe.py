import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from audit_refill_overlap_probe import audit
from run_refill_overlap_probe import digest, hashes


class RefillAuditTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        work = self.root / "work"
        work.mkdir()
        for name in ("run.vcs.log", "input.elf", "vector_trace.csv", "commit_trace.csv"):
            (work / name).write_text(name)
        image = self.root / "simv"
        image.write_text("sealed image")
        self.write("pins-before.json", hashes([image]))
        self.write("pins-after.json", hashes([image]))
        self.state = dict(state="PASS", child_pid=None, simulator_exit_code=0)
        self.write("status.json", self.state)
        self.write("result.json", dict(state="PASS", software_cycles={}, trace={}))
        self.uvm = dict(status="PASS", issues=[], sim_image_sha256=hashes([image]),
                        backend_counts=dict(allocations=1, completions=1),
                        axi_read_counts=dict(pending=0), axi_write_counts=dict(pending=0))
        for key, name in (("elf_sha256", "input.elf"), ("log_sha256", "run.vcs.log"),
                          ("vector_trace_sha256", "vector_trace.csv")):
            self.uvm[key] = digest(work / name)
        self.write("uvm_result.json", self.uvm)
        self.seal()
        self.addCleanup(patch.stopall)
        patch("audit_refill_overlap_probe.check_log", return_value=dict(software_cycles={})).start()
        patch("audit_refill_overlap_probe.check_traces", return_value={}).start()

    def write(self, name, value):
        (self.root / name).write_text(json.dumps(value))

    def seal(self):
        self.write("artifact-hashes.json", hashes(p for p in self.root.rglob("*")
            if p.is_file() and p.name != "artifact-hashes.json"))

    def test_accepts_complete_receipt(self):
        self.assertEqual(audit(self.root)["state"], "PASS")

    def test_rejects_running(self):
        self.write("status.json", {**self.state, "child_pid": 1})
        self.seal()
        with self.assertRaises(ValueError):
            audit(self.root)

    def test_rejects_artifact_drift(self):
        (self.root / "work/run.vcs.log").write_text("changed")
        with self.assertRaises(ValueError):
            audit(self.root)

    def test_rejects_false_result(self):
        self.write("result.json", dict(state="PASS", software_cycles={"changed": 1}, trace={}))
        self.seal()
        with self.assertRaises(ValueError):
            audit(self.root)

    def test_rejects_pending_transactions(self):
        self.uvm["axi_read_counts"]["pending"] = 1
        self.write("uvm_result.json", self.uvm)
        self.seal()
        with self.assertRaises(ValueError):
            audit(self.root)

    def test_rejects_protocol_input_mismatch(self):
        self.uvm["elf_sha256"] = "wrong"
        self.write("uvm_result.json", self.uvm)
        self.seal()
        with self.assertRaises(ValueError):
            audit(self.root)


if __name__ == "__main__":
    unittest.main()
