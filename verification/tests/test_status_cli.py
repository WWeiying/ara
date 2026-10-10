import importlib.util
from pathlib import Path
import unittest
import json
import tempfile
import io
from contextlib import redirect_stdout
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("campaign_status", Path(__file__).parents[1] / "status.py")
status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)


class StatusTest(unittest.TestCase):
    def test_running_cases_are_not_completed(self):
        state = {"status": "RUNNING", "total": 2, "cases": {
            "live": {"status": "RUNNING"}, "done": {"status": "PASS"}}}
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(status, "load_run", return_value=(Path(directory), state, [])), \
                    patch.object(status, "service_state", return_value={"ActiveState": "active"}), \
                    redirect_stdout(output):
                status.show({"name": "batch", "service": "test.service"}, detailed=True)
        self.assertIn("1/2 completed", output.getvalue())
        self.assertIn("live", output.getvalue())
        self.assertNotIn("No scheduler results", output.getvalue())

    def test_reused_results_in_batch_total(self):
        state = {"status": "RUNNING", "total": 3, "cases": {
            "old": {"status": "RTL_STALL", "reused": True},
            "new": {"status": "PASS"}}}
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with patch.object(status, "load_run", return_value=(Path(directory), state, [])), \
                    patch.object(status, "service_state", return_value={"ActiveState": "active"}), \
                    redirect_stdout(output):
                status.show({"name": "batch", "service": "test.service"}, detailed=True)
            self.assertIn("2/3 completed | reused=1", output.getvalue())
            self.assertIn("PASS=1, RTL_STALL=1", output.getvalue())
            self.assertIn("old (reused)", output.getvalue())

    def test_running(self):
        self.assertEqual(status.verdict("RUNNING", {"ActiveState": "active"}), "RUNNING")

    def test_preparing_service_is_not_pass(self):
        self.assertEqual(status.verdict(None, {"ActiveState": "active"}),
                         "RUNNING (preparing; no result yet)")
        self.assertIn("UNKNOWN", status.verdict(None, {"ActiveState": "inactive"}))

    def test_coverage_completion_display(self):
        output = io.StringIO()
        state = dict(status="PASS", coverage_status="COMPLETE", aggregate_passed=654)
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(status, "load_run", return_value=(Path(directory), state, [])), \
                    patch.object(status, "service_state", return_value={"ActiveState": "inactive"}), \
                    redirect_stdout(output):
                status.show(dict(name="batch", service="test.service"))
        self.assertIn("coverage: COMPLETE | completed aggregate PASS: 654", output.getvalue())

    def test_stale_is_not_running(self):
        self.assertIn("STALE", status.verdict("RUNNING", {"ActiveState": "failed"}))

    def test_service_unknown_not_assumed_dead(self):
        self.assertIn("UNKNOWN", status.verdict("RUNNING", {}))

    def test_pass(self):
        self.assertEqual(status.verdict("PASS", {"ActiveState": "inactive"}), "PASS")

    def test_conflict(self):
        self.assertIn("CONFLICT", status.verdict("PASS", {"ActiveState": "failed"}))

    def test_stopped(self):
        self.assertEqual(status.verdict("STOPPED", {"ActiveState": "failed"}), "STOPPED")

    def test_building_is_live(self):
        self.assertEqual(status.verdict("BUILDING", {"ActiveState": "active"}), "RUNNING")

    def test_exploration_failure_not_scheduler_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "out/batch"
            (run / "functional-scheduler").mkdir(parents=True)
            (run / "checkpoint.json").write_text(json.dumps({
                "cases": {"one": {"status": "RTL_STALL"}}}))
            (run / "functional-scheduler/status.json").write_text(json.dumps({
                "results": [{"name": "one", "status": "PASS"}]}))
            with patch.object(status, "HERE", root):
                _, _, stages = status.load_run({"directory": "batch"})
            self.assertEqual(stages[0][1][0]["status"], "RTL_STALL")
