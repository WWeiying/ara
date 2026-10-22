"""Host-only batch policy tests. All external commands are mocked."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_batch_exploration as batch


def plan():
    return {"random": [{"name": f"random-{i}", "profile": f"profile-{i // 20}", "seed": i}
                       for i in range(200)],
            "directed": [{"name": f"directed-{i}", "test": f"rvv:test_{i}"} for i in range(40)]}


class BatchPolicyTests(unittest.TestCase):
    def test_seed1408_isolation_never_swallows_other_timeouts(self):
        row = {"seed": 1409, "test": "ara_dsa_rvv1_load_store_slide_coverage300"}
        outcome = {"status": "INFRASTRUCTURE_ERROR", "reason": "TimeoutExpired: Command test"}
        self.assertIsNone(batch.seed1408_isolation(row, Path("/missing"), outcome, {}))
        row["seed"] = 1408
        self.assertIsNone(batch.seed1408_isolation(row, Path("/missing"), {**outcome, "reason": "checker error"}, {}))

    def test_seed1408_bounded_address_proof_and_elf_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory)
            artifact = result / "tests/ara_dsa_rvv1_load_store_slide_coverage300_0"
            artifact.mkdir(parents=True)
            expected = "5f4b5c985fa9047f2e07ae747763689e45abc8259b77e6bae8402f553376d136"
            batch.save(artifact / "inputs.json", {"binary": {"sha256": expected},
                "simv": {"image_sha256": {"image": "hash"}}, "spike": {"sha256": "spike-hash"}})
            identity = {"image": "image", "spike": "spike", "images": {"image": {"image": "hash"}},
                        "files": {"spike": "spike-hash"}}
            with (artifact / "spike_commit.log").open("wb") as stream:
                stream.write(b"core v20 0x19f4cfaa000000000000000000000000\ncore x23 0x80004cda\n"
                             b"core 0x000000008000129a (0x674be107)\n")
                stream.truncate(2320400384)
            terminal = ("AXI read address 0x0000000099f51c84 exceeds the 2097152-byte simulation L2\n"
                        "requests=507 responses=507 outstanding=0\n")
            for filename in ("rtl_console.log", "run.vcs.log"):
                (artifact / filename).write_text(terminal)
            row = {"seed": 1408, "test": "ara_dsa_rvv1_load_store_slide_coverage300"}
            outcome = {"status": "INFRASTRUCTURE_ERROR", "reason": "TimeoutExpired: Command test"}
            hashes = ["d39c1c4224e9455fbe845b00420d7e35975f11c7f9627aad3df556cc6f76899a",
                      "08797d9f6e95777d77c898123688cc04cdf6da3f656b0705a64ec51203089a66"]
            with patch.object(batch, "sha256", return_value=expected), \
                    patch.object(batch.hashlib, "sha256", side_effect=[Mock(hexdigest=Mock(return_value=h)) for h in hashes]):
                report = batch.seed1408_isolation(row, result, outcome, identity)
                self.assertEqual(report["address"], "0x99f51c84")
                self.assertEqual(report["reference_bytes_inspected"], 2162688)
                self.assertEqual(outcome["status"], "INFRASTRUCTURE_ERROR")
            with patch.object(batch, "sha256", return_value="changed"), self.assertRaisesRegex(RuntimeError, "ELF differs"):
                batch.seed1408_isolation(row, result, outcome, identity)

    def test_recursive_history_pins_and_wrapper_allowlist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old, parent = root / "old", root / "parent"
            old.mkdir()
            parent.mkdir()
            evidence = parent / "audit.json"
            evidence.write_text("original audit")
            common = {key: {} for key in ("image", "generator", "spike", "source_manifest", "sources", "images")}
            identity = {**common, "files": {str(batch.SCRIPT): batch.PRIOR_WRAPPER},
                        "reused_evidence": {str(evidence): batch.sha256(evidence)}}
            batch.save(parent / "identity.json", identity)
            batch.save(old / "continuation.json", {"source": str(parent)})
            batch.save(old / "identity.json", {**identity, "files": {
                str(old / "continuation.json"): batch.sha256(old / "continuation.json")}})
            with patch.object(batch, "OUT", root):
                batch.verify_history(old, common)
                evidence.write_text("tampered")
                with self.assertRaisesRegex(RuntimeError, "historical input/evidence changed"):
                    batch.verify_history(old, common)
                identity["reused_evidence"] = {}
                identity["files"][str(batch.SCRIPT)] = "unknown-wrapper"
                batch.save(parent / "identity.json", identity)
                with self.assertRaises(RuntimeError):
                    batch.verify_history(parent, common)

    def test_precise_preprocessing_rejection_preserves_partial_source(self):
        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory)
            source = result / "asm_test/profile_0.S"
            source.parent.mkdir()
            source.write_text("li s0, 8\njalr gp,a0,831\nvsetvl zero, zero, s0\n")
            log = result / "driver.log"
            message = f"python3 generator.py\nerror: cannot prove vsetvl vtype before indexed store in {source}: vsetvl zero, zero, s0\n"
            log.write_text(message)
            row = {"kind": "random", "test": "profile"}
            before = source.read_bytes()
            probe = result / "spike_probe/spike_vstart_probe.elf"
            probe.parent.mkdir()
            probe.write_bytes(b"probe")
            self.assertEqual(batch.rejected_stimulus(row, result, log, 1)["status"], "REJECTED_STIMULUS")
            self.assertEqual(source.read_bytes(), before)
            for bad in (message + "Traceback (most recent call last)\n", message.replace("cannot prove", "checker failed")):
                log.write_text(bad)
                self.assertIsNone(batch.rejected_stimulus(row, result, log, 1))
            log.write_text(message)
            self.assertIsNone(batch.rejected_stimulus(row, result, log, -9))
            source.write_text("li s0, 8\nvsetvl zero, zero, s0\n")
            self.assertIsNone(batch.rejected_stimulus(row, result, log, 1))
            source.write_bytes(before)
            candidate = result / "candidate.elf"
            candidate.write_bytes(b"case")
            self.assertIsNone(batch.rejected_stimulus(row, result, log, 1))
            candidate.unlink()
            (result / "summary.json").write_text("[]")
            self.assertIsNone(batch.rejected_stimulus(row, result, log, 1))

    def test_reused_evidence_tampering_stops_full_check(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            evidence = output / "evidence"
            evidence.write_text("original")
            batch.save(output / "identity.json", {"files": {}, "reused_evidence": {str(evidence): batch.sha256(evidence)}})
            evidence.write_text("changed")
            with self.assertRaisesRegex(RuntimeError, "reused evidence changed"):
                batch.check_identity(output)

    def test_policy_first_interleaving_preserves_parameters(self):
        rows = [{"kind": "random", "name": "r", "test": "profile", "seed": 1},
                {"kind": "directed", "name": "d", "test": "ordinary"},
                {"kind": "directed", "name": "p", "test": "rvv:vpolicy_type_matrix"}]
        before = json.dumps(rows)
        ordered = batch.scheduling_order(rows)
        self.assertEqual([row["name"] for row in ordered], ["p", "d", "r"])
        self.assertEqual(json.dumps(rows), before)

    def test_noether_schema_and_counts(self):
        profiles = {f"profile-{i}": {"gen_opts": "+instr_cnt=300 +no_csr_instr=1"} for i in range(10)}
        rows = batch.validate_plan(plan(), profiles)
        self.assertEqual(len(rows), 240)
        self.assertEqual(sum(row["kind"] == "random" for row in rows), 200)
        self.assertEqual(sum(row["kind"] == "directed" for row in rows), 40)
        self.assertEqual(rows[0]["test"], "profile-0")
        self.assertEqual(rows[0]["instr_count"], 300)

    def test_rejects_small_duplicate_unbounded_or_ambiguous_batches(self):
        profiles = {f"profile-{i}": {"gen_opts": "+instr_cnt=300"} for i in range(10)}
        for mutation in (lambda p: p["random"].pop(), lambda p: p["directed"].pop(),
                         lambda p: p["random"][1].update(name="random-0"),
                         lambda p: p["random"][1].update(seed=0),
                         lambda p: p["random"][0].update(name="../escape"),
                         lambda p: p["random"][0].update(timeout_s=100000),
                         lambda p: p["directed"][0].update(test="rvv:*")):
            candidate = plan()
            mutation(candidate)
            with self.assertRaises(ValueError):
                batch.validate_plan(candidate, profiles)
        for opts in ("+instr_cnt=301", "", "+instr_cnt=10 +instr_cnt=300"):
            with self.subTest(opts=opts), self.assertRaises(ValueError):
                batch.validate_plan(plan(), {**profiles, "profile-0": {"gen_opts": opts}})

    def test_stale_failfast_policy_rejected_before_freezing(self):
        candidate = plan()
        candidate["policy"] = {"stop_on_any_non_pass": True}
        with self.assertRaisesRegex(ValueError, "stale fail-fast"):
            batch.validate_plan(candidate, {})

    def test_normal_failures_are_case_verdicts(self):
        for status in batch.NORMAL_FAILURES:
            with self.subTest(status=status):
                self.assertEqual(batch.classify({"status": status}, 1), status)
        self.assertEqual(batch.classify({"status": "RTL_STALL", "trace": {"status": "ERROR"}}, 1),
                         "RTL_STALL")
        self.assertEqual(batch.classify({"status": "PASS"}, 0), "PASS")

    def test_corruption_and_unclassified_results_stop(self):
        for row, rc in (({"status": "INPUT_CHANGED"}, 1), ({"status": "TRACE_FAIL"}, 1),
                        ({"status": "SPIKE_FAIL"}, 1), ({"status": "PASS"}, 1),
                        ({"status": "FAIL", "input_errors": ["changed"]}, 1),
                        ({"status": "FAIL", "reason": "simulator executable changed"}, 1),
                        ({"status": "FAIL", "reason": "invalid commit trace: malformed"}, 1),
                        ({"status": "MISMATCH", "comparison": {"status": "ERROR"}}, 1),
                        ({"status": "FAIL"}, -9), ({}, 0)):
            with self.subTest(row=row, rc=rc), self.assertRaises(RuntimeError):
                batch.classify(row, rc)

    def test_commands_use_single_case_and_strict_audits_without_build(self):
        identity = {"image": "/simv", "generator": "/generator", "spike": "/spike"}
        common = {"name": "one", "timeout_s": 900, "spike_timeout_s": 120, "watchdog_cycles": 250000}
        for kind in ("random", "directed", "replay"):
            row = {**common, "kind": kind, "test": "rvv:test", "seed": 3,
                   "summary": "/summary", "case": "old"}
            command, audit = batch.commands(row, identity, Path("/out"))
            self.assertNotIn("make", command)
            if kind == "random":
                self.assertEqual(command[command.index("--iterations") + 1], "1")
                self.assertIn("--vector-commit-compare", command)
                self.assertIn("--generator-simv", command)
            else:
                self.assertEqual(command[command.index("--jobs") + 1], "1")
            if kind == "directed":
                self.assertIn("--skip-build", command)
            else:
                self.assertIn("--require-vector", audit)
                self.assertIn("--require-full-match", audit)


class BatchWorkerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / "verification/out/batch"
        self.output.mkdir(parents=True)
        self.patch("ROOT", self.root)
        self.patch("OUT", self.output.parent)
        self.patch("check_service")
        self.identity = {"image": "/simv", "generator": "/generator", "spike": "/spike",
                         "images": {"/simv": {"/simv": "image"}}, "files": {"/spike": "spike"}}
        self.check = self.patch("check_identity", return_value=self.identity)
        self.invoke = self.patch("invoke")
        self.patch_process = patch.object(batch.subprocess, "run", side_effect=AssertionError("external command"))
        self.patch_process.start()
        self.addCleanup(self.patch_process.stop)
        self.rows = [{"name": name, "kind": "random", "test": "profile", "seed": index,
                      "timeout_s": 900, "spike_timeout_s": 120, "watchdog_cycles": 250000}
                     for index, name in enumerate(("first", "second"))]
        batch.save(self.output / "plan.json", {"cases": self.rows})
        batch.save(self.output / "checkpoint.json", {"status": "PREPARED", "total": 2,
            "completed": 0, "passed": 0, "failed": 0, "infrastructure_errors": 0,
            "cases": {}, "failure_buckets": {}})

    def patch(self, name, *args, **kwargs):
        item = patch.object(batch, name, *args, **kwargs)
        result = item.start()
        self.addCleanup(item.stop)
        return result

    def fake_case(self, status="PASS", audit_pass=True, broken_summary=False):
        def invoke(command, log, timeout):
            result = Path(command[command.index("--output") + 1])
            if "audit" in command:
                batch.save(result, {"status": "PASS" if audit_pass else "FAIL", "errors": []})
                return 0 if audit_pass else 1
            if broken_summary:
                return 1
            artifact = result / "tests/case"
            artifact.mkdir(parents=True)
            elf = artifact / "input.elf"
            elf.write_bytes(b"ELF")
            batch.save(artifact / "inputs.json", {
                "binary": {"sha256": batch.sha256(elf)},
                "simv": {"image_sha256": self.identity["images"]["/simv"]},
                "spike": {"sha256": "spike"}})
            batch.save(result / "summary.json", [{"name": "case", "status": status,
                                                  "artifact_dir": str(artifact)}])
            return 0 if status == "PASS" else 1
        self.invoke.side_effect = invoke

    def state(self):
        return batch.read(self.output / "checkpoint.json")

    def test_failure_then_pass_continues_and_audits_only_pass(self):
        self.fake_case("RTL_STALL")
        self.assertEqual(batch.worker(self.output, "first"), 0)
        self.assertEqual(self.invoke.call_count, 1)
        self.fake_case("PASS")
        self.assertEqual(batch.worker(self.output, "second"), 0)
        self.assertEqual(self.invoke.call_count, 3)
        self.assertEqual(self.state()["completed"], 2)
        self.assertEqual(self.state()["failed"], 1)
        self.assertEqual(self.state()["passed"], 1)
        self.assertEqual(self.state()["failure_buckets"], {"random:profile:RTL_STALL": 1})
        self.assertTrue((self.output / "cases/second/independent_audit.json").exists())
        self.assertIsNone(self.state()["cases"]["first"]["audit"])

    def test_pass_audit_failure_stops_queue(self):
        self.fake_case("PASS", audit_pass=False)
        self.assertEqual(batch.worker(self.output, "first"), 1)
        self.assertEqual(self.state()["status"], "STOPPED")
        self.assertEqual(self.state()["passed"], 0)
        self.assertEqual(self.state()["infrastructure_errors"], 1)

    def test_missing_summary_is_infrastructure_not_a_normal_failure(self):
        self.fake_case(broken_summary=True)
        self.assertEqual(batch.worker(self.output, "first"), 1)
        self.assertEqual(self.state()["status"], "STOPPED")

    def test_hash_failure_prevents_command_dispatch(self):
        self.check.side_effect = RuntimeError("image drift")
        self.assertEqual(batch.worker(self.output, "first"), 1)
        self.invoke.assert_not_called()

    def test_outer_timeout_stops_instead_of_claiming_rtl_timeout(self):
        self.invoke.side_effect = subprocess.TimeoutExpired("verify", 2400)
        self.assertEqual(batch.worker(self.output, "first"), 1)
        self.assertEqual(self.state()["infrastructure_errors"], 1)

    def test_scheduler_success_does_not_relabel_failed_cases_pass(self):
        def scheduler(command, log, timeout):
            self.assertEqual(command[command.index("--jobs") + 1], "5")
            for name, status in (("first", "RTL_TIMEOUT"), ("second", "PASS")):
                batch.publish_case(self.output, name, {"status": status, "bucket": status})
            return 0
        self.invoke.side_effect = scheduler
        self.assertEqual(batch.execute(self.output, 5), 0)
        self.assertEqual(self.state()["status"], "COMPLETE_WITH_FAILURES")
        self.assertEqual(self.check.call_count, 2)
        self.assertTrue((self.output / "functional-plan.json").exists())

    def test_scheduler_failure_never_runs_another_queue(self):
        self.invoke.return_value = 1
        with self.assertRaises(RuntimeError):
            batch.execute(self.output, 5)
        self.invoke.assert_called_once()
        self.assertEqual(self.state()["status"], "STOPPED")

    def test_scheduler_never_dispatches_reused_case(self):
        batch.publish_case(self.output, "first", {"status": "PASS", "bucket": "PASS", "reused": True})
        def scheduler(command, log, timeout):
            scheduled = batch.read(self.output / "functional-plan.json")
            self.assertEqual([row["name"] for row in scheduled], ["second"])
            batch.publish_case(self.output, "second", {"status": "RTL_STALL", "bucket": "RTL_STALL"})
            return 0
        self.invoke.side_effect = scheduler
        self.assertEqual(batch.execute(self.output, 5), 0)
        self.assertEqual(self.state()["completed"], 2)
        self.assertEqual(self.state()["reused"], 1)

    def test_status_is_read_only_and_never_dispatches(self):
        before = (self.output / "checkpoint.json").read_bytes()
        with patch.object(sys, "argv", ["batch", "--output", str(self.output), "--status"]), \
                contextlib.redirect_stdout(io.StringIO()) as stream:
            self.assertEqual(batch.main(), 0)
        self.assertEqual(json.loads(stream.getvalue())["checkpoint"]["status"], "PREPARED")
        self.assertEqual((self.output / "checkpoint.json").read_bytes(), before)
        self.invoke.assert_not_called()
        self.check.assert_not_called()

    def test_environment_errors_are_not_ordinary_rtl_failures(self):
        result = self.output / "cases/first"
        result.mkdir(parents=True)
        (result / "rtl_console.log").write_text("Error: license checkout failed")
        with self.assertRaisesRegex(RuntimeError, "systemic environment"):
            batch.check_environment_logs(result)


if __name__ == "__main__":
    unittest.main()
