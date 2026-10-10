import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from run_failfast_checkpoint import atomic_json, load_plan, run, stop_groups


class FailfastCheckpointTests(unittest.TestCase):
    def reaped_cleanup(self, active):
        return {"status": "DIRECT_CHILDREN_REAPED", "children": [
            {"index": index, "reaped": True, "returncode": -9}
            for index in active]}

    def job(self, root, name, code):
        return {"name": name, "command": [sys.executable, "-c", code], "cwd": str(root)}

    def plan(self, root, jobs):
        path = root / "plan.json"
        path.write_text(json.dumps(jobs, indent=3) + "\n")
        return path

    def test_success_preserves_plan_and_separate_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self.plan(root, [self.job(root, str(i), f"print('job{i}')") for i in range(7)])
            output = root / "out"
            self.assertEqual(run(plan, output, jobs=2), 0)
            self.assertEqual((output / "plan.json").read_bytes(), plan.read_bytes())
            state = json.loads((output / "status.json").read_text())
            self.assertEqual(state["status"], "PASS")
            self.assertEqual(len(state["results"]), 7)
            for index, result in enumerate(state["results"]):
                self.assertEqual(result["status"], "PASS")
                self.assertEqual(Path(result["stdout"]).read_text(), f"job{index}\n")
            self.assertFalse((output / "STOP.json").exists())
            self.assertFalse(list(output.glob("*.tmp")))

    def test_failure_stops_dispatch_and_kills_term_ignoring_sibling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sleeper = self.job(root, "sleeper", "import signal,time,pathlib; "
                               "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                               "pathlib.Path('ready').touch(); time.sleep(30)")
            failure = self.job(root, "failure", "import pathlib,time,sys\n"
                               "for _ in range(500):\n"
                               " if pathlib.Path('ready').exists(): break\n"
                               " time.sleep(.01)\n"
                               "print('first failure', flush=True)\nsys.exit(7)")
            pending = self.job(root, "pending", "from pathlib import Path; Path('BAD').touch()")
            plan = self.plan(root, [sleeper, failure, pending])
            output = root / "out"
            started = time.monotonic()
            self.assertEqual(run(plan, output, jobs=2), 1)
            self.assertLess(time.monotonic() - started, 8)
            state = json.loads((output / "status.json").read_text())
            self.assertEqual([row["status"] for row in state["results"]],
                             ["CANCELLED", "FAIL", "CANCELLED"])
            stop = json.loads((output / "STOP.json").read_text())
            self.assertEqual(stop["failure"]["name"], "failure")
            self.assertEqual(stop["failure"]["returncode"], 7)
            self.assertIn("first failure", Path(stop["failure"]["stdout"]).read_text())
            self.assertFalse((root / "BAD").exists())
            self.assertEqual(stop["cleanup"]["status"], "DIRECT_CHILDREN_REAPED")
            self.assertTrue(state["results"][0]["termination"]["reaped"])
            self.assertEqual(state["results"][0]["termination"]["returncode"], -signal.SIGKILL)
            # kill(pid, 0) is not a reliable liveness probe in the command
            # execution environment. Check wait() evidence and /proc instead.
            self.assertEqual(state["results"][0]["termination"]["after"], {"State": "absent"})
            self.assertFalse(Path(f"/proc/{state['results'][0]['pid']}").exists())

    def test_spawn_error_stops_without_overwriting_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self.plan(root, [{"name": "missing", "cwd": str(root),
                                     "command": [str(root / "does-not-exist")]}])
            output = root / "out"
            self.assertEqual(run(plan, output), 1)
            stop = json.loads((output / "STOP.json").read_text())
            self.assertEqual(stop["failure"]["status"], "ERROR")
            original = (output / "STOP.json").read_bytes()
            with self.assertRaises(FileExistsError):
                run(plan, output)
            self.assertEqual((output / "STOP.json").read_bytes(), original)

    def test_completed_success_and_failure_do_not_refill_slots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self.plan(root, [self.job(root, str(i), "pass") for i in range(3)])
            children = []

            def spawn(*args, **kwargs):
                index = len(children)
                child = Mock(pid=100 + index)
                child.poll.side_effect = lambda: None if len(children) < 2 else (0 if index == 0 else 9)
                children.append(child)
                return child

            with patch("run_failfast_checkpoint.subprocess.Popen", side_effect=spawn) as popen, \
                 patch("run_failfast_checkpoint.stop_groups", side_effect=self.reaped_cleanup):
                self.assertEqual(run(plan, root / "out", jobs=2), 1)
            self.assertEqual(popen.call_count, 2)
            state = json.loads((root / "out/status.json").read_text())
            self.assertEqual([row["status"] for row in state["results"]],
                             ["PASS", "FAIL", "CANCELLED"])

    def test_idle_polls_do_not_publish_and_terminal_status_is_preserved(self):
        for rc in (0, 7):
            with self.subTest(returncode=rc), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                plan = self.plan(root, [self.job(root, "worker", "pass")])
                child = Mock(pid=100)
                child.poll.side_effect = [None] * 20 + [rc]
                with patch("run_failfast_checkpoint.subprocess.Popen", return_value=child), \
                     patch("run_failfast_checkpoint.stop_groups", side_effect=self.reaped_cleanup), \
                     patch("run_failfast_checkpoint.atomic_json", wraps=atomic_json) as publish, \
                     patch("run_failfast_checkpoint.time.sleep") as sleep:
                    sleep.side_effect = lambda _: self.assertEqual(publish.call_count, 2)
                    self.assertEqual(run(plan, root / "out"), 0 if rc == 0 else 1)
                    self.assertEqual(sleep.call_count, 20)
                    self.assertEqual(publish.call_count, 4 if rc == 0 else 6)
                state = json.loads((root / "out/status.json").read_text())
                self.assertEqual(state["status"], "PASS" if rc == 0 else "FAIL")
                self.assertEqual((root / "out/STOP.json").exists(), rc != 0)

    def test_reaping_timeout_is_recorded_not_silenced(self):
        child = Mock(pid=1234)
        child.wait.side_effect = subprocess.TimeoutExpired("mock-child", 3)
        with patch("run_failfast_checkpoint.os.killpg") as kill, \
             patch("run_failfast_checkpoint.process_state", return_value={"State": "D"}), \
             patch("run_failfast_checkpoint.time.monotonic", side_effect=[0, 1, 1, 5]):
            result = stop_groups({2: child})
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertFalse(result["children"][0]["reaped"])
        self.assertEqual(result["children"][0]["after"]["State"], "D")
        self.assertEqual(kill.call_count, 2)
        child.wait.assert_called_once_with(timeout=0.0)

    def test_unconfirmed_termination_is_not_reported_as_cancelled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self.plan(root, [self.job(root, "live", "pass"),
                                    self.job(root, "failed", "pass")])
            children = []

            def spawn(*args, **kwargs):
                index = len(children)
                child = Mock(pid=100 + index)
                child.poll.side_effect = lambda: 7 if index == 1 else None
                children.append(child)
                return child

            cleanup = {"status": "INCOMPLETE", "children": [
                {"index": 0, "reaped": False, "returncode": None},
                {"index": 1, "reaped": True, "returncode": 7}]}
            with patch("run_failfast_checkpoint.subprocess.Popen", side_effect=spawn), \
                 patch("run_failfast_checkpoint.stop_groups", return_value=cleanup):
                self.assertEqual(run(plan, root / "out", jobs=2), 1)
            state = json.loads((root / "out/status.json").read_text())
            self.assertEqual(state["results"][0]["status"], "TERMINATION_PENDING")
            self.assertEqual(state["results"][1]["status"], "FAIL")

    def test_rejects_empty_duplicate_shell_string_and_invalid_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = self.job(root, "name", "pass")
            for jobs in ([], [item, item], [{**item, "command": "echo unsafe"}]):
                with self.subTest(plan=jobs):
                    with self.assertRaises(ValueError):
                        load_plan(self.plan(root, jobs))
            plan = self.plan(root, [item])
            for jobs in (0, 6):
                with self.assertRaises(ValueError):
                    run(plan, root / "out", jobs)
            self.assertFalse((root / "out").exists())

    def test_sigterm_cancels_and_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = self.plan(root, [self.job(root, "sleep", "import time; time.sleep(30)")])
            output = root / "out"
            script = Path(__file__).resolve().parents[1] / "run_failfast_checkpoint.py"
            process = subprocess.Popen([sys.executable, str(script), "--plan", str(plan),
                                        "--output", str(output)], start_new_session=True)
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if (output / "status.json").exists():
                        state = json.loads((output / "status.json").read_text())
                        if state["results"][0]["status"] == "RUNNING":
                            break
                    time.sleep(.01)
                else:
                    self.fail("supervisor did not start host child")
                process.send_signal(signal.SIGTERM)
                self.assertEqual(process.wait(timeout=5), 1)
                state = json.loads((output / "status.json").read_text())
                self.assertEqual(state["status"], "CANCELLED")
                self.assertEqual(state["results"][0]["status"], "CANCELLED")
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()


if __name__ == "__main__":
    unittest.main()
