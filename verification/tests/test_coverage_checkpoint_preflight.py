"""Checkpoint preflight and failure tests; no build or simulation is invoked."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_coverage_checkpoint as checkpoint


class CheckpointPreflightTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / "verification/out/checkpoint"
        self.output.mkdir(parents=True)
        self.patch("ROOT", self.root)
        self.spike = self.file("spike", executable=True)
        self.patch("SPIKE", self.spike)
        self.run = self.patch("run")
        # Any unexpected direct external command must fail the test.
        process = patch.object(checkpoint.subprocess, "run",
                               side_effect=AssertionError("unexpected external command"))
        process.start()
        self.addCleanup(process.stop)
        self.simdir = "verification/out/merged-store-fp16-image-20260926-01/sim"
        self.simv = self.image(self.simdir + "/simv")
        self.file(self.simdir + "/vcs_source_manifest.json", "{}")
        self.file(self.simdir + "/simulator.conf", "qbs=1")
        self.generator = self.image(
            "verification/out/integrated-random-short-control-preflight-20260925-01/vcs_simv")
        self.file("verification/riscv_dv/testlist.yaml", "testlist")
        self.elfs = []
        for suffix in ("arithmetic10-replay-20260925-02", "loadstore10-replay-20260925-01",
                       "fp32-10-replay-20260925-01", "fp64-10-replay-20260925-01",
                       "vtype10-replay-20260925-01"):
            base = "verification/out/integrated-wred-m8-" + suffix
            elf = self.file(base + "/tests/case/input.elf", "ELF")
            self.elfs.append(elf)
            self.file(base + "/summary.json", json.dumps([
                {"name": "case", "seed": 1, "status": "PASS", "elf": str(elf)}]))
        for name in ("villegal_vstart_ops", "vmask_dest_overlap_illegal",
                     "vregister_group_illegal", "vwiden_overlap_edges", "vnclip_edges"):
            self.elfs.append(self.file("apps/bin/rv64uv-ara-" + name, "ELF"))
        checkpoint.prepare(self.output)
        self.run.reset_mock()

    def patch(self, name, *args, **kwargs):
        item = patch.object(checkpoint, name, *args, **kwargs)
        result = item.start()
        self.addCleanup(item.stop)
        return result

    def file(self, name, content="fixture", executable=False):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        if executable:
            path.chmod(0o755)
        return path

    def image(self, name):
        path = self.file(name, executable=True)
        self.file(name + ".daidir/design.so", "design")
        return path

    def state(self):
        return json.loads((self.output / "checkpoint.json").read_text())

    def test_plan_counts_workers_and_seed_flags_unchanged(self):
        self.assertEqual(self.state()["functional_cases"], 30)
        self.assertEqual(len(self.state()["coverage_cases"]), 14)
        functional = json.loads((self.output / "functional-plan.json").read_text())
        coverage = json.loads((self.output / "coverage-plan.json").read_text())
        self.assertEqual(len(functional), 31)
        self.assertEqual(len(coverage), 14)
        for seed in range(501, 511):
            for kind in ("control", "memory"):
                steps = json.loads((self.output / "steps" / f"short-{kind}-{seed}.json").read_text())
                command = steps[1]
                self.assertEqual(command[command.index("--iterations") + 1], "1")
                self.assertEqual(command[command.index("--seed") + 1], str(seed))
                for flag in ("--vector-signature", "--defined-scalar-sources",
                             "--vector-commit-compare"):
                    self.assertIn(flag, command)
        checkpoint.check_inputs(self.output)

    def test_actual_systemd_properties_required(self):
        good = {"KillMode": "control-group", "Restart": "no", "RemainAfterExit": "no",
                "MainPID": str(os.getpid()), "InvocationID": "invocation"}
        with patch.dict(os.environ, {"ARA_CHECKPOINT_UNIT": "test.service",
                                     "INVOCATION_ID": "invocation"}, clear=True):
            for key, bad in ((None, None), ("KillMode", "process"), ("Restart", "always"),
                             ("RemainAfterExit", "yes"), ("MainPID", "0"),
                             ("InvocationID", "other"), ("KillMode", None)):
                values = dict(good)
                if key:
                    values[key] = bad
                response = subprocess.CompletedProcess([], 0, stdout="\n".join(
                    f"{name}={value}" for name, value in values.items() if value is not None))
                with self.subTest(key=key, bad=bad), patch.object(
                        checkpoint.subprocess, "run", return_value=response) as show:
                    if key:
                        with self.assertRaises(RuntimeError):
                            checkpoint.check_service()
                    else:
                        checkpoint.check_service()
                        self.assertEqual(show.call_args.args[0][:4],
                                         ["systemctl", "--user", "show", "test.service"])
                        self.assertEqual(show.call_args.kwargs["timeout"], 10)

    def test_missing_service_identity_and_query_failure_stop_before_dispatch(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                checkpoint.execute(self.output)
        self.assertEqual(self.state()["status"], "STOPPED")
        self.assertEqual(self.state()["phase"], "preflight")
        self.run.assert_not_called()
        with patch.dict(os.environ, {"ARA_CHECKPOINT_UNIT": "test.service",
                                     "INVOCATION_ID": "invocation"}, clear=True), patch.object(
                checkpoint.subprocess, "run", side_effect=subprocess.TimeoutExpired("systemctl", 10)):
            with self.assertRaises(subprocess.TimeoutExpired):
                checkpoint.check_service()

    def test_output_rejects_outside_root_and_symlink_escape(self):
        outside = self.root / "elsewhere"
        outside.mkdir()
        link = self.root / "verification/out/escape"
        link.symlink_to(outside, target_is_directory=True)
        for path in (outside / "job", link / "job", self.root / "verification/out"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                checkpoint.checked_output(path)
        self.assertEqual(checkpoint.checked_output(self.output), self.output)

    def test_changed_prepared_inputs_are_rejected(self):
        paths = [self.simv, Path(str(self.simv) + ".daidir/design.so"), self.generator,
                 Path(str(self.generator) + ".daidir/design.so"), self.spike, *self.elfs,
                 self.output / "functional-plan.json", self.output / "coverage-plan.json",
                 self.output / "steps/short-control-501.json",
                 self.root / self.simdir / "vcs_source_manifest.json"]
        for path in paths:
            original = path.read_bytes()
            try:
                path.write_bytes(b"changed")
                with self.subTest(path=path), self.assertRaises(RuntimeError):
                    checkpoint.check_inputs(self.output)
            finally:
                path.write_bytes(original)
        added = self.file(str(self.simv.relative_to(self.root)) + ".daidir/new.so")
        with self.assertRaises(RuntimeError):
            checkpoint.check_inputs(self.output)
        added.unlink()
        self.elfs[0].unlink()
        with self.assertRaises(FileNotFoundError):
            checkpoint.check_inputs(self.output)

    def test_changed_plan_stops_before_any_command(self):
        (self.output / "functional-plan.json").write_text("[]")
        self.patch("check_service")
        with self.assertRaisesRegex(RuntimeError, "prepared input changed"):
            checkpoint.execute(self.output)
        self.assertEqual(self.state()["status"], "STOPPED")
        self.run.assert_not_called()

    def test_prepare_failure_records_stopped_without_execution(self):
        output = self.root / "verification/out/failed-prepare"
        with patch.object(checkpoint, "prepare", side_effect=FileNotFoundError("missing ELF")), \
                patch.object(checkpoint, "execute") as execute, \
                patch.object(sys, "argv", ["checkpoint", "--output", str(output), "--prepare-only"]), \
                patch.dict(os.environ):
            with self.assertRaises(FileNotFoundError):
                checkpoint.main()
        record = json.loads((output / "checkpoint.json").read_text())
        self.assertEqual(record["status"], "STOPPED")
        self.assertEqual(record["phase"], "prepare")
        self.assertIn("missing ELF", record["reason"])
        execute.assert_not_called()

    def test_child_rechecks_steps_before_running_commands(self):
        steps = self.output / "steps/short-control-501.json"
        steps.write_text("[]")
        with patch.object(sys, "argv", ["checkpoint", "--steps", str(steps)]), \
                patch.dict(os.environ):
            with self.assertRaisesRegex(RuntimeError, "prepared input changed"):
                checkpoint.main()
        self.run.assert_not_called()

    def fake_campaign(self, fail=None):
        calls = []

        def run(command):
            calls.append(command)
            stage = ("functional" if "5" in command else "coverage") if \
                "verification/run_failfast_checkpoint.py" in command else Path(command[1]).stem
            if stage == fail:
                raise subprocess.CalledProcessError(1, command)
            if stage == "functional":
                image = Path(self.state()["coverage_image"])
                image.parent.mkdir(parents=True, exist_ok=True)
                image.write_text("coverage image")
            if stage == "coverage":
                for name in self.state()["coverage_cases"]:
                    checkpoint.save(self.output / "coverage" / name / "case_replay.json",
                                    {"cases": [{"result": str(self.output / name / "result.json")}]})
        self.run.side_effect = run
        return calls

    def test_success_order_and_worker_limits(self):
        self.patch("check_service")
        calls = self.fake_campaign()
        checkpoint.execute(self.output)
        self.assertEqual(self.state()["status"], "PASS")
        self.assertEqual(len(calls), 5)
        self.assertEqual(calls[0][calls[0].index("--jobs") + 1], "5")
        self.assertEqual(calls[1][calls[1].index("--jobs") + 1], "3")
        checkpoint.check_coverage_image(self.output)
        Path(self.state()["coverage_image"]).write_text("replaced")
        with self.assertRaisesRegex(RuntimeError, "coverage image changed"):
            checkpoint.check_coverage_image(self.output)

    def test_failures_are_durable_and_never_continue(self):
        self.patch("check_service")
        original = self.state()
        for index, (failure, phase) in enumerate((
                ("functional", "functional"), ("coverage", "coverage"),
                ("merge_verilator_coverage", "merge"), ("audit_merged", "audit"),
                ("review_uncovered", "review"))):
            checkpoint.save(self.output / "checkpoint.json", original)
            calls = self.fake_campaign(failure)
            with self.subTest(failure=failure), self.assertRaises(subprocess.CalledProcessError):
                checkpoint.execute(self.output)
            self.assertEqual(len(calls), index + 1)
            self.assertEqual(self.state()["status"], "STOPPED")
            self.assertEqual(self.state()["phase"], phase)

    def test_missing_merge_inputs_stop_and_stopped_checkpoint_cannot_resume(self):
        self.patch("check_service")
        self.run.side_effect = None
        image = Path(self.state()["coverage_image"])
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_text("coverage image")
        with self.assertRaises(FileNotFoundError):
            checkpoint.execute(self.output)
        self.assertEqual(self.state()["status"], "STOPPED")
        self.assertEqual(self.state()["phase"], "merge")
        self.run.reset_mock()
        with self.assertRaises(RuntimeError):
            checkpoint.execute(self.output)
        self.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
