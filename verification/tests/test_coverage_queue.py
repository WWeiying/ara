import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location("coverage_queue", Path(__file__).parents[1] / "coverage/queue_batch_coverage.py")
queue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(queue)


class QueueTest(unittest.TestCase):
    def check(self, recorded, active):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text(json.dumps({"status": recorded}))
            with patch.object(queue.subprocess, "run", return_value=SimpleNamespace(
                    stdout=f"ActiveState={active}\nResult=success\n")):
                return queue.ready(path, "test.service", {"PASS", "COMPLETE_WITH_FAILURES"})

    def test_running_waits(self):
        self.assertFalse(self.check("RUNNING", "active"))

    def test_pass_but_service_still_running_waits(self):
        self.assertFalse(self.check("PASS", "active"))

    def test_finished_with_functional_failures_can_collect(self):
        self.assertTrue(self.check("COMPLETE_WITH_FAILURES", "inactive"))

    def test_dead_without_completion_rejected(self):
        with self.assertRaises(RuntimeError):
            self.check("RUNNING", "inactive")

    def test_failed_dependency_rejected(self):
        with self.assertRaises(RuntimeError):
            self.check("STOPPED", "failed")

    def test_pass_only_waits_for_build_and_passes_pinned_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch = root / "batch"
            batch.mkdir()
            output = root / "queue"
            snapshot = {"batch": str(batch), "batch_unit": "batch.service", "mode": "SOURCE_PASS_ONLY",
                        "selected_count": 233, "original_total": 248, "original_status": "STOPPED",
                        "complete_original_batch": False, "files": {}, "excluded": [{}] * 15}
            argv = ["queue", "--batch", str(batch), "--batch-unit", "batch.service",
                    "--image-dir", str(root / "image"), "--build-unit", "build.service",
                    "--queue-output", str(output), "--output", str(root / "replay"), "--source-pass-only"]
            with patch.object(sys, "argv", argv), patch.object(queue, "check_service"), \
                    patch.object(queue, "pass_source_snapshot", return_value=snapshot), \
                    patch.object(queue, "check_files"), patch.object(queue, "check_source_stopped"), \
                    patch.object(queue, "ready", side_effect=[False, True]) as ready, \
                    patch.object(queue.time, "sleep") as sleep, \
                    patch.object(queue.subprocess, "run") as run, patch.object(queue.os, "execv") as execute:
                queue.main()
            self.assertEqual(ready.call_count, 2)
            self.assertEqual(ready.call_args.args[1], "build.service")
            sleep.assert_called_once_with(30)
            command = run.call_args.args[0]
            self.assertIn("--source-pass-only", command)
            self.assertIn("--source-snapshot", command)
            self.assertEqual(execute.call_args.args[1][-2:], ["--jobs", "3"])
            state = json.loads((output / "checkpoint.json").read_text())
            self.assertEqual(state["status"], "HANDED_OFF")
            self.assertEqual(state["source_selection"]["selected_count"], 233)

    def test_pass_only_identity_failure_stops_before_build_or_prepare(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            argv = ["queue", "--batch", str(root), "--batch-unit", "batch.service",
                    "--image-dir", str(root), "--build-unit", "build.service",
                    "--queue-output", str(root / "queue"), "--output", str(root / "replay"),
                    "--source-pass-only"]
            with patch.object(sys, "argv", argv), patch.object(queue, "check_service"), \
                    patch.object(queue, "pass_source_snapshot", side_effect=RuntimeError("drift")), \
                    patch.object(queue, "ready") as ready, patch.object(queue.subprocess, "run") as run:
                with self.assertRaisesRegex(RuntimeError, "drift"):
                    queue.main()
                ready.assert_not_called()
                run.assert_not_called()
            self.assertEqual(json.loads((root / "queue/checkpoint.json").read_text())["status"], "STOPPED")
