"""Host-only replay policy tests; no simulator or campaign is launched."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "coverage"))
import run_batch_coverage as batch


class BatchCoverageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.output = self.root / "coverage"
        self.output.mkdir()
        self.source = self.root / "functional/cases/random/tests/generated"
        self.source.mkdir(parents=True)
        self.summary = self.source.parent.parent / "summary.json"
        self.row = {"name": "random-1", "kind": "random"}
        self.actual = {"status": "PASS", "artifact_dir": str(self.source),
                       "summary": str(self.summary),
                       "audit": str(self.summary.parent / "independent_audit.json")}
        elf = self.source / "input.elf"
        elf.write_bytes(b"test ELF")
        self.identity = {"image": "/vcs", "images": {"/vcs": {"/vcs": "hash"}},
                         "spike": "/spike", "files": {"/spike": "spike-hash"}}
        batch.save(self.source / "inputs.json", {
            "binary": {"path": str(elf), "sha256": batch.sha256(elf)},
            "simv": {"image_sha256": {"/vcs": "hash"}}, "spike": {"sha256": "spike-hash"}})
        batch.save(self.source / "rtl.command.json", {"command": ["/vcs", "+COMMIT_TOHOST=80001000"]})
        self.set_status("PASS")
        batch.save(Path(self.actual["audit"]), self.audit())
        self.process = patch.object(batch.subprocess, "run", side_effect=AssertionError("external command"))
        self.process.start()
        self.addCleanup(self.process.stop)

    def audit(self):
        return {"status": "PASS", "errors": [], "case_count": 1,
                "passed_cases": 1, "failed_cases": 0,
                "policy": {key: True for key in ("require_trace", "require_complete",
                                                 "require_vector", "require_full_match")},
                "cases": [{"status": "PASS", "errors": [], "name": "generated",
                           "artifact_dir": str(self.source)}]}

    def set_status(self, status):
        self.actual["status"] = status
        batch.save(self.summary, [{"name": "generated", "status": status,
                                   "artifact_dir": str(self.source)}])
        batch.save(self.source / "result.json", {"status": status})

    def case(self):
        return batch.source_case(self.row, self.actual, self.output, self.identity)

    def test_source_case_freezes_elf_and_random_tohost(self):
        case = self.case()
        self.assertEqual(case["tohost_addr"], 0x80001000)
        self.assertEqual(batch.sha256(Path(case["frozen_elf"])), case["elf_sha256"])
        self.assertIn(str(self.source / "rtl.command.json"), case["source_files"])
        (self.source / "input.elf").write_bytes(b"drift")
        with self.assertRaisesRegex(RuntimeError, "drift"):
            batch.check_files(case["source_files"])

    def test_failed_source_is_eligible_without_pass_audit(self):
        self.set_status("RTL_STALL")
        self.actual["audit"] = None
        self.assertEqual(self.case()["source_status"], "RTL_STALL")

    def test_directed_source_does_not_invent_random_tohost(self):
        self.row["kind"] = "directed"
        (self.source / "rtl.command.json").unlink()
        (self.source / "result.json").unlink()
        batch.save(self.source / "command.json", {"command": ["/vcs", "+COMMIT_TRACE=commit_trace.csv"]})
        (self.source / "console.log").write_text("Core Test *** SUCCESS *** (tohost = 0)\n")
        report = self.audit()
        report["policy"].update(require_vector=False, require_full_match=False,
                                require_contract=False, recompute_terminal_tohost=False)
        batch.save(Path(self.actual["audit"]), report)
        metadata = batch.read(self.source / "inputs.json")
        metadata.pop("spike")
        batch.save(self.source / "inputs.json", metadata)
        case = self.case()
        self.assertIsNone(case["tohost_addr"])
        self.assertIn(str(self.source / "command.json"), case["source_files"])
        self.assertIn(str(self.source / "console.log"), case["source_files"])
        self.assertNotIn(str(self.source / "result.json"), case["source_files"])
        self.assertEqual(case["source_audit"], self.actual["audit"])
        self.actual["status"] = "FAIL"
        with self.assertRaisesRegex(RuntimeError, "disagree"):
            self.case()

    def test_bad_hash_and_summary_disagreement_rejected(self):
        (self.source / "input.elf").write_bytes(b"changed")
        with self.assertRaisesRegex(RuntimeError, "ELF hash"):
            self.case()
        self.actual["status"] = "FAIL"
        with self.assertRaisesRegex(RuntimeError, "disagree"):
            self.case()

    def test_tohost_missing_duplicate_unaligned_and_outside_model(self):
        for args in ([], ["80001000", "80001008"], ["80001001"], ["80200000"]):
            with self.subTest(args=args):
                batch.save(self.source / "rtl.command.json", {
                    "command": ["+COMMIT_TOHOST=" + x for x in args]})
                with self.assertRaises(RuntimeError):
                    self.case()

    def test_audit_must_match_actual_case_and_full_random_policy(self):
        for mutation in (lambda a: a.update(status="FAIL"),
                         lambda a: a["policy"].update(require_full_match=False),
                         lambda a: a["cases"][0].update(artifact_dir="/wrong"),
                         lambda a: a.update(case_count=2)):
            report = self.audit()
            mutation(report)
            batch.save(Path(self.actual["audit"]), report)
            with self.assertRaisesRegex(RuntimeError, "VCS PASS audit"):
                self.case()

    def test_readiness_uses_supplied_batch_and_requires_all_completed(self):
        source_batch = self.root / "batch-02"
        batch.save(source_batch / "plan.json", {"cases": [self.row]})
        state = {"status": "COMPLETE_WITH_FAILURES", "total": 1, "completed": 1,
                 "infrastructure_errors": 0, "cases": {"random-1": {"status": "RTL_STALL"}}}
        batch.save(source_batch / "checkpoint.json", state)
        self.assertEqual(len(batch.ready_cases(source_batch)), 1)
        for update in ({"status": "RUNNING"}, {"status": "STOPPED"}, {"completed": 0},
                       {"infrastructure_errors": 1}, {"cases": {}}):
            batch.save(source_batch / "checkpoint.json", {**state, **update})
            with self.assertRaises(RuntimeError):
                batch.ready_cases(source_batch)

    def sample(self, status="PASS", raw=True):
        target = self.output / "replays/random-1"
        target.mkdir(parents=True, exist_ok=True)
        (target / "simv").write_bytes(b"image")
        (target / "elf").write_bytes(b"test ELF")
        (target / "sim.log").write_text("Core Test *** SUCCESS *** (tohost = 0)\n" if status == "PASS"
                                         else "bounded execution stopped\n")
        result = {"status": status, "simv": str(target / "simv"), "elf": str(target / "elf"),
                  "simv_sha256": batch.sha256(target / "simv"),
                  "elf_sha256": batch.sha256(target / "elf"), "sim_returncode": 0,
                  "term_cycles": 100000, "timeout_s": 900, "tohost_addr": 0x80001000,
                  "sim_log_sha256": batch.sha256(target / "sim.log"),
                  "self_check_pass": status == "PASS"}
        if status == "PASS":
            result["report_returncode"] = 0
        else:
            result["reason"] = "simulation or in-program self-check failed"
        if raw:
            (target / "coverage.dat").write_text("C '\x01f\x02/hardware/src/dut.sv\x01t\x02line' 1\n")
            result["coverage_sha256"] = batch.sha256(target / "coverage.dat")
        batch.save(target / "result.json", result)
        return target / "result.json", result, {"image_sha256": result["simv_sha256"]}

    def test_passed_only_requires_both_verdicts(self):
        path, _, plan = self.sample()
        case = self.case()
        self.assertTrue(batch.check_result(path, case, plan, 0)["passed_only"])
        case["source_status"] = "RTL_FAIL"
        outcome = batch.check_result(path, case, plan, 0)
        self.assertFalse(outcome["passed_only"])
        self.assertTrue(outcome["raw_valid"])
        self.assertTrue(outcome["partial"])

    def test_normal_failure_preserves_valid_partial_raw(self):
        path, _, plan = self.sample("FAIL")
        result = batch.check_result(path, self.case(), plan, 1)
        self.assertTrue(result["raw_valid"])
        self.assertFalse(result["passed_only"])

    def test_bounded_timeout_without_raw_is_case_failure(self):
        path, result, plan = self.sample("FAIL", raw=False)
        result.pop("sim_returncode")
        result["reason"] = "timeout: simulator"
        batch.save(path, result)
        self.assertFalse(batch.check_result(path, self.case(), plan, 1)["raw_valid"])

    def test_environment_report_error_or_changed_raw_is_infrastructure(self):
        case = self.case()
        path, result, plan = self.sample("FAIL")
        (path.parent / "sim.log").write_text("error while loading shared libraries")
        result["sim_log_sha256"] = batch.sha256(path.parent / "sim.log")
        batch.save(path, result)
        with self.assertRaisesRegex(RuntimeError, "environment"):
            batch.check_result(path, case, plan, 1)
        path, result, plan = self.sample("FAIL")
        result["report_returncode"] = 1
        batch.save(path, result)
        with self.assertRaisesRegex(RuntimeError, "runner/report"):
            batch.check_result(path, case, plan, 1)
        path, result, plan = self.sample("FAIL")
        (path.parent / "coverage.dat").write_text("changed")
        with self.assertRaisesRegex(ValueError, "coverage.dat"):
            batch.check_result(path, case, plan, 1)

    def test_worker_failure_continues_but_drift_returns_nonzero(self):
        self.set_status("RTL_STALL")
        self.actual["audit"] = None
        case = self.case()
        path, _, plan = self.sample("FAIL")
        plan.update(cases=[case], image="/image", reporter="/reporter")
        with patch.object(batch, "check_inputs", return_value=plan), \
                patch.object(batch, "invoke", return_value=1) as invoke:
            self.assertEqual(batch.worker(self.output, case["name"]), 0)
            invoke.assert_called_once()
            args = invoke.call_args.args[0]
            self.assertEqual(args[args.index("--timeout") + 1], "900")
            self.assertEqual(args[args.index("--term-cycles") + 1], "100000")
            self.assertIn("--tohost-addr", args)
        with patch.object(batch, "check_inputs", side_effect=RuntimeError("drift")), \
                patch.object(batch, "invoke") as invoke:
            self.assertEqual(batch.worker(self.output, case["name"]), 1)
            invoke.assert_not_called()

    def test_worker_pass_requires_fresh_audit_before_replay(self):
        case = self.case()
        path, _, plan = self.sample()
        plan.update(cases=[case], image="/image", reporter="/reporter")
        with patch.object(batch, "check_inputs", return_value=plan), \
                patch.object(batch, "invoke", return_value=1) as invoke:
            self.assertEqual(batch.worker(self.output, case["name"]), 1)
            invoke.assert_called_once()
            self.assertIn("audit", invoke.call_args.args[0])
        def invoke(command, log, timeout):
            if "audit" in command:
                batch.save(Path(command[command.index("--output") + 1]), self.audit())
            return 0
        with patch.object(batch, "check_inputs", return_value=plan), \
                patch.object(batch, "invoke", side_effect=invoke) as mocked:
            self.assertEqual(batch.worker(self.output, case["name"]), 0)
            self.assertEqual(mocked.call_count, 2)
        outcome = batch.read(self.output / "outcomes/random-1.json")
        self.assertTrue(outcome["passed_only"])
        self.assertTrue(outcome["source_reaudit_sha256"])

    def test_two_collections_preserve_association_and_empty_passed_set(self):
        path, result, plan = self.sample("FAIL")
        self.set_status("RTL_STALL")
        self.actual["audit"] = None
        case = self.case()
        plan.update(cases=[case], reporter="/reporter")
        outcome = batch.check_result(path, case, plan, 1)
        outcome.update(source_status="RTL_STALL", elf_sha256=case["elf_sha256"])
        batch.save(self.output / "outcomes/random-1.json", outcome)
        batch.save(self.output / "plan.json", plan)
        with patch.object(batch, "invoke", return_value=0) as invoke:
            batch.merge(self.output, plan)
            invoke.assert_called_once()
            self.assertIn(str(batch.COVERAGE / "merge_exploration.py"), invoke.call_args.args[0])
        report = batch.read(self.output / "exploration/collection.json")
        self.assertTrue(report["includes_source_failures"])
        self.assertEqual(report["samples"][0]["elf_sha256"], case["elf_sha256"])
        self.assertEqual(batch.read(self.output / "passed-only/collection.json")["status"], "EMPTY")
        self.assertEqual(report["coverage"], batch.SCOPES)

    def test_scheduler_failure_returns_promptly_without_merge(self):
        (self.root / "verification/out").mkdir(parents=True)
        batch.save(self.output / "status.json", {"status": "PREPARED"})
        with patch.object(batch, "ROOT", self.root), patch.object(batch, "check_service"), \
                patch.object(batch, "check_inputs", return_value={"batch": "/batch", "cases": [self.row]}), \
                patch.object(batch, "check_batch"), patch.object(batch, "invoke", return_value=1) as invoke, \
                patch.object(batch, "merge") as merge:
            self.assertEqual(batch.execute(self.output, 3), 1)
            invoke.assert_called_once()
            command = invoke.call_args.args[0]
            self.assertEqual(command[command.index("--jobs") + 1], "3")
            merge.assert_not_called()
        self.assertEqual(batch.read(self.output / "status.json")["status"], "STOPPED")

    def test_default_cli_only_prepares_explicit_batch(self):
        fresh = self.root / "new-output"
        with patch.object(sys, "argv", ["coverage", "--batch", str(self.source),
                                       "--image-dir", str(self.source), "--output", str(fresh),
                                       "--verilator-coverage", str(self.source / "input.elf")]), \
                patch.object(batch, "checked_output", return_value=fresh), \
                patch.object(batch, "prepare") as prepare, patch.object(batch, "execute") as execute:
            self.assertEqual(batch.main(), 0)
            self.assertEqual(prepare.call_args.args[0], self.source)
            execute.assert_not_called()

    def prepare_fixture(self):
        image_dir = self.root / "image"
        image_dir.mkdir()
        image = image_dir / "Vara_tb_verilator"
        image.write_bytes(b"frozen image")
        image.chmod(0o550)
        batch.save(image_dir / "status.json", {"status": "PASS", "source_check": "PASS",
            "coverage": batch.SCOPES, "image": str(image), "image_sha256": batch.sha256(image)})
        sources = {"schema_version": 1, "filelist": "/filelist", "repo_root": str(self.root),
                   "build_dir": "/build", "files": [{"path": str(self.root / "hardware/src/ara_dispatcher.sv"),
                                                      "sha256": "rtl-hash"}]}
        for name in ("source_manifest.json", "source_manifest.before.json", "source_manifest.after.json"):
            batch.save(image_dir / name, sources)
        source_batch = self.root / "ready-batch"
        batch.save(source_batch / "plan.json", {"cases": [self.row]})
        batch.save(source_batch / "checkpoint.json", {
            "status": "PASS", "total": 1, "completed": 1, "infrastructure_errors": 0,
            "cases": {self.row["name"]: self.actual}})
        self.identity["sources"] = sources["files"]
        batch.save(source_batch / "identity.json", self.identity)
        for name in ("verify.py", "run_batch_exploration.py", "run_coverage_checkpoint.py",
                     "run_failfast_checkpoint.py"):
            path = self.root / "verification" / name
            path.parent.mkdir(exist_ok=True)
            path.write_text("# fixture\n")
        return source_batch, image_dir, sources, image

    def test_prepare_manifest_equal_dictionaries_and_no_simulation(self):
        source_batch, image_dir, sources, reporter = self.prepare_fixture()
        # JSON formatting/key order must not cause a false provenance failure.
        (image_dir / "source_manifest.after.json").write_text(json.dumps(sources, sort_keys=True))
        def invoke(command, log, timeout):
            self.assertTrue(command[1].endswith("check_elf_fit.py"))
            batch.save(self.output / "elf_fit.json", {"status": "PASS"})
            return 0
        with patch.object(batch, "ROOT", self.root), \
                patch.object(batch, "check_batch", return_value=self.identity), \
                patch.object(batch, "check_sources", return_value=sources), \
                patch.object(batch, "invoke", side_effect=invoke) as invoked:
            batch.prepare(source_batch, image_dir, reporter, self.output)
            invoked.assert_called_once()
        state = batch.read(self.output / "status.json")
        self.assertEqual(state["status"], "PREPARED")
        self.assertFalse(state["simulations_started"])
        plan = batch.read(self.output / "plan.json")
        self.assertEqual(plan["batch"], str(source_batch))
        self.assertEqual(plan["coverage"], batch.SCOPES)
        self.assertEqual(plan["cases"][0]["source_elf"], str(self.source / "input.elf"))

    def test_prepare_rejects_manifest_metadata_drift_before_any_command(self):
        source_batch, image_dir, sources, reporter = self.prepare_fixture()
        for suffix in ("before", "after"):
            for s in ("before", "after"):
                batch.save(image_dir / f"source_manifest.{s}.json", sources)
            batch.save(image_dir / f"source_manifest.{suffix}.json", {**sources, "build_dir": "/other"})
            with self.subTest(suffix=suffix), patch.object(batch, "ROOT", self.root), \
                    patch.object(batch, "check_sources", return_value=sources), \
                    patch.object(batch, "check_batch") as checked, patch.object(batch, "invoke") as invoked:
                with self.assertRaisesRegex(RuntimeError, "before/after provenance"):
                    batch.prepare(source_batch, image_dir, reporter, self.output)
                checked.assert_not_called()
                invoked.assert_not_called()

    def test_source_pass_snapshot_preserves_stopped_and_excluded_without_elf(self):
        source_batch, _, _, _ = self.prepare_fixture()
        excluded = {"name": "failed-no-elf", "kind": "random"}
        batch.save(source_batch / "plan.json", {"cases": [self.row, excluded]})
        batch.save(source_batch / "checkpoint.json", {"status": "STOPPED", "passed": 1,
            "total": 2, "completed": 2, "infrastructure_errors": 1,
            "cases": {self.row["name"]: self.actual,
                      excluded["name"]: {"status": "INFRASTRUCTURE_ERROR", "reason": "no ELF"}}})
        with patch.object(batch, "check_source_stopped", return_value={"MainPID": "0"}), \
                patch.object(batch, "check_batch", return_value=self.identity):
            snapshot = batch.pass_source_snapshot(source_batch, "batch.service")
        self.assertEqual(snapshot["selected_names"], [self.row["name"]])
        self.assertEqual(snapshot["original_status"], "STOPPED")
        self.assertEqual(snapshot["original_total"], 2)
        self.assertFalse(snapshot["complete_original_batch"])
        self.assertEqual(snapshot["excluded"][0]["original"]["reason"], "no ELF")
        with self.assertRaises(RuntimeError):
            batch.ready_cases(source_batch)
        state = batch.read(source_batch / "checkpoint.json")
        state["cases"][self.row["name"]]["status"] = "FAIL"
        batch.save(source_batch / "checkpoint.json", state)
        with self.assertRaisesRegex(RuntimeError, "drift"):
            batch.check_files(snapshot["files"])

    def test_source_service_requires_no_main_control_or_descendant_process(self):
        state = {"LoadState": "loaded", "ActiveState": "failed", "MainPID": "0", "ControlPID": "0",
                 "ControlGroup": "", "TasksCurrent": "[not set]", "ExecStart": f"driver --output {self.root}"}
        for change in ({}, {"ActiveState": "active"}, {"MainPID": "123"}, {"ControlPID": "4"},
                       {"TasksCurrent": "1"}, {"ExecStart": "another batch"}, {"LoadState": "not-found"},
                       {"ControlGroup": "/"}):
            stdout = "\n".join(f"{k}={v}" for k, v in {**state, **change}.items())
            with patch.object(batch.subprocess, "run", return_value=SimpleNamespace(stdout=stdout)):
                if change:
                    with self.assertRaises(RuntimeError):
                        batch.check_source_stopped(self.root, "batch.service")
                else:
                    self.assertEqual(batch.check_source_stopped(self.root, "batch.service"), state)
        procs = self.root / "cgroup.procs"
        procs.write_text("123\n")
        stdout = "\n".join(f"{k}={v}" for k, v in {**state, "ControlGroup": "/unit"}.items())
        with patch.object(batch.subprocess, "run", return_value=SimpleNamespace(stdout=stdout)), \
                patch.object(Path, "exists", return_value=True), \
                patch.object(Path, "rglob", return_value=[procs]):
            with self.assertRaisesRegex(RuntimeError, "cgroup still has processes"):
                batch.check_source_stopped(self.root, "batch.service")

    def test_pass_only_prepare_records_partial_selection_and_never_dispatches_excluded(self):
        source_batch, image_dir, sources, reporter = self.prepare_fixture()
        state = batch.read(source_batch / "checkpoint.json")
        state.update(status="STOPPED", passed=1, total=2, completed=2, infrastructure_errors=1)
        state["cases"]["excluded"] = {"status": "INFRASTRUCTURE_ERROR", "reason": "missing ELF"}
        batch.save(source_batch / "checkpoint.json", state)
        batch.save(source_batch / "plan.json", {"cases": [self.row, {"name": "excluded", "kind": "random"}]})
        def fit(command, log, timeout):
            self.assertEqual(command.count("--elf"), 1)
            batch.save(self.output / "elf_fit.json", {"status": "PASS"})
            return 0
        with patch.object(batch, "ROOT", self.root), patch.object(batch, "check_source_stopped", return_value={}), \
                patch.object(batch, "check_sources", return_value=sources), \
                patch.object(batch, "check_batch", return_value=self.identity), \
                patch.object(batch, "invoke", side_effect=fit):
            batch.prepare(source_batch, image_dir, reporter, self.output,
                          source_pass_only=True, batch_unit="batch.service")
        plan = batch.read(self.output / "plan.json")
        self.assertEqual(len(plan["cases"]), 1)
        self.assertEqual(plan["source_selection"]["original_total"], 2)
        self.assertEqual(plan["source_selection"]["original_status"], "STOPPED")
        self.assertEqual(batch.read(self.output / "status.json")["total"], 1)
        self.assertEqual(batch.read(source_batch / "checkpoint.json"), state)

    def test_pass_only_never_waives_identity_drift(self):
        source_batch, _, _, _ = self.prepare_fixture()
        state = batch.read(source_batch / "checkpoint.json")
        state.update(status="STOPPED", passed=1)
        batch.save(source_batch / "checkpoint.json", state)
        with patch.object(batch, "check_source_stopped", return_value={}), \
                patch.object(batch, "check_batch", side_effect=RuntimeError("wrapper drift")):
            with self.assertRaisesRegex(RuntimeError, "wrapper drift"):
                batch.pass_source_snapshot(source_batch, "batch.service")


if __name__ == "__main__":
    unittest.main()
