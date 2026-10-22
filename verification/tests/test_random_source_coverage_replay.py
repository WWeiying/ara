import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "coverage"))
from audit_random_source_coverage import audit  # noqa: E402


class RandomSourceCoverageReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.source_run = root / "original"
        self.replay_run = root / "replay"
        self.plan = root / "plan.json"
        name = "sample"
        for directory in (self.source_run, self.replay_run):
            (directory / "tests" / name).mkdir(parents=True)
            (directory / "tests" / name / "input.elf").write_bytes(b"frozen ELF")
        (self.source_run / "asm_test").mkdir()
        (self.source_run / "asm_test" / f"{name}.S").write_text(
            "main:\nvsetvli zero, zero, e8, m1, ta, ma\n"
            "vadd.vv v1, v2, v3\ntest_done:\n")
        (self.replay_run / "summary.json").write_text(json.dumps([
            {"name": name, "status": "PASS"}]))
        (self.replay_run / "tests" / name / "result.json").write_text(json.dumps({
            "status": "PASS", "comparison": {"status": "TERMINAL_MATCH"},
            "trace": {"status": "VALID"}, "vector_commit": {"status": "PASS"},
        }))
        (self.replay_run / "independent_audit.json").write_text(
            json.dumps({"status": "PASS"}))
        (self.replay_run / "replay_manifest.json").write_text(json.dumps([{
            "name": name, "elf": str(self.source_run / "tests" / name / "input.elf"),
        }]))
        self.plan.write_text(json.dumps({"coverage_dimensions": {
            "sew": ["e8"], "lmul": ["m1"], "tail_policy": ["ta"],
            "mask_policy": ["ma"], "memory_mode": [],
        }}))

    def test_accepts_strict_replay_with_identical_frozen_elf(self):
        report = audit([self.replay_run], self.plan, [self.source_run])
        self.assertEqual(report["accepted_count"], 1)
        self.assertEqual(report["rejected_count"], 0)
        self.assertEqual(report["missing_planned_bins"]["tail_policy"], [])

    def test_rejects_replayed_elf_drift(self):
        (self.replay_run / "tests/sample/input.elf").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "replayed ELF differs"):
            audit([self.replay_run], self.plan, [self.source_run])


if __name__ == "__main__":
    unittest.main()
