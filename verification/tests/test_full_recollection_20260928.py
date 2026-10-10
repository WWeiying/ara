"""Pure/mocked tests only: never run VCS, DVE, URG, or a background service."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "verification/coverage"
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("full_recollection", HERE / "run_full_recollection_20260928.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


def uvm(**kwargs):
    return dict({"name": "test", "kind": "uvm", "elf_sha256": "a" * 64,
        "oracle": "UVM+selfcheck+independent-audit", "timeout_s": 900,
        "frozen_elf": "/input.elf", "coverage_test": "test", "source_files": {},
        "origins": [{"source": "old-plan", "name": "old-FAIL"}], "reset": {}}, **kwargs)


class SelectionTests(unittest.TestCase):
    def test_aliases_and_wall_budgets(self):
        cases = [uvm(), uvm(name="other", timeout_s=1800)]
        actual = run.deduplicate(cases)
        self.assertEqual(len(actual), 1)
        self.assertEqual(actual[0]["timeout_s"], 1800)
        self.assertEqual(len(actual[0]["origins"]), 2)
        self.assertEqual(cases[0]["name"], "test")

    def test_reset_contracts_and_oracles_never_collapse(self):
        cases = [uvm(), uvm(reset={"kind": "read", "read_index": 1}),
                 uvm(reset={"kind": "read", "read_index": 2}),
                 uvm(reset={"kind": "state", "target": "qbs_request"}),
                 uvm(reset={"kind": "state", "target": "qbs_validate"}),
                 uvm(oracle="different"), uvm(elf_sha256="b" * 64),
                 uvm(require_axi=False), uvm(required_markers=["PASSED"])]
        self.assertEqual(len(run.deduplicate(cases)), len(cases))

    def test_watchdog_is_not_a_wall_budget(self):
        case = uvm(kind="replay", seed=721, spike_sha256="s", watchdog_cycles=100000)
        other = dict(case, watchdog_cycles=250000)
        self.assertEqual(len(run.deduplicate([case, other])), 2)

    def test_production_inventory_retains_all_planned_failures(self):
        data = run.inventory(run.DEFAULT_PLAN)
        cases = data["cases"]
        origins = {(o["source"], o["name"]) for c in cases for o in c["origins"]}
        selection = run.read(run.DEFAULT_PLAN)
        for entry in selection["plans"]:
            path = ROOT / entry["path"]
            source = run.read(path)
            rows = source.get("cases", list(source.get("jobs", {}).values()))
            self.assertEqual(len(rows), entry["count"])
            for row in rows:
                self.assertIn((str(path), row["name"]), origins)
        names = {c.get("source_name") for c in cases}
        for name in selection["required_gap28_timeouts"]:
            self.assertIn("rvv:" + name, names)
        self.assertEqual(sum("vrvv_gap29_fp16_" in (n or "") for n in names), 6)
        self.assertEqual(data["latest_entries"], 48)
        self.assertEqual(data["repair_smoke_entries"], 4)
        self.assertEqual(data["unique_cases"], 600)
        self.assertEqual(set(data["case_bounds"]), {c["name"] for c in cases})
        for case in cases:
            bounds = data["case_bounds"][case["name"]]
            self.assertEqual(bounds["rtl_wall_s"], case["timeout_s"])
            self.assertEqual(bounds["runner_outer_s"], case["timeout_s"] + 600)
            self.assertEqual(bounds["independent_audit_s"], 300)
        self.assertFalse(any(c.get("seed") == 719 for c in cases))
        self.assertTrue(any(c.get("seed") == 721 for c in cases))
        self.assertEqual(len(data["gate_cases"]), 60)
        gates = [c for c in cases if c["name"] in data["gate_cases"]]
        by_name = {c["name"]: c for c in cases}
        ordered = [by_name[name] for name in data["gate_cases"]]
        self.assertEqual([c["source_name"] for c in ordered[:6]], selection["gate"]["fp16_tests"])
        self.assertEqual([c["source_name"] for c in ordered[6:12]],
                         ["rvv:" + name for name in selection["required_gap28_timeouts"]])
        self.assertEqual([c["coverage_test"] for c in ordered[12:16]], selection["gate"]["adjacent_smoke"])
        self.assertEqual([c["source_name"] for c in ordered[16:19]], selection["gate"]["conversion_tests"])
        self.assertEqual(ordered[19]["kind"], "axpy")
        self.assertEqual([c["source_name"] for c in ordered[20:]],
                         run.read(ROOT / selection["memory_selection"])["tests"])
        self.assertEqual(sum(c["kind"] == "directed" for c in gates), 55)
        self.assertEqual(sum(c["kind"] == "uvm" for c in gates), 4)
        self.assertEqual(sum(c["kind"] == "axpy" for c in gates), 1)
        self.assertTrue({"rvv:vfncvt", "rvv:vfwcvt", "rvv:vfcvt"} <= {c.get("source_name") for c in gates})
        gate_tests = {c.get("source_name") for c in gates}
        self.assertTrue(set(run.read(ROOT / selection["memory_selection"])["tests"]) <= gate_tests)
        self.assertTrue({f"rvv:vmemory_gap_nf{nf}_e{eew}_indexed" for nf in (5, 6, 7)
                         for eew in (8, 16, 32, 64)} <= gate_tests)
        self.assertTrue({"rvv:" + n for n in selection["required_gap28_timeouts"]} <= gate_tests)
        for case in cases:
            if case.get("source_name") in selection["wall_budget_review"]["seconds_by_test"]:
                self.assertEqual(case["timeout_s"], selection["wall_budget_review"]["seconds_by_test"][case["source_name"]])
                self.assertEqual(case["wall_timeout_adjustment"]["previous_seconds"], 300)
                self.assertEqual(case["contract"], run.contract(case))
                self.assertTrue(case["wall_timeout_adjustment"]["not_a_pass_claim"])

    def test_gate_does_not_drop_distinct_memory_elf_variant(self):
        data = run.inventory(run.DEFAULT_PLAN)
        selection = run.read(run.DEFAULT_PLAN)
        memory_tests = run.read(ROOT / selection["memory_selection"])["tests"]
        variant = dict(next(c for c in data["cases"] if c.get("source_name") == memory_tests[0]),
                       name="other-elf-variant", elf_sha256="different")
        policy = dict(selection["gate"], expected_count=61)
        gate = run.gate_selection(data["cases"] + [variant], policy, memory_tests, selection["required_gap28_timeouts"])
        self.assertEqual(len(gate), 61)
        self.assertIn("other-elf-variant", gate)

    def test_invalid_bounds_or_duplicate_gate_fail_closed(self):
        cases = [uvm(name=f"case{i}") for i in range(600)]
        gates = [c["name"] for c in cases[:60]]
        self.assertEqual(len(run.validate_bounds(cases, gates)), 600)
        with self.assertRaisesRegex(ValueError, "exactly once"):
            run.validate_bounds(cases, gates[:-1] + [gates[0]])
        for invalid in (0, -1, 1801, float("inf"), True):
            cases[0]["timeout_s"] = invalid
            with self.assertRaisesRegex(ValueError, "wall timeout"):
                run.validate_bounds(cases, gates)
        cases[0].update(timeout_s=900, kind="replay", spike_timeout_s=60, watchdog_cycles=0)
        with self.assertRaisesRegex(ValueError, "watchdog"):
            run.validate_bounds(cases, gates)


class GateTests(unittest.TestCase):
    def run_gate(self, tmp, failed=False, infra=False):
        output = Path(tmp)
        names = [f"gate{i}" for i in range(60)]
        run.save(output / "plan.json", {"gate_cases": names, "gate_expected_count": 60})
        calls = []
        def dispatch(directory, selected, jobs):
            calls.append((list(selected), jobs))
            (output / "scheduler").mkdir()
            if infra:
                raise RuntimeError("license unavailable")
            for name in selected:
                passed = not (failed and name == "gate0")
                run.save(output / "outcomes" / (name + ".json"),
                         {"name": name, "status": "PASS" if passed else "FAIL", "passed_only": passed})
        with patch.object(run, "original_schedule", side_effect=dispatch), patch.object(run, "frozen"):
            if failed or infra:
                with self.assertRaises((ValueError, RuntimeError)):
                    run.schedule(output, names + ["full0", "full1"], 8)
            else:
                run.schedule(output, names + ["full0", "full1"], 8)
        return output, calls

    def test_all_sixty_pass_then_only_remaining_cases_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            output, calls = self.run_gate(tmp)
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[1], (["full0", "full1"], 8))
            self.assertTrue((output / "gate-scheduler").is_dir())
            self.assertEqual(run.read(output / "gate.json")["status"], "PASS")

    def test_ordinary_gate_failure_blocks_full_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            output, calls = self.run_gate(tmp, failed=True)
            self.assertEqual(len(calls), 1)
            result = run.read(output / "gate.json")
            self.assertEqual(result["status"], "FAIL")
            self.assertFalse(result["full_dispatch_started"])
            self.assertEqual(result["failed"], [{"name": "gate0", "status": "FAIL"}])

    def test_infrastructure_gate_failure_blocks_full_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            output, calls = self.run_gate(tmp, infra=True)
            self.assertEqual(len(calls), 1)
            result = run.read(output / "gate.json")
            self.assertEqual(result["status"], "INFRASTRUCTURE_ERROR")
            self.assertFalse(result["full_dispatch_started"])


class RoutingTests(unittest.TestCase):
    def test_probe_checker_and_dependency_are_frozen(self):
        with patch.object(run.shutil, "which", return_value="/bin/sh"):
            paths = run.tool_paths()
        self.assertIn(Path(run.closure.__file__).resolve(), paths)
        self.assertIn(Path(run.closure.prior.__file__).resolve(), paths)

    def test_uvm_reset_arguments(self):
        case = uvm(reset={"kind": "read", "read_index": 2})
        command, audit, env = run.uvm_commands(Path("/fresh"), case, {"simv": "/new/sim/simv"})
        self.assertEqual(command[-1], "read")
        self.assertEqual(env["ARA_UVM_RESET_READ_INDEX"], "2")
        self.assertEqual(env["ARA_VCS_CODE_COVERAGE"], "1")
        self.assertIn("--expect-reset-abort", audit)
        self.assertIn("--require-axi-write", audit)

    def test_repair_smoke_preserves_audit_not_extra_axi_requirement(self):
        case = uvm(require_axi=False, required_markers=["PASSED"])
        command, audit, env = run.uvm_commands(Path("/fresh"), case, {"simv": "/new/sim/simv"})
        self.assertEqual(command[:3], ["timeout", "--foreground", "900"])
        self.assertIn("--require-backend", audit)
        self.assertNotIn("--require-axi", audit)
        self.assertIn("/fresh/results/test/code.vdb", command)

    def test_probe_opt_in_preserved(self):
        with patch.object(run, "original_commands", return_value=(["replay"], ["audit"])):
            command, _ = run.commands(Path("/fresh"), {"fault_vstart_probe": True}, {})
        self.assertEqual(command, ["replay", "--fault-vstart-probe"])

    def test_systemd_is_command_only_eight_workers_in_driver(self):
        command = run.systemd_command(Path("/fresh"), {"service": "full.service"})
        self.assertIn("--property=KillMode=control-group", command)
        self.assertIn("--property=Restart=no", command)
        self.assertEqual(command[-1], "--execute")
        self.assertNotIn("--collect", command)


class FailureTests(unittest.TestCase):
    def test_probe_semantics_fail_but_missing_capture_stops(self):
        with patch.object(run.closure, "check_probe", side_effect=RuntimeError("probe differs: cause")):
            self.assertEqual(run.probe_capture(Path("/artifact"), Path("/diagnostic"))["status"], "FAIL")
        with patch.object(run.closure, "check_probe", side_effect=RuntimeError("missing/ambiguous fresh fault-vstart response")):
            with self.assertRaises(RuntimeError):
                run.probe_capture(Path("/artifact"), Path("/diagnostic"))

    def test_reset_semantics_fail_but_missing_capture_stops(self):
        log = "[ARA_UVM_RESET_TEST] kind=state observed=1 target=qbs_request actual=DESCRIPTOR_REQUEST\n"
        self.assertTrue(run.reset_target_matches(log, "qbs_request"))
        self.assertFalse(run.reset_target_matches(log, "qbs_validate"))
        with self.assertRaises(ValueError):
            run.reset_target_matches("", "qbs_request")

    def test_uvm_nonzero_simulator_exit_is_audited_and_continues_on_functional_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            case = uvm()
            case["contract"] = run.contract(case)
            target = output / "results/test"
            plan = {"cases": [case], "simv": "/new/simv", "image": {"/new/simv": "hash"}}
            def invoke(command, log, timeout, env):
                if command[0] == "bash":
                    (target / "work").mkdir(parents=True)
                    for name in ("run.vcs.log", "vector_trace.csv", "input.elf"):
                        (target / "work" / name).write_text("functional-failure-evidence\n")
                    return 1
                self.assertIn("--require-axi-write", command)
                run.save(target / "uvm_result.json", {"status": "FAIL", "issues": ["selfcheck failed"],
                    "elf_sha256": case["elf_sha256"], "sim_image_sha256": plan["image"]})
                return 1
            with patch.object(run, "frozen", return_value=plan), patch.object(run, "check"), patch.object(run.batch, "invoke", side_effect=invoke) as invoke_mock, patch.object(run.batch, "valid_vdb", side_effect=ValueError("incomplete")), patch.object(run.batch, "publish"):
                self.assertEqual(run.worker(output, "test"), 0)
            self.assertEqual(invoke_mock.call_count, 2)
            outcome = run.read(output / "outcomes/test.json")
            self.assertEqual(outcome["status"], "FAIL")
            self.assertFalse(outcome["passed_only"])
            self.assertIn(str(target / "uvm_result.json"), outcome["files"])

    def test_post_exit_audit_requires_real_simulation_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(run.batch, "invoke") as invoke:
                with self.assertRaisesRegex(ValueError, "without simulation evidence"):
                    run.recover_uvm_report(Path(tmp), uvm(), Path(tmp) / "result", [], {})
                invoke.assert_not_called()

    def test_campaign_with_functional_failures_exits_nonzero_after_reporting(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            run.save(output / "checkpoint.json", {"status": "COMPLETE_WITH_FAILURES"})
            with patch.object(run.batch, "execute", return_value=0) as execute:
                self.assertEqual(run.execute(output), 1)
            execute.assert_called_once_with(output, 8)
            run.save(output / "checkpoint.json", {"status": "PASS"})
            with patch.object(run.batch, "execute", return_value=0):
                self.assertEqual(run.execute(output), 0)

    def test_classification(self):
        self.assertEqual(run.uvm_verdict(1, {"status": "FAIL"}), "FAIL")
        self.assertEqual(run.uvm_verdict(124, None), "RTL_TIMEOUT")
        self.assertEqual(run.uvm_verdict(0, {"status": "PASS"}), "PASS")
        for rc, report in [(1, None), (2, {"status": "FAIL"}), (0, {"status": "FAIL"}), (1, {"status": "PASS"})]:
            with self.assertRaises(ValueError):
                run.uvm_verdict(rc, report)
        with self.assertRaisesRegex(ValueError, "integrity"):
            run.uvm_verdict(1, {"status": "FAIL", "issues": ["cannot read vector trace"]})

    def test_ordinary_batch_failure_returns_zero_and_retains_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            case = uvm(kind="directed")
            case["contract"] = {"oracle": "selfcheck"}
            plan = {"cases": [case]}
            def worker(*args):
                run.save(output / "outcomes/test.json", {"name": "test", "status": "TIMEOUT",
                    "files": {"/old-log": "hash"}, "passed_only": False})
                return 0
            with patch.object(run, "frozen", return_value=plan), patch.object(run.batch, "worker", side_effect=worker), patch.object(run.batch, "publish"):
                self.assertEqual(run.worker(output, "test"), 0)
            item = run.read(output / "outcomes/test.json")
            self.assertEqual(item["status"], "TIMEOUT")
            self.assertEqual(item["files"], {"/old-log": "hash"})
            self.assertEqual(item["origins"], case["origins"])

    def test_dve_keeps_failures_excluded_and_reports_unreviewed_waivers(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            cases = [uvm(name="pass"), uvm(name="fail")]
            for case in cases:
                case["contract"] = run.contract(case)
                passed = case["name"] == "pass"
                item = dict(case, status="PASS" if passed else "FAIL", files={}, reused=False,
                    passed_only=passed, vdb_valid=passed, vdb_files={},
                    vdb=str(output / "results" / case["name"] / "code.vdb"))
                run.save(output / "outcomes" / (case["name"] + ".json"), item)
            plan = {"cases": cases, "image": {"/new/simv": "hash"}, "simv": "/new/simv",
                    "design_vdb": "/new/simv.vdb", "design_files": {}, "dve_outer_timeout_s": 1920,
                    "dve_timeout_s": 1800}
            def invoke(command, log, timeout, env):
                self.assertEqual(command[1], str(run.DVE / "run_dve_coverage.sh"))
                self.assertEqual(env["DVE_WAIVERS"], "auto")
                target = Path(command[2])
                target.mkdir()
                paths = Path(command[-1]).read_text()
                self.assertNotIn("results/fail", paths)
                (target / "inputs.txt").write_text(paths)
                (target / "selected_tests.txt").write_text(str(output / "results/pass/code/test") + "\n")
                (target / "summary.csv").write_text("Name,Line\nara,1\n")
                run.save(target / "waiver_status.json", {"status": "NOT_APPLICABLE_UNREVIEWED_DESIGN"})
                return 0
            with patch.object(run.base, "inventory", return_value={}), patch.object(run.base, "pure_design"), patch.object(run.batch, "valid_vdb", return_value={}), patch.object(run.batch, "invoke", side_effect=invoke):
                outcomes = run.summarize(output, plan)
            self.assertEqual(len(outcomes), 2)
            report = run.read(output / "collection.json")
            self.assertEqual(report["status"], "COMPLETE_WITH_FAILURES")
            self.assertEqual(report["passed"], 1)
            self.assertEqual([c["name"] for c in report["failed_cases_excluded"]], ["fail"])
            self.assertNotIn(str(output / "dve/summary_waived.csv"), report["reports"])

    def test_unapproved_image_cannot_prepare(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "unused"
            freeze = Path(tmp) / "freeze.json"
            run.save(freeze, {"status": "BUILD_PASS"})
            with self.assertRaisesRegex(ValueError, "post-repair"):
                run.prepare(output, run.DEFAULT_PLAN, freeze)
            self.assertFalse(output.exists())

    def test_infrastructure_persists_reason_and_stops_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            with patch.object(run, "frozen", side_effect=ValueError("image drift")), patch.object(run.batch, "publish") as publish:
                self.assertEqual(run.worker(output, "test"), 1)
            outcome = run.read(output / "outcomes/test.json")
            self.assertEqual(outcome["status"], "INFRASTRUCTURE_ERROR")
            self.assertIn("image drift", outcome["reason"])
            publish.assert_called_once()

    def test_old_vdb_rejected_before_dve(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            case = uvm()
            case["contract"] = run.contract(case)
            item = dict(case, files={}, vdb="/old/result/code.vdb", status="PASS")
            run.save(output / "outcomes/test.json", item)
            with patch.object(run.batch, "invoke") as invoke:
                with self.assertRaisesRegex(ValueError, "old/foreign"):
                    run.summarize(output, {"cases": [case]})
                invoke.assert_not_called()


if __name__ == "__main__":
    unittest.main()
