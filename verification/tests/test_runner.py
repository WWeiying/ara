import json
import tempfile
import unittest
from pathlib import Path

from ara_verify.model import TestResult
from ara_verify.runner import (
    FAIL_RE,
    SUCCESS_RE,
    RegressionRunner,
    RunOptions,
    _invalidate_reports,
    _safe_name,
)
from verify import _parser


class ResultParsingTests(unittest.TestCase):
    def test_success_marker(self):
        self.assertIsNotNone(SUCCESS_RE.search("Core Test *** SUCCESS *** (tohost = 0)"))

    def test_failure_markers(self):
        for text in (
            "Core Test *** FAILED ***",
            "UVM_FATAL",
            "Error: assertion foo failed",
            "Index 0 FAILED. Got 0, expected 1.",
            "FAILED.",
        ):
            self.assertIsNotNone(FAIL_RE.search(text))

    def test_vcs_warning_assertion_is_not_a_fatal_failure(self):
        warning = (
            "gen_assertion[1].a_invalid_read_data: started at 10fs failed at 10fs\n"
            "Warning: reading invalid data"
        )
        self.assertIsNone(FAIL_RE.search(warning))

    def test_safe_name(self):
        self.assertEqual(_safe_name("rvv:vadd/test"), "rvv_vadd_test")

    def test_run_timeout_override(self):
        args = _parser().parse_args(["run", "rvv-directed", "--timeout", "900"])

        self.assertEqual(args.timeout, 900)

    def test_new_run_invalidates_stale_reports_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            for filename in ("summary.json", "summary.csv", "junit.xml"):
                (output / filename).write_text("stale", encoding="utf-8")
            (output / "console.log").write_text("keep", encoding="utf-8")

            _invalidate_reports(output)

            for filename in ("summary.json", "summary.csv", "junit.xml"):
                self.assertFalse((output / filename).exists())
            self.assertEqual((output / "console.log").read_text(), "keep")

    def test_report_completion_updates_run_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            options = RunOptions(
                repo_root=output,
                output_root=output,
                config="default",
                jobs=1,
                seed=1,
                dry_run=False,
                build_only=False,
                skip_build=True,
                simv=None,
                commit_trace=False,
                timeout_s=None,
            )
            runner = RegressionRunner(options, [], ["verify.py", "run"])
            runner.prepare()
            self.assertEqual(json.loads((output / "run.json").read_text())["status"], "RUNNING")

            runner._write_reports([
                TestResult("rvv:test", "rvv", "PASS", 0, 1.0, "", output / "case")
            ])

            metadata = json.loads((output / "run.json").read_text())
            self.assertEqual(metadata["status"], "COMPLETE")
            self.assertEqual(metadata["status_counts"], {"PASS": 1})
            self.assertIn("completed_at", metadata)
