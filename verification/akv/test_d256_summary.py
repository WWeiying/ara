import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import summarize_d256_efficiency as summary


class SummaryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.case = self.root / "case"
        self.case.mkdir()
        self.output = self.root / "summary"
        cohort = patch.object(summary, "COHORT", ("case",))
        cohort.start()
        self.addCleanup(cohort.stop)

    def test_pending_is_not_complete_or_pass(self):
        (self.case / "stage.json").write_text('{"status":"RUNNING"}')
        summary.archive(self.root, self.output)
        result = json.loads((self.output / "summary.json").read_text())
        self.assertFalse(result["complete"])
        self.assertFalse(result["all_pass"])

    def test_finished_failure_is_preserved(self):
        (self.case / "stage.json").write_text('{"status":"FAIL","mode":"akv_v2"}')
        run = self.case / "decode_attention_core_test"
        run.mkdir()
        (run / "ara.log").write_text(
            "LLAMA_OPERATOR operator/decode/attention_core/akv_v2 FAIL cycles=99 mismatches=18\n")
        summary.archive(self.root, self.output)
        result = json.loads((self.output / "summary.json").read_text())
        self.assertTrue(result["complete"])
        self.assertFalse(result["all_pass"])
        self.assertIn("case,FAIL,99,18,", (self.output / "performance.csv").read_text())

    def test_missing_evidence_cannot_pass(self):
        (self.case / "stage.json").write_text('{"status":"PASS"}')
        with self.assertRaises(RuntimeError):
            summary.archive(self.root, self.output)


if __name__ == "__main__":
    unittest.main()
