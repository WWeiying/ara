"""Host-only repair coverage policy/provenance tests; never invoke VCS or DVE."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "coverage"))
import run_repair_closure_coverage as runner


class RepairCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "new"
        self.output.mkdir()
        (self.output / "logs").mkdir()

    def spec(self, name="seed1401-original", kind="replay"):
        return {"name": name, "kind": kind, "case": "seed1401_original", "seed": 1401,
                "summary": "frozen.json", "elf": "frozen.elf", "coverage_test": name.replace("-", "_"),
                "timeout_s": 900 if kind == "axpy" else 300, "fault_vstart_probe": name in runner.PROBES}

    def build_state(self, **changes):
        state = {"LoadState": "loaded", "ActiveState": "inactive", "MainPID": "0", "Result": "success",
                 "ExecMainStatus": "0", "ExecMainCode": "1", "ExecMainStartTimestampMonotonic": "100"}
        state.update(changes)
        return subprocess.CompletedProcess([], 0, "\n".join(f"{k}={v}" for k, v in state.items()))

    def test_exact_twenty_one_selection(self):
        self.assertEqual(len(runner.FIRST), 16)
        self.assertEqual(len(runner.SECOND), 5)
        self.assertFalse(runner.FIRST & runner.SECOND)
        self.assertEqual(sum(n.endswith("-replacement") for n in runner.SECOND), 3)

    def test_compile_only_changes_three_options(self):
        command = ["make", "code_coverage=0", "buildpath=old/build", "sim_dir=old/sim",
                   "config=default", "verify_extra_sources=uvm.sv fault_probe.sv", "fail_on_assert=0"]
        with patch.object(runner, "read", return_value={"command": command}):
            result = runner.compile_command(self.output)
        self.assertEqual(result, [command[0], "code_coverage=1", f"buildpath={self.output}/build",
                                 f"sim_dir={self.output}/sim", *command[4:]])

    def test_duplicate_build_option_rejected(self):
        with patch.object(runner, "read", return_value={"command": ["code_coverage=0", "code_coverage=1"]}):
            with self.assertRaises(RuntimeError):
                runner.compile_command(self.output)

    def test_probe_is_explicit_only_two_originals(self):
        for name in runner.FIRST | runner.SECOND:
            command, audit = runner.commands(self.output, self.spec(name), {"spike": "spike"})
            self.assertEqual("--fault-vstart-probe" in command, name in runner.PROBES)
            for flag in ("--require-trace", "--require-vector", "--require-full-match"):
                self.assertIn(flag, audit)
            self.assertNotIn("-cm", command)

    def test_replay_uses_private_wrapper_and_include_passed(self):
        command, _ = runner.commands(self.output, self.spec(), {"spike": "spike"})
        self.assertIn("--include-passed", command)
        self.assertEqual(command[command.index("--simv") + 1], str(self.output / "inputs/coverage_simv"))
        self.assertEqual(command[command.index("--spike-timeout") + 1], "60")

    def test_axpy_not_precreated_and_independent_audit(self):
        command, audit = runner.commands(self.output, self.spec("axpy", "axpy"), {"spike": "spike"})
        self.assertFalse((self.output / "results/axpy").exists())
        self.assertEqual(command[-1], str(self.output / "results/axpy"))
        self.assertIn("ara_verify.uvm_dut", audit)
        for flag in ("--require-events", "--require-backend", "--require-axi", "--require-axi-write"):
            self.assertIn(flag, audit)

    def test_directed_strict_trace_audit(self):
        command, audit = runner.commands(self.output, self.spec("vlsseg", "directed"), {})
        self.assertIn("--directed", command)
        self.assertIn("--require-trace", audit)
        self.assertNotIn("--require-vector", audit)

    def test_successful_build_must_be_quiescent(self):
        with patch.object(runner.subprocess, "run", return_value=self.build_state()), \
                patch.object(runner.base, "quiescent_build") as quiet:
            runner.wait_build("build.service", self.output)
        quiet.assert_called_once_with("build.service")

    def test_failed_missing_never_started_build_rejected(self):
        for changes in ({"ActiveState": "failed"}, {"ExecMainStatus": "1"}, {"Result": "timeout"},
                        {"LoadState": "not-found"}, {"ExecMainCode": "2"},
                        {"ExecMainStartTimestampMonotonic": "0"}, {"MainPID": "12"}):
            with self.subTest(changes=changes), \
                    patch.object(runner.subprocess, "run", return_value=self.build_state(**changes)):
                with self.assertRaises(RuntimeError):
                    runner.wait_build("build.service", self.output)

    def test_build_wait_bounded(self):
        with patch.object(runner.subprocess, "run", return_value=self.build_state(ActiveState="active")), \
                patch.object(runner.time, "monotonic", side_effect=[0, 2]):
            with self.assertRaisesRegex(RuntimeError, "exceeded bound"):
                runner.wait_build("build.service", self.output, 1)

    def test_build_wait_then_success(self):
        with patch.object(runner.subprocess, "run", side_effect=[self.build_state(ActiveState="active"),
                                                                self.build_state()]), \
                patch.object(runner.base, "quiescent_build"), patch.object(runner.time, "sleep") as sleep:
            runner.wait_build("build.service", self.output)
        sleep.assert_called_once()

    def test_explicit_adoption_accepts_gc_without_claiming_exit(self):
        with patch.object(runner.subprocess, "run", return_value=self.build_state(LoadState="not-found")), \
                patch.object(runner.base, "quiescent_build") as quiet:
            runner.wait_build("build.service", self.output, adopt_built=True)
        quiet.assert_called_once_with("build.service")
        self.assertEqual(runner.read(self.output / "build-service.json")["process_exit_evidence"],
                         "NOT_RETAINED_UNIT_GC")

    def test_adoption_does_not_allow_live_or_failed_unit(self):
        for changes in ({"LoadState": "not-found", "MainPID": "10"},
                        {"LoadState": "not-found", "ActiveState": "active"},
                        {"ActiveState": "failed", "ExecMainStatus": "1"}):
            with self.subTest(changes=changes), \
                    patch.object(runner.subprocess, "run", return_value=self.build_state(**changes)):
                with self.assertRaises(RuntimeError):
                    runner.wait_build("build.service", self.output, adopt_built=True)

    def test_worker_failure_not_admitted(self):
        with patch.object(runner, "frozen", side_effect=RuntimeError("source drift")):
            self.assertEqual(runner.worker(self.output, "seed1417"), 1)
        result = runner.read(self.output / "outcomes/seed1417.json")
        self.assertFalse(result["admitted"])
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("source drift", result["reason"])

    def test_scheduler_supports_eight_and_no_more(self):
        active, peak = [], [0]
        def spawn(*args, **kwargs):
            child = Mock(pid=123)
            child.poll.side_effect = lambda: 0 if len(active) >= 8 else None
            active.append(child)
            peak[0] = max(peak[0], len(active))
            self.assertTrue(kwargs["start_new_session"])
            return child
        with patch.object(runner.subprocess, "Popen", side_effect=spawn), patch.object(runner.time, "sleep"):
            runner.schedule(self.output, [f"job{i}" for i in range(8)], 8)
        self.assertEqual(peak[0], 8)
        rows = runner.read(self.output / "scheduler/status.json")["cases"]
        self.assertTrue(all(r["status"] == "PASS" for r in rows))
        with self.assertRaises(RuntimeError):
            runner.schedule(self.output, [], 9)

    def test_failfast_no_dispatch_after_observed_failure(self):
        child = Mock(pid=123)
        child.poll.return_value = 1
        with patch.object(runner.subprocess, "Popen", return_value=child) as spawn, \
                patch.object(runner, "stop_groups", return_value={}) as stop:
            with self.assertRaisesRegex(RuntimeError, "fail-fast"):
                runner.schedule(self.output, ["first", "second"], 8)
        self.assertEqual(spawn.call_count, 1)
        stop.assert_called_once()
        rows = runner.read(self.output / "scheduler/status.json")["cases"]
        self.assertEqual([r["status"] for r in rows], ["FAIL", "CANCELLED"])

    def test_merge_rejects_nonpass_without_dve(self):
        jobs = {f"job{i}": {} for i in range(21)}
        for name in jobs:
            runner.save(self.output / "outcomes" / (name + ".json"),
                        {"name": name, "status": "FAIL", "admitted": False})
        with patch.object(runner.coverage, "invoke") as invoke:
            with self.assertRaisesRegex(RuntimeError, "non-PASS"):
                runner.merge(self.output, {"jobs": jobs}, {"design_files": {}})
        invoke.assert_not_called()

    def test_merge_rejects_old_vdb_without_dve(self):
        jobs = {f"job{i}": {} for i in range(21)}
        for name in jobs:
            runner.save(self.output / "outcomes" / (name + ".json"),
                        {"name": name, "status": "PASS", "admitted": True, "vdb": "/old/code.vdb"})
        with patch.object(runner.coverage, "invoke") as invoke:
            with self.assertRaisesRegex(RuntimeError, "foreign/old"):
                runner.merge(self.output, {"jobs": jobs}, {"design_files": {}})
        invoke.assert_not_called()

    def test_prepare_rejects_existing_plan_before_writes(self):
        path = self.output / "plan.json"
        runner.save(path, {"sentinel": True})
        with self.assertRaises(RuntimeError):
            runner.prepare(self.output)
        self.assertEqual(runner.read(path), {"sentinel": True})

    def test_prepare_preserves_existing_build(self):
        (self.output / "build").mkdir()
        command = ["existing"]
        runner.save(self.output / "compile.command.json", {"command": command})
        with patch.object(runner.base, "sources", return_value={"files": []}), \
                patch.object(runner, "compile_command", return_value=command), \
                patch.object(runner, "selected_sources", side_effect=RuntimeError("selection boundary")):
            with self.assertRaisesRegex(RuntimeError, "selection boundary"):
                runner.prepare(self.output)
        self.assertEqual(runner.read(self.output / "compile.command.json"), {"command": command})
        self.assertTrue((self.output / "build").exists())

    def test_real_archived_selection_read_only(self):
        if not all((p / "checkpoint.json").exists() for p in runner.SOURCES):
            self.skipTest("archived repaired results not installed")
        jobs, files, spike = runner.selected_sources()
        self.assertEqual(set(jobs), runner.FIRST | runner.SECOND)
        self.assertEqual(sum(s["kind"] == "replay" for s in jobs.values()), 14)
        self.assertEqual(sum(s["kind"] == "directed" for s in jobs.values()), 6)
        self.assertEqual(sum(s["fault_vstart_probe"] for s in jobs.values()), 2)
        self.assertIn(spike, files)

    def test_use_built_waits_then_replays_without_compile(self):
        root = Path(self.temp.name) / "repo"
        (root / "verification/out").mkdir(parents=True)
        runner.save(self.output / "status.json", {"status": "PREPARED"})
        with patch.object(runner, "ROOT", root), patch.object(runner.base, "check_service"), \
                patch.object(runner, "frozen", return_value={"jobs": {"seed1417": {}}}), \
                patch.object(runner, "wait_build") as wait, \
                patch.object(runner, "check_build", return_value={}), \
                patch.object(runner.base, "run") as compile_run, \
                patch.object(runner, "schedule") as schedule, patch.object(runner, "merge"):
            runner.execute(self.output, True, "build.service", 7200, 8)
        wait.assert_called_once_with("build.service", self.output, 7200, adopt_built=False)
        schedule.assert_called_once_with(self.output, ["seed1417"], 8)
        compile_run.assert_not_called()

    def test_adopt_alone_never_compiles_and_requires_image_check(self):
        root = Path(self.temp.name) / "repo"
        (root / "verification/out").mkdir(parents=True)
        runner.save(self.output / "status.json", {"status": "PREPARED"})
        with patch.object(runner, "ROOT", root), patch.object(runner.base, "check_service"), \
                patch.object(runner, "frozen", return_value={"jobs": {}}), \
                patch.object(runner, "wait_build") as wait, \
                patch.object(runner, "check_build", side_effect=RuntimeError("image mismatch")) as image, \
                patch.object(runner.base, "run") as compile_run, \
                patch.object(runner, "schedule") as schedule:
            with self.assertRaisesRegex(RuntimeError, "image mismatch"):
                runner.execute(self.output, False, "build.service", 7200, 8, adopt_built=True)
        wait.assert_called_once_with("build.service", self.output, 7200, adopt_built=True)
        image.assert_called_once_with(self.output)
        compile_run.assert_not_called()
        schedule.assert_not_called()

    def test_failed_build_cannot_replay_or_merge(self):
        root = Path(self.temp.name) / "repo"
        (root / "verification/out").mkdir(parents=True)
        runner.save(self.output / "status.json", {"status": "PREPARED"})
        with patch.object(runner, "ROOT", root), patch.object(runner.base, "check_service"), \
                patch.object(runner, "frozen", return_value={}), \
                patch.object(runner, "wait_build", side_effect=RuntimeError("build failed")), \
                patch.object(runner, "schedule") as schedule, patch.object(runner, "merge") as merge:
            with self.assertRaisesRegex(RuntimeError, "build failed"):
                runner.execute(self.output, True, "build.service", 7200, 8)
        schedule.assert_not_called()
        merge.assert_not_called()
        self.assertEqual(runner.read(self.output / "status.json")["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
