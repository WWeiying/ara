import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("batch_summary", Path(__file__).parents[1] / "summarize_batch_exploration.py")
summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary)


class BatchSummaryTest(unittest.TestCase):
    def test_pending_and_failure_are_not_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = root / "case"
            case.mkdir()
            (case / "commit_comparison.json").write_text(json.dumps({
                "next_spike": {"instruction": "0x12345678", "pc": "0x80000000"}}))
            (case / "rtl.command.json").write_text(json.dumps({"command": ["simv"]}))
            (root / "plan.json").write_text(json.dumps({"cases": [
                {"name": "fail", "kind": "random"},
                {"name": "pending", "kind": "directed"}]}))
            (root / "checkpoint.json").write_text(json.dumps({"status": "RUNNING", "cases": {
                "fail": {"status": "RTL_STALL", "artifact_dir": str(case)}}}))
            result = summary.summarize(root)
            self.assertEqual(result["counts"], {"RTL_STALL": 1, "NOT_COMPLETED": 1})
            self.assertIn("RTL_STALL:0x12345678", result["failure_groups"])
            evidence = result["failure_groups"]["RTL_STALL:0x12345678"]["representatives"][0]
            self.assertEqual(evidence["evidence_files"]["rtl.command.json"]["path"],
                             str(case / "rtl.command.json"))
            self.assertEqual(len(evidence["evidence_files"]["rtl.command.json"]["sha256"]), 64)

    def test_representatives_limited_without_dropping_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [{"name": f"case{i}", "kind": "random"} for i in range(5)]
            (root / "plan.json").write_text(json.dumps({"cases": rows}))
            (root / "checkpoint.json").write_text(json.dumps({"status": "COMPLETE_WITH_FAILURES",
                "cases": {r["name"]: {"status": "RTL_STALL", "artifact_dir": str(root)}
                          for r in rows}}))
            group = summary.summarize(root)["failure_groups"]["RTL_STALL:unclassified"]
            self.assertEqual(group["count"], 5)
            self.assertEqual(len(group["cases"]), 5)
            self.assertEqual(len(group["representatives"]), 3)
