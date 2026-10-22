"""Offline scheduler regressions recovered from the older verification tree."""

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "qbs"))
from rerun_paired_campaign import digest, run


class QbsPairedSchedulerTests(unittest.TestCase):
    def simulated_plan(self, root, modes):
        simv = root / "sim/simv"
        simv.parent.mkdir()
        simv.write_bytes(b"simv")
        config = simv.parent / "simulator.conf"
        config.write_text("qbs=1\nakv_v2=1\n")
        runner = root / "runner.sh"
        runner.write_text("runner\n")
        cases = []
        pairs = []
        for index, mode in enumerate(modes):
            elf = root / f"input-{index}.elf"
            elf.write_bytes(f"elf-{index}".encode())
            app = root / f"app-{index}"
            app.mkdir()
            (app / "case.json").write_text("{}\n")
            destination = root / "output" / f"case-{index}" / mode
            cases.append({"name": f"case-{index}", "mode": mode,
                          "elf": str(elf), "elf_sha256": digest(elf),
                          "app": str(app),
                          "app_inputs_sha256": {str(app / "case.json"):
                                                digest(app / "case.json")},
                          "output": str(destination), "testcase": f"case-{index}"})
            pairs.append({f"{mode}_run": str(destination)})
        plan = {"status": "PLANNED", "simv_sha256": digest(simv),
                "simulator_conf_sha256": digest(config),
                "runner_sha256": digest(runner), "cases": cases,
                "output_manifest": {"qbs_pairs": pairs, "akv_pair": {}}}
        output = root / "output"
        output.mkdir()
        return plan, output, simv, runner

    def test_parallel_is_bounded_and_runs_evidence_and_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            plan, output, simv, runner = self.simulated_plan(
                Path(directory), ("rvv", "qbs", "rvv", "qbs"))
            lock = threading.Lock()
            active = 0
            peak = 0
            commands = []
            started = threading.Barrier(2)

            def fake_run(command, **kwargs):
                nonlocal active, peak
                with lock:
                    commands.append(command)
                    if command[0] == str(runner):
                        active += 1
                        peak = max(peak, active)
                if command[0] == str(runner):
                    started.wait(timeout=2)
                    Path(command[-1]).mkdir(parents=True)
                    with lock:
                        active -= 1
                return SimpleNamespace(returncode=0)

            with patch("rerun_paired_campaign.RUNNER", runner), patch(
                    "rerun_paired_campaign.subprocess.run", side_effect=fake_run):
                self.assertEqual(run(plan, output, simv, 9, jobs=2), 0)
            self.assertEqual(peak, 2)
            self.assertEqual(sum(cmd[0] == str(runner) for cmd in commands), 4)
            self.assertEqual(sum("--case-json" in cmd for cmd in commands), 2)
            self.assertEqual(sum("--manifest" in cmd for cmd in commands), 1)
            self.assertEqual(len({case["log"] for case in plan["cases"]}), 4)
            self.assertTrue(all(case["status"] == "PASS" for case in plan["cases"]))
            self.assertEqual(json.loads((output / "plan.json").read_text())["status"],
                             "PASS")

    def test_failure_drains_started_cases_and_resume_skips_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            plan, output, simv, runner = self.simulated_plan(
                Path(directory), ("rvv", "rvv", "rvv"))
            started = threading.Barrier(2)
            calls = []

            def first_run(command, **kwargs):
                calls.append(command)
                if command[0] == str(runner):
                    started.wait(timeout=2)
                    if command[3] == "case-1":
                        time.sleep(0.05)
                    Path(command[-1]).mkdir(parents=True)
                    return SimpleNamespace(returncode=1 if command[3] == "case-0" else 0)
                return SimpleNamespace(returncode=0)

            with patch("rerun_paired_campaign.RUNNER", runner), patch(
                    "rerun_paired_campaign.subprocess.run", side_effect=first_run):
                self.assertEqual(run(plan, output, simv, 9, jobs=2), 1)
            self.assertEqual([case.get("status") for case in plan["cases"]],
                             ["FAIL", "PASS", None])
            self.assertFalse(any("--manifest" in cmd for cmd in calls))
            self.assertEqual(len(calls), 2)

            resume_calls = []

            def resumed_run(command, **kwargs):
                resume_calls.append(command)
                if command[0] == str(runner):
                    Path(command[-1]).mkdir(parents=True)
                return SimpleNamespace(returncode=0)

            with patch("rerun_paired_campaign.RUNNER", runner), patch(
                    "rerun_paired_campaign.subprocess.run", side_effect=resumed_run):
                self.assertEqual(run(plan, output, simv, 9, jobs=2), 0)
            self.assertEqual(sum(cmd[0] == str(runner) for cmd in resume_calls), 2)
            self.assertFalse(any(cmd[3] == "case-1" for cmd in resume_calls
                                 if cmd[0] == str(runner)))
            self.assertEqual(plan["cases"][0]["attempts"][0]["status"], "FAIL")
            self.assertTrue(plan["cases"][0]["output"].endswith("rvv.retry-1"))
            self.assertEqual(plan["status"], "PASS")

    def test_parallel_hash_change_prevents_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            plan, output, simv, runner = self.simulated_plan(Path(directory), ("rvv",))
            Path(plan["cases"][0]["elf"]).write_bytes(b"changed")
            with patch("rerun_paired_campaign.RUNNER", runner), patch(
                    "rerun_paired_campaign.subprocess.run") as process:
                self.assertEqual(run(plan, output, simv, 9, jobs=2), 1)
            process.assert_not_called()
            self.assertEqual(plan["cases"][0]["reason"],
                             "frozen input or runner hash changed")

    def test_evidence_failure_is_recorded_and_blocks_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            plan, output, simv, runner = self.simulated_plan(Path(directory), ("qbs",))
            commands = []

            def fake_run(command, **kwargs):
                commands.append(command)
                if command[0] == str(runner):
                    Path(command[-1]).mkdir(parents=True)
                return SimpleNamespace(returncode=3 if "--case-json" in command else 0)

            with patch("rerun_paired_campaign.RUNNER", runner), patch(
                    "rerun_paired_campaign.subprocess.run", side_effect=fake_run):
                self.assertEqual(run(plan, output, simv, 9, jobs=2), 1)
            self.assertEqual(plan["cases"][0]["returncode"], 0)
            self.assertEqual(plan["cases"][0]["evidence_returncode"], 3)
            self.assertEqual(plan["cases"][0]["status"], "FAIL")
            self.assertFalse(any("--manifest" in cmd for cmd in commands))


if __name__ == "__main__":
    unittest.main()
