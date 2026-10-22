import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_remaining15_validation as runner


class RemainingValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)

    def save(self, relative, data):
        runner.save(self.output / relative, data)

    def inventory(self):
        seeds = [1417, *runner.CONTROLS, *runner.OOB_SEEDS, 1401, 1402, 1406, 1420]
        rows = [{"name": f"case{s}", "seed": s, "kind": "random", "test": "profile"} for s in seeds]
        rows += [{"name": "vlsseg", "kind": "directed", "test": "rvv:vlsseg"}]
        checkpoint = {"status": "STOPPED", "completed": len(rows),
                      "cases": {r["name"]: {"status": "FAIL"} for r in rows}}
        return {"cases": rows}, checkpoint

    def test_defaults_select_only_seed1417_and_six_controls(self):
        plan, checkpoint = self.inventory()
        remaining, selected = runner.select_cases(plan, checkpoint, [])
        self.assertEqual(len(remaining), 15)
        self.assertEqual([r["seed"] for r in selected], [1417, *runner.CONTROLS])
        self.assertEqual(len(remaining) - len(selected), 8)

    def test_confirmed_replay_requires_explicit_unresolved_seed(self):
        plan, checkpoint = self.inventory()
        _, selected = runner.select_cases(plan, checkpoint, [1402])
        self.assertEqual(selected[-1]["seed"], 1402)
        for seeds in ([701], [1417], [1402, 1402], [999], [1409], [1410], [1412]):
            with self.subTest(seeds=seeds), self.assertRaises(RuntimeError):
                runner.select_cases(plan, checkpoint, seeds)

    def test_current_confirmed_pair_keeps_other_loads_pending(self):
        plan, checkpoint = self.inventory()
        remaining, selected = runner.select_cases(plan, checkpoint, [1406, 1420])
        self.assertEqual([r["seed"] for r in selected], [1417, *runner.CONTROLS, 1406, 1420])
        self.assertTrue({1401, 1402, 1409, 1410, 1412} <=
                        {r.get("seed") for r in remaining if r not in selected})

    def test_active_or_incomplete_batch_rejected(self):
        plan, checkpoint = self.inventory()
        checkpoint["status"] = "RUNNING"
        with self.assertRaisesRegex(RuntimeError, "active"):
            runner.select_cases(plan, checkpoint, [])
        checkpoint["status"] = "STOPPED"
        checkpoint["completed"] -= 1
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            runner.select_cases(plan, checkpoint, [])

    def test_source_allowlist_exact_and_dispatcher_opt_in(self):
        before = [{"path": str(p), "sha256": "old"} for p in
                  (runner.SLDU, runner.DISPATCHER, runner.ROOT / "hardware/src/ara.sv")]
        after = copy.deepcopy(before)
        after[0]["sha256"] = "new"
        self.assertEqual(runner.authorized_sources(before, after), [str(runner.SLDU)])
        after[1]["sha256"] = "new"
        with self.assertRaisesRegex(RuntimeError, "unauthorized"):
            runner.authorized_sources(before, after)
        self.assertEqual(len(runner.authorized_sources(before, after, True)), 2)
        after[2]["sha256"] = "new"
        with self.assertRaisesRegex(RuntimeError, "unauthorized"):
            runner.authorized_sources(before, after, True)
        with self.assertRaisesRegex(RuntimeError, "inventory"):
            runner.authorized_sources(before, before[:-1], True)

    def test_private_elf_copy_preserves_source_and_rejects_overwrite(self):
        source, target = self.output / "old.elf", self.output / "inputs/new.elf"
        source.write_bytes(b"original")
        files = set()
        record = runner.snapshot_elf(source, target, files)
        self.assertEqual(source.read_bytes(), target.read_bytes())
        self.assertEqual(record["elf_sha256"], runner.sha256(source))
        self.assertEqual(files, {source, target})
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            runner.snapshot_elf(source, target, files)

    def record(self):
        return {"image_root": str(self.output / "prebuilt"), "prebuilt": True,
                "spike": "spike", "jobs": {
            "seed1417": {"kind": "replay", "seed": 1417, "case": "oldcase", "summary": "old.json",
                         "elf_sha256": "hash", "original_case": "old-case1417"},
            "vslide1up_vredand": {"kind": "directed", "test": "rvv:vslide1up_vredand", "elf": "frozen.elf"},
            "vlsseg": {"kind": "directed", "test": "rvv:vlsseg", "elf": "frozen.elf", "timeout_s": 900},
            "axpy": {"kind": "axpy", "elf": "frozen.elf"}}}

    def test_replay_commands_always_strict_and_use_prebuilt(self):
        command, audit = runner.commands(self.output, "seed1417", self.record())
        self.assertIn("replay-failed-rvv", command)
        self.assertNotIn("--include-passed", command)
        self.assertEqual(command[command.index("--simv") + 1], str(self.output / "prebuilt/sim/simv"))
        self.assertEqual(command[command.index("--watchdog-cycles") + 1], "100000")
        for flag in ("--require-trace", "--require-vector", "--require-full-match"):
            self.assertIn(flag, audit)

    def test_directed_uses_frozen_elf_not_apps_bin_or_build(self):
        record = self.record()
        with patch.object(runner, "check_frozen", return_value=record), \
             patch.object(runner, "RegressionRunner") as engine:
            engine.return_value.run.return_value = [type("Result", (), {"status": "PASS"})()]
            runner.run_directed(self.output, "vlsseg")
        options, tests, _ = engine.call_args.args
        self.assertTrue(options.skip_build)
        self.assertFalse(options.code_coverage)
        self.assertTrue(options.commit_trace)
        self.assertEqual(options.timeout_s, 900)
        self.assertEqual(tests[0].binary, Path("frozen.elf"))

    def test_compile_flags_are_same_config_without_coverage(self):
        command = runner.compile_command(self.output)
        for flag in ("nr_lanes=4", "vlen=1024", "qbs=1", "akv=1", "akv_v2=1",
                     "sim_l2_mb=2", "code_coverage=0", "verify_source_manifest=1", "no_fsdb=1"):
            self.assertIn(flag, command)

    def test_prebuilt_rejects_changed_compile_flags_before_use(self):
        with patch.object(runner, "vcs_argv", return_value=["wrong"]):
            with self.assertRaisesRegex(RuntimeError, "compile options"):
                runner.freeze_candidate(self.output, {**self.record(), "compile_argv": ["expected"]})

    def test_job_cannot_bypass_seed_gate(self):
        self.save("candidate.json", {})
        self.save("seed1417-scheduler/status.json", {"status": "FAIL"})
        with patch.object(runner, "check_frozen", return_value=self.record()), \
             patch.object(runner, "run") as launch:
            with self.assertRaisesRegex(RuntimeError, "seed1417 gate"):
                runner.job(self.output, "axpy")
            launch.assert_not_called()

    def execute_fixture(self):
        record = self.record()
        record["phases"] = [("seed1417", ["seed1417"], 1), ("regression", ["axpy"], 5)]
        state = {"status": "PREPARED", "remaining": [
            {"name": "old-case1417", "validation_status": "PENDING"},
            {"name": "old-case1401", "validation_status": "PENDING"}]}
        self.save("checkpoint.json", state)
        return record

    def test_prebuilt_skips_compile_and_failure_stops_next_phase(self):
        record = self.execute_fixture()
        with patch.object(runner, "check_service"), \
             patch.object(runner, "check_frozen", return_value=record), \
             patch.object(runner, "compile_command") as compile_command, \
             patch.object(runner, "run", side_effect=RuntimeError("seed failed")) as launch:
            with self.assertRaisesRegex(RuntimeError, "seed failed"):
                runner.execute(self.output)
            compile_command.assert_not_called()
            self.assertEqual(launch.call_count, 1)
        state = runner.read(self.output / "checkpoint.json")
        self.assertEqual(state["status"], "STOPPED")
        self.assertTrue(all(r["validation_status"] == "PENDING" for r in state["remaining"]))

    def test_selected_pass_leaves_unselected_pending(self):
        record = self.execute_fixture()
        for phase, names, workers in record["phases"]:
            self.save(f"{phase}-scheduler/status.json", {"status": "PASS", "results": [
                {"name": name, "status": "PASS"} for name in names]})
            for name in names:
                self.save(f"verdicts/{name}.json", {"status": "PASS"})
        with patch.object(runner, "check_service"), \
             patch.object(runner, "check_frozen", return_value=record), patch.object(runner, "run"):
            runner.execute(self.output)
        state = runner.read(self.output / "checkpoint.json")
        self.assertEqual(state["status"], "SELECTED_PASS")
        self.assertEqual(state["pending_count"], 1)
        self.assertEqual([r["validation_status"] for r in state["remaining"]], ["PASS", "PENDING"])

    def test_no_run_outside_service(self):
        self.execute_fixture()
        with patch.object(runner, "check_service", side_effect=RuntimeError("unsafe service")), \
             patch.object(runner, "run") as launch:
            with self.assertRaisesRegex(RuntimeError, "unsafe service"):
                runner.execute(self.output)
            launch.assert_not_called()

    def test_axpy_checks_identity_and_cycles_not_exit_code_only(self):
        record = self.record()
        result = self.output / "results/axpy"
        (result / "work").mkdir(parents=True)
        elf, log, trace = [result / "work" / p for p in ("input.elf", "run.vcs.log", "vector_trace.csv")]
        elf.write_bytes(b"elf")
        trace.write_text("trace")
        log.write_text("[PERF] total_cycles : 2810\n")
        image = {"simv": "hash"}
        self.save("candidate.json", {"image": image})
        record["jobs"]["axpy"]["elf_sha256"] = runner.sha256(elf)
        report = {"status": "PASS", "issues": [], "elf_sha256": runner.sha256(elf),
                  "log_sha256": runner.sha256(log), "vector_trace_sha256": runner.sha256(trace),
                  "sim_image_sha256": image}
        runner.save(result / "uvm_result.json", report)
        runner.validate_result(self.output, "axpy", record)
        log.write_text("[PERF] total_cycles : 2811\n")
        report["log_sha256"] = runner.sha256(log)
        runner.save(result / "uvm_result.json", report)
        with self.assertRaisesRegex(RuntimeError, "cycle regression"):
            runner.validate_result(self.output, "axpy", record)
        self.assertEqual(runner.read(result / "cycle_comparison.json")["status"], "FAIL")
        report["status"] = "FAIL"
        runner.save(result / "uvm_result.json", report)
        with self.assertRaisesRegex(RuntimeError, "UVM is not PASS"):
            runner.validate_result(self.output, "axpy", record)

    def test_scalar_prefix_and_vector_prefix_never_pass_strict_gate(self):
        self.assertFalse(runner._full_architecture_match({"status": "PREFIX", "matched_instructions": 1,
                                                       "ara_committed_instructions": 2}))
        self.assertFalse(runner._full_vector_match({"status": "PREFIX"}))

    def frozen_fixture(self):
        checker = self.output / "checker.py"
        elf = self.output / "old.elf"
        checker.write_text("original checker")
        elf.write_bytes(b"original ELF")
        record = {"tool_inventory": sorted(str(p) for p in
                  (runner.ROOT / "verification/ara_verify").glob("*.py")),
                  "files": {str(p): runner.sha256(p) for p in (checker, elf)}}
        self.save("frozen.json", record)
        self.save("checkpoint.json", {"frozen_sha256": runner.sha256(self.output / "frozen.json")})
        return checker, elf

    def test_checker_drift_stops_before_source_check_or_launch(self):
        checker, _ = self.frozen_fixture()
        checker.write_text("changed checker")
        with patch.object(runner, "current_sources") as sources:
            with self.assertRaisesRegex(RuntimeError, "input/checker/ELF drift"):
                runner.check_frozen(self.output)
            sources.assert_not_called()

    def test_elf_drift_stops_before_source_check_or_launch(self):
        _, elf = self.frozen_fixture()
        elf.write_bytes(b"changed ELF")
        with patch.object(runner, "current_sources") as sources:
            with self.assertRaisesRegex(RuntimeError, "input/checker/ELF drift"):
                runner.check_frozen(self.output)
            sources.assert_not_called()

    def test_frozen_manifest_drift_rejected(self):
        self.frozen_fixture()
        self.save("frozen.json", {})
        with self.assertRaisesRegex(RuntimeError, "manifest changed"):
            runner.check_frozen(self.output)


if __name__ == "__main__":
    unittest.main()
