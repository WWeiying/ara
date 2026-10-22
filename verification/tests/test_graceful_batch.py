"""Host-only queue tests. No Verilator image or processor simulation is launched."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "coverage"))
import run_graceful_batch as queue


class QueueTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.previous = self.root / "previous"
        (self.previous / "outcomes").mkdir(parents=True)
        self.output = self.root / "new"
        self.output.mkdir()
        self.cases = [{"name": n} for n in ("passed", "failed", "cancelled", "queued")]

    def write_outcome(self, name, status):
        path = self.previous / "outcomes" / f"{name}.json"
        queue.save(path, {"name": name, "status": status})
        return path

    def test_only_complete_outcomes_exclude_dispatch(self):
        self.write_outcome("passed", "PASS")
        self.write_outcome("failed", "FAIL")
        queue.save(self.previous / "replays/cancelled/result.json", {"status": "RUNNING"})
        found, pending = queue.inventory(self.previous, self.cases)
        self.assertEqual(set(found), {"passed", "failed"})
        self.assertEqual(pending, ["cancelled", "queued"])
        rows = queue.scheduler_rows({"pending_names": pending}, self.output)
        self.assertEqual([row["name"] for row in rows], pending)
        self.assertTrue(all(row["command"][-2] == "--worker" for row in rows))

    def test_completed_infrastructure_outcome_also_preserved(self):
        self.write_outcome("failed", "INFRASTRUCTURE_ERROR")
        found, pending = queue.inventory(self.previous, self.cases)
        self.assertIn("failed", found)
        self.assertNotIn("failed", pending)

    def test_unknown_outcome_rejected(self):
        self.write_outcome("unknown", "PASS")
        with self.assertRaises(ValueError):
            queue.inventory(self.previous, self.cases)

    def test_duplicate_case_names_rejected(self):
        with self.assertRaises(ValueError):
            queue.inventory(self.previous, self.cases * 2)

    def test_nonterminal_outcome_rejected(self):
        self.write_outcome("passed", "RUNNING")
        with self.assertRaises(ValueError):
            queue.inventory(self.previous, self.cases)

    def test_unloaded_stopped_service_supported(self):
        output = "LoadState=not-found\nActiveState=inactive\nMainPID=0\nControlPID=0\nControlGroup=\nTasksCurrent=[not set]\n"
        with patch.object(queue.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, output)), \
                patch.object(queue.Path, "glob", return_value=[]):
            self.assertEqual(queue.stopped("old.service")["LoadState"], "not-found")

    def test_live_service_rejected(self):
        output = "LoadState=loaded\nActiveState=active\nMainPID=42\nControlPID=0\nTasksCurrent=3\n"
        with patch.object(queue.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, output)):
            with self.assertRaises(RuntimeError):
                queue.stopped("old.service")

    def test_hidden_nested_session_rejected(self):
        cgroup = self.root / "cgroup"
        cgroup.write_text("0::/user.slice/old.service/child\n")
        output = "LoadState=not-found\nActiveState=inactive\nMainPID=0\nControlPID=0\nControlGroup=\nTasksCurrent=[not set]\n"
        with patch.object(queue.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, output)), \
                patch.object(queue.Path, "glob", return_value=[cgroup]):
            with self.assertRaises(RuntimeError):
                queue.stopped("old.service")

    def test_snapshot_preserves_fail_bytes_and_pending_order(self):
        reference = self.root / "reference.json"
        reference.write_text("{}")
        self.write_outcome("failed", "FAIL")
        path = self.write_outcome("passed", "PASS")
        queue.save(path, {"name": "passed", "status": "PASS", "passed_only": True, "result": str(reference)})
        for name in ("plan.json", "plan.sha256.json", "status.json"):
            (self.previous / name).write_text("{}")
        original = {"batch": str(self.root), "cases": [dict(c, source_status="PASS") for c in self.cases],
                    "files": {}, "coverage": queue.old.SCOPES, "image_sha256": "image",
                    "source_selection": {"original_total": 248, "selected_count": 233,
                                         "excluded": list(range(15)), "original_status": "STOPPED"}}
        with patch.object(queue, "stopped", return_value={"ActiveState": "inactive"}), \
                patch.object(queue.old, "check_inputs", return_value=original), \
                patch.object(queue.old, "check_batch"), \
                patch.object(queue, "inherited_evidence", side_effect=lambda p, *a: queue.old.pin([p])), \
                patch.object(queue.graceful, "reference_points", return_value=(set(), {})), \
                patch.object(queue, "check_inputs"), \
                patch.object(queue.old, "invoke", side_effect=AssertionError("no launch in prepare")):
            queue.prepare(self.previous, "old.service", reference, self.output)
        plan = queue.read(self.output / "plan.json")
        self.assertEqual(plan["pending_names"], ["cancelled", "queued"])
        self.assertEqual(plan["source_selection"], original["source_selection"])
        self.assertEqual(plan["grace_s"], 120)
        self.assertEqual(queue.read(self.output / "status.json")["inherited_counts"], {"PASS": 1, "FAIL": 1})
        for name in ("passed", "failed"):
            self.assertEqual((self.output / f"outcomes/{name}.json").read_bytes(),
                             (self.previous / f"outcomes/{name}.json").read_bytes())

    def test_inventory_drift_rejected(self):
        self.write_outcome("passed", "PASS")
        plan = {"previous": str(self.previous), "cases": self.cases,
                "inherited_names": [], "pending_names": [c["name"] for c in self.cases]}
        with patch.object(queue.old, "check_inputs", return_value=plan):
            with self.assertRaisesRegex(RuntimeError, "inventory changed"):
                queue.check_inputs(self.output)

    def result_fixture(self, status="TIMEOUT"):
        sim, elf, log = [self.output / name for name in ("simv", "input.elf", "sim.log")]
        for path in (sim, elf, log):
            path.write_text(path.name)
        case = {"elf_sha256": queue.sha256(elf), "tohost_addr": None}
        plan = {"image_sha256": queue.sha256(sim), "reference_result": "/reference.json",
                "reporter": "/reporter", "files": {"/reporter": "reporter-hash"}}
        result = {"status": status, "simv": str(sim), "elf": str(elf),
                  "simv_sha256": plan["image_sha256"], "elf_sha256": case["elf_sha256"],
                  "sim_log_sha256": queue.sha256(log), "infrastructure_errors": [],
                  "term_cycles": 100000, "timeout_s": 900, "grace_s": 120, "tohost_addr": None,
                  "reference_result": "/reference.json", "reporter_sha256": "reporter-hash",
                  "timed_out": status == "TIMEOUT", "self_check_pass": True, "sim_returncode": 0,
                  "replay_pass_eligible": status == "PASS", "exploration_eligible": True,
                  "raw_valid": True, "denominator_check": "PASS", "report_returncode": 0}
        path = self.output / "result.json"
        queue.save(path, result)
        return path, case, plan, result

    def test_timeout_even_late_success_never_passed_only(self):
        path, case, plan, _ = self.result_fixture()
        with patch.object(queue.old, "validate_sample", return_value={"valid": True}):
            item = queue.check_result(path, case, plan, 1)
        self.assertEqual(item["status"], "TIMEOUT")
        self.assertTrue(item["raw_valid"])
        self.assertFalse(item["passed_only"])

    def test_denominator_validation_required(self):
        path, case, plan, result = self.result_fixture()
        result["denominator_check"] = "NOT_CHECKED"
        queue.save(path, result)
        with self.assertRaisesRegex(RuntimeError, "denominator"):
            queue.check_result(path, case, plan, 1)

    def test_infrastructure_error_cannot_be_normal_timeout(self):
        path, case, plan, result = self.result_fixture()
        result["infrastructure_errors"] = ["image drift"]
        queue.save(path, result)
        with self.assertRaises(RuntimeError):
            queue.check_result(path, case, plan, 2)

    def test_worker_never_overwrites_inherited_fail(self):
        path = self.output / "outcomes/failed.json"
        queue.save(path, {"name": "failed", "status": "FAIL"})
        before = path.read_bytes()
        with patch.object(queue, "check_inputs", side_effect=AssertionError("no work")):
            self.assertEqual(queue.worker(self.output, "failed"), 1)
        self.assertEqual(path.read_bytes(), before)

    def test_worker_audits_then_continues_after_timeout(self):
        case = {"name": "cancelled", "kind": "random", "summary": str(self.root / "summary.json"),
                "source_status": "PASS", "source_elf": "/original.elf", "elf_sha256": "hash",
                "source_audit": "/original.audit", "source_files": {}}
        plan = {"pending_names": ["cancelled"], "cases": [case]}
        def invoke(command, log, timeout):
            if "audit" in command:
                queue.save(Path(command[command.index("--output") + 1]), {"status": "PASS"})
                self.assertIn("--require-full-match", command)
                return 0
            self.assertEqual(timeout, 1200)
            return 1
        with patch.object(queue, "check_inputs", return_value=plan), \
                patch.object(queue.old, "check_files"), patch.object(queue.old, "validate_audit") as audit, \
                patch.object(queue.old, "invoke", side_effect=invoke), \
                patch.object(queue, "replay_command", return_value=["fake-runner"]), \
                patch.object(queue, "check_result", return_value={"status": "TIMEOUT", "passed_only": False}):
            self.assertEqual(queue.worker(self.output, "cancelled"), 0)
        audit.assert_called_once()
        item = queue.read(self.output / "outcomes/cancelled.json")
        self.assertEqual(item["status"], "TIMEOUT")
        self.assertFalse(item["passed_only"])
        self.assertEqual(queue.sha256(Path(item["source_reaudit"])), item["source_reaudit_sha256"])

    def test_worker_stops_on_drift_before_simulation(self):
        with patch.object(queue, "check_inputs", side_effect=RuntimeError("input drift")), \
                patch.object(queue.old, "invoke") as invoke:
            self.assertEqual(queue.worker(self.output, "cancelled"), 1)
        invoke.assert_not_called()
        self.assertEqual(queue.read(self.output / "outcomes/cancelled.json")["status"], "INFRASTRUCTURE_ERROR")

    def test_replay_budget_and_reference(self):
        command = queue.replay_command({"image": "image", "reporter": "reporter",
                                       "reference_result": "seed601/result.json"},
                                      {"frozen_elf": "elf", "tohost_addr": 0x80001000}, self.output)
        for flag, value in (("--timeout", "900"), ("--grace", "120"), ("--term-cycles", "100000"),
                            ("--reference-result", "seed601/result.json"), ("--tohost-addr", "0x80001000")):
            self.assertEqual(command[command.index(flag) + 1], value)

    def test_merge_separates_timeout_from_strict_pass(self):
        queue.save(self.output / "plan.json", {})
        items = []
        for name, status, valid in (("passed", "PASS", True), ("failed", "FAIL", False),
                                     ("cancelled", "TIMEOUT", True), ("queued", "TIMEOUT", False)):
            item = {"name": name, "status": status, "raw_valid": valid, "passed_only": status == "PASS",
                    "result": f"/{name}/result.json", "result_sha256": "hash",
                    "source_reaudit": "/audit", "source_reaudit_sha256": "hash"}
            queue.save(self.output / f"outcomes/{name}.json", item)
            items.append(item)
        plan = {"cases": self.cases, "inherited_names": ["passed", "failed"], "reporter": "/reporter"}
        with patch.object(queue.old, "check_files"), patch.object(queue.old, "invoke", return_value=0) as invoke:
            self.assertEqual(queue.merge(self.output, plan), items)
        commands = [call.args[0] for call in invoke.call_args_list]
        self.assertIn("/cancelled/result.json", commands[0])
        self.assertNotIn("/cancelled/result.json", commands[1])
        self.assertNotIn("/failed/result.json", commands[0])
        self.assertEqual(len(queue.read(self.output / "exploration/collection.json")["samples"]), 2)
        self.assertEqual(len(queue.read(self.output / "passed-only/collection.json")["samples"]), 1)

    def test_no_pending_skips_supervisor(self):
        self.assertEqual(queue.scheduler_rows({"pending_names": []}, self.output), [])


if __name__ == "__main__":
    unittest.main()
