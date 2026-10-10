"""Host-only finisher tests: no build, simulation, or DVE execution."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "coverage"))
import finish_repair_closure_coverage as finish


class FinishCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "control"
        self.source = self.root / "old"
        self.retry = self.source / "results/vlsseg_retry1800"
        self.output.mkdir()
        self.retry.mkdir(parents=True)
        for name, value in (("SOURCE", self.source), ("RETRY", self.retry)):
            patcher = patch.object(finish, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.spec = {"elf": str(self.source / "input.elf"), "elf_sha256": "elfhash", "test": "rvv:vlsseg"}
        self.metadata = {"source": str(self.source), "result": str(self.retry), **self.spec,
                         "timeout_s": 1800, "original_timeout_s": 900, "coverage_test": "vlsseg",
                         "wrapper": str(self.source / "inputs/coverage_simv"),
                         "wrapper_image": {"wrapper": "imagehash"}, "pins": {"script": "hash"}}

    def replay_state(self, **changes):
        finish.save(self.retry / "summary.json", [{"status": "PASS"}])
        state = {"status": "PASS", "result": str(self.retry), "timeout_s": 1800, "coverage_verified": False,
                 "summary_sha256": finish.sha256(self.retry / "summary.json")}
        state.update(changes)
        finish.save(self.output / "replay-status.json", state)

    def test_input_schema_identity(self):
        finish.save(self.output / "replay-inputs.json", self.metadata)
        with patch.object(finish, "check") as check:
            actual = finish.replay_inputs(self.output, {"jobs": {"vlsseg": self.spec}},
                                          {"wrapper_image": self.metadata["wrapper_image"]})
        self.assertEqual(actual, self.metadata)
        self.assertEqual(check.call_count, 2)

    def test_wrong_input_metadata_rejected(self):
        for key, value in (("result", str(self.source / "results/vlsseg")), ("timeout_s", 3600),
                           ("original_timeout_s", 300), ("elf_sha256", "changed"),
                           ("wrapper_image", {}), ("coverage_test", "wrong"), ("test", "rvv:other")):
            with self.subTest(key=key):
                finish.save(self.output / "replay-inputs.json", dict(self.metadata, **{key: value}))
                with patch.object(finish, "check"), self.assertRaises(RuntimeError):
                    finish.replay_inputs(self.output, {"jobs": {"vlsseg": self.spec}},
                                         {"wrapper_image": self.metadata["wrapper_image"]})

    def test_pin_drift_rejected(self):
        finish.save(self.output / "replay-inputs.json", self.metadata)
        with patch.object(finish, "check", side_effect=RuntimeError("pin drift")), self.assertRaises(RuntimeError):
            finish.replay_inputs(self.output, {"jobs": {"vlsseg": self.spec}},
                                 {"wrapper_image": self.metadata["wrapper_image"]})

    def test_wait_accepts_only_completion_not_coverage(self):
        self.replay_state()
        state = finish.wait_replay(self.output, 1)
        self.assertFalse(state["coverage_verified"])
        self.assertFalse((self.output / "summary.json").exists())

    def test_wait_rejects_failure_without_invocation(self):
        self.replay_state(status="FAIL")
        with patch.object(finish.coverage, "invoke") as invoke, self.assertRaises(RuntimeError):
            finish.wait_replay(self.output, 1)
        invoke.assert_not_called()

    def test_wait_checks_summary_hash_result_and_timeout(self):
        for changes in ({"summary_sha256": "bad"}, {"result": "old-timeout"},
                        {"timeout_s": 3600}, {"coverage_verified": True}):
            with self.subTest(changes=changes):
                self.replay_state(**changes)
                with self.assertRaises(RuntimeError):
                    finish.wait_replay(self.output, 1)

    def test_wait_missing_is_bounded(self):
        with patch.object(finish.time, "monotonic", side_effect=[0, 2]), self.assertRaisesRegex(RuntimeError, "exhausted"):
            finish.wait_replay(self.output, 1)

    def test_wait_running_then_pass(self):
        self.replay_state(status="RUNNING")
        with patch.object(finish.time, "sleep", side_effect=lambda _: self.replay_state()) as sleep:
            finish.wait_replay(self.output, 100)
        sleep.assert_called_once()

    def accepted(self):
        items = []
        for name in sorted(finish.campaign.FIRST | finish.campaign.SECOND):
            vdb = (self.retry / "tests/rvv_vlsseg/work/code.vdb" if name == "vlsseg" else
                   self.source / "results" / name / "work/code.vdb")
            items.append({"name": name, "status": "PASS", "admitted": True, "vdb": str(vdb),
                          "coverage_test": name.replace("-", "_"), "vdb_files": {}, "files": {}})
        plan = {"reused": [i for i in items if i["name"] != "vlsseg"], "design_files": {},
                "excluded_timeout_vdb": str(self.source / "results/vlsseg/tests/rvv_vlsseg/work/code.vdb")}
        return plan, next(i for i in items if i["name"] == "vlsseg")

    def test_selection_is_twenty_plus_retry_and_design(self):
        plan, retry = self.accepted()
        with patch.object(finish.coverage, "valid_vdb", return_value={}), \
                patch.object(finish.base, "inventory", return_value={}), patch.object(finish.base, "pure_design"):
            items, databases = finish.selected_databases(plan, retry)
        self.assertEqual(len(items), 21)
        self.assertEqual(len(databases), 22)
        self.assertNotIn(plan["excluded_timeout_vdb"], databases)

    def test_no_timeout_failed_missing_duplicate_or_foreign_vdb(self):
        for corruption in ("timeout", "fail", "missing", "duplicate", "foreign", "hash"):
            plan, retry = self.accepted()
            if corruption == "timeout":
                retry["vdb"] = plan["excluded_timeout_vdb"]
            elif corruption == "fail":
                retry["status"] = "FAIL"
            elif corruption == "missing":
                plan["reused"].pop()
            elif corruption == "duplicate":
                plan["reused"][0] = copy.deepcopy(plan["reused"][1])
            elif corruption == "foreign":
                retry["vdb"] = "/old-image/code.vdb"
            else:
                retry["vdb_files"] = {"changed": "hash"}
            with self.subTest(corruption=corruption), \
                    patch.object(finish.coverage, "valid_vdb", return_value={}), \
                    patch.object(finish.base, "inventory", return_value={}), \
                    patch.object(finish.base, "pure_design"), self.assertRaises(RuntimeError):
                finish.selected_databases(plan, retry)

    def test_bad_selfcheck_prevents_independent_audit(self):
        finish.save(self.retry / "summary.json", [{"status": "TIMEOUT"}])
        with patch.object(finish.coverage, "invoke") as invoke, self.assertRaises(RuntimeError):
            finish.audit_retry(self.output, {"replay": self.metadata})
        invoke.assert_not_called()

    def test_prepare_refuses_existing_finisher_plan(self):
        finish.save(self.output / "finish-plan.json", {"original": True})
        with self.assertRaises(RuntimeError):
            finish.prepare(self.output)
        self.assertEqual(finish.read(self.output / "finish-plan.json"), {"original": True})

    def test_execute_order_wait_audit_merge_only(self):
        (self.root / "verification/out").mkdir(parents=True)
        finish.save(self.output / "finish-status.json", {"status": "PREPARED", "coverage_verified": False})
        calls = []
        with patch.object(finish, "ROOT", self.root), patch.object(finish.base, "check_service"), \
                patch.object(finish, "frozen", return_value={}), \
                patch.object(finish, "wait_replay", side_effect=lambda *a: calls.append("wait")), \
                patch.object(finish, "audit_retry", side_effect=lambda *a: calls.append("audit")), \
                patch.object(finish, "merge", side_effect=lambda *a: calls.append("merge")):
            finish.execute(self.output, 2400)
        self.assertEqual(calls, ["wait", "audit", "merge"])
        self.assertTrue(finish.read(self.output / "finish-status.json")["coverage_verified"])

    def test_failed_audit_never_merges(self):
        (self.root / "verification/out").mkdir(parents=True)
        finish.save(self.output / "finish-status.json", {"status": "PREPARED", "coverage_verified": False})
        with patch.object(finish, "ROOT", self.root), patch.object(finish.base, "check_service"), \
                patch.object(finish, "frozen", return_value={}), patch.object(finish, "wait_replay"), \
                patch.object(finish, "audit_retry", side_effect=RuntimeError("audit failed")), \
                patch.object(finish, "merge") as merge, self.assertRaises(RuntimeError):
            finish.execute(self.output, 2400)
        merge.assert_not_called()
        state = finish.read(self.output / "finish-status.json")
        self.assertEqual(state["status"], "FAIL")
        self.assertFalse(state["coverage_verified"])


if __name__ == "__main__":
    unittest.main()
