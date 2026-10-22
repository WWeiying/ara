import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import report_batch_activity as activity


class BatchActivityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.batch = self.root / "batch"
        self.run = self.batch / "cases" / "directed"
        self.case = self.run / "tests" / "rvv"
        self.case.mkdir(parents=True)
        self.tool = self.root / "objdump"
        self.tool.write_bytes(b"tool")
        self.simv = self.root / "simv"
        self.simv.write_bytes(b"image")
        self.elf = self.case / "input.elf"
        self.elf.write_bytes(b"private ELF")
        self.image = {str(self.simv): activity.digest(self.simv)}
        self.row = {"name": "directed", "kind": "directed", "test": "rvv:fixture",
                    "elf_sha256": activity.digest(self.elf)}
        self.outcome = {"status": "PASS", "returncode": 0, "artifact_dir": str(self.case),
                        "summary": str(self.run / "summary.json"),
                        "audit": str(self.run / "independent_audit.json")}
        self.identity = {"image": str(self.simv), "images": {str(self.simv): self.image}}
        self.proof = {"status": "PROVEN", "fingerprint": "fixture", "simv_path": str(self.simv),
                      "component_count": 1, "config_sha256": "fixture"}
        self.write(self.batch / "identity.json", self.identity)
        self.write(self.batch / "plan.json", {"cases": [self.row, {
            "name": "pending", "kind": "random", "test": "profile", "seed": 601}]})
        self.checkpoint = {"status": "RUNNING", "total": 2, "completed": 1, "passed": 1,
                           "cases": {"directed": self.outcome}}
        self.write(self.batch / "checkpoint.json", self.checkpoint)
        self.write(self.run / "batch_result.json", self.outcome)
        self.write(self.run / "summary.json", [{"name": "rvv", "status": "PASS",
                                                "artifact_dir": str(self.case)}])
        self.write(self.run / "run.json", {"status": "COMPLETE", "invocation": "fixture",
                                           "git": {"commit": "fixture"}})
        self.audit = {"status": "PASS", "errors": [], "case_count": 1,
                      "policy": {"require_complete": True, "require_trace": True},
                      "cases": [{"status": "PASS", "errors": [], "artifact_dir": str(self.case)}]}
        self.write(self.run / "independent_audit.json", self.audit)
        self.write(self.case / "trace_summary.json", {"status": "VALID"})
        self.write(self.case / "command.json", {"command": [str(self.simv)]})
        self.inputs = {"binary": {"path": str(self.elf), "sha256": activity.digest(self.elf)},
                       "simv": {"path": str(self.simv), "image_sha256": self.image}}
        self.write(self.case / "inputs.json", self.inputs)
        # The vtype comes only from retired x5=0x11, not a source vset string.
        self.trace = self.case / "commit_trace.csv"
        self.trace.write_text("event,pc,insn,trap,rd,rd_wdata\n"
                              "retire,1000,01100293,0,5,11\n"
                              "retire,1004,80507057,0,0,0\n"
                              "retire,1008,0081d073,0,0,0\n"
                              "retire,100c,00000057,0,0,0\n"
                              "retire,1010,00000057,1,0,0\n"
                              "issue,1010,00000057,0,0,0\n")
        self.decoded = {0x1004: (0x80507057, "vsetvl", "zero,zero,t0"),
                        0x1008: (0x0081d073, "csrw", "vstart,3"),
                        0x100c: (0x00000057, "vadd.vv", "v0,v0,v0,v0.t"),
                        0x1010: (0x00000057, "vadd.vv", "v0,v0,v0,v0.t")}
        for target in ("report_batch_activity.disassemble", "ara_verify.dynamic_coverage.disassemble"):
            patcher = patch(target, return_value=self.decoded)
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def write(path, data):
        path.write_text(json.dumps(data))

    def run_report(self):
        with patch.object(activity, "prove_identity", return_value=self.proof):
            return activity.report(self.batch, self.tool)

    def make_continuation(self):
        old = self.batch
        wrapper = str(activity.ROOT / "verification/run_batch_exploration.py")
        prior = {**self.identity, "generator": "fixture-generator", "spike": "fixture-spike",
                 "source_manifest": "fixture-manifest", "sources": [{"path": "fixture"}],
                 "files": {wrapper: activity.PRIOR_WRAPPER,
                           str(old / "plan.json"): activity.digest(old / "plan.json")}}
        self.write(old / "identity.json", prior)
        self.checkpoint["status"] = "STOPPED"
        self.write(old / "checkpoint.json", self.checkpoint)
        (old / "logs").mkdir()
        (old / "logs/directed.log").write_text("historical worker log")
        new = self.root / "resumed"
        (new / "reuse-audits").mkdir(parents=True)
        self.write(new / "reuse-audits/directed.json", self.audit)
        self.write(new / "plan.json", activity.read(old / "plan.json"))
        outcome = {**self.outcome, "reused": True, "source_batch": str(old)}
        self.write(new / "checkpoint.json", {**self.checkpoint, "status": "RUNNING",
                                              "cases": {"directed": outcome}})
        self.continuation = {"source": str(old), "wrapper_changes": [{
            "path": wrapper, "before": activity.PRIOR_WRAPPER,
            "after": activity.digest(Path(wrapper))}]}
        self.write(new / "continuation.json", self.continuation)
        evidence = [old / f for f in ("identity.json", "checkpoint.json", "plan.json", "logs/directed.log")]
        evidence += [p for p in self.run.rglob("*") if p.is_file()]
        evidence += [new / "reuse-audits/directed.json"]
        self.identity = {**prior, "files": {wrapper: activity.digest(Path(wrapper)),
                         **{str(new / f): activity.digest(new / f)
                            for f in ("continuation.json", "plan.json")}},
                         "reused_evidence": {str(p): activity.digest(p) for p in evidence}}
        self.write(new / "identity.json", self.identity)
        self.batch = new
        return old

    def update_continuation(self):
        path = self.batch / "continuation.json"
        self.write(path, self.continuation)
        self.identity["files"][str(path)] = activity.digest(path)
        self.write(self.batch / "identity.json", self.identity)

    def test_reused_pass_keeps_old_paths_and_new_provenance(self):
        old = self.make_continuation()
        result = self.run_report()
        self.assertEqual(result["status"], "PARTIAL", result["excluded_batch_cases"])
        self.assertEqual(result["counts"]["accepted"], 1)
        self.assertTrue(result["cases"][0]["reused"])
        self.assertEqual(result["cases"][0]["source_batch"], str(old))
        self.assertIn(str(self.batch / "reuse-audits/directed.json"),
                      result["cases"][0]["evidence_sha256"])
        self.assertFalse((self.batch / "cases/directed/batch_result.json").exists())

    def test_reuse_source_must_match_continuation(self):
        self.make_continuation()
        self.continuation["source"] = str(self.root)
        self.update_continuation()
        self.assertEqual(self.run_report()["status"], "NOT_PROVEN")

    def test_reuse_old_outcome_must_match_without_metadata(self):
        self.make_continuation()
        path = self.batch / "checkpoint.json"
        checkpoint = activity.read(path)
        checkpoint["cases"]["directed"]["returncode"] = 9
        self.write(path, checkpoint)
        result = self.run_report()
        self.assertEqual(result["status"], "NOT_PROVEN")
        self.assertIn("old checkpoint/outcome disagree", result["excluded_batch_cases"][0]["reason"])

    def test_reuse_requires_all_old_artifact_pins(self):
        self.make_continuation()
        del self.identity["reused_evidence"][str(self.trace)]
        self.write(self.batch / "identity.json", self.identity)
        self.assertEqual(self.run_report()["status"], "NOT_PROVEN")

    def test_reuse_rejects_changed_old_trace(self):
        self.make_continuation()
        self.trace.write_text(self.trace.read_text() + "\n")
        self.assertEqual(self.run_report()["status"], "NOT_PROVEN")

    def test_reuse_requires_new_audit(self):
        self.make_continuation()
        (self.batch / "reuse-audits/directed.json").unlink()
        self.assertEqual(self.run_report()["status"], "NOT_PROVEN")

    def test_reuse_new_audit_must_check_same_case_and_policy(self):
        self.make_continuation()
        path = self.batch / "reuse-audits/directed.json"
        audit = activity.read(path)
        audit["policy"]["require_complete"] = False
        self.write(path, audit)
        self.identity["reused_evidence"][str(path)] = activity.digest(path)
        self.write(self.batch / "identity.json", self.identity)
        self.assertEqual(self.run_report()["status"], "NOT_PROVEN")

    def test_reuse_rejects_unauthorized_wrapper_history(self):
        self.make_continuation()
        self.continuation["wrapper_changes"][0]["before"] = "unknown-prior-wrapper"
        self.update_continuation()
        self.assertEqual(self.run_report()["status"], "NOT_PROVEN")

    def test_reuse_rejects_unrecorded_wrapper_change(self):
        self.make_continuation()
        self.continuation["wrapper_changes"] = []
        self.update_continuation()
        self.assertEqual(self.run_report()["status"], "NOT_PROVEN")

    def test_reuse_case_plan_must_match(self):
        self.make_continuation()
        path = self.batch / "plan.json"
        plan = activity.read(path)
        plan["cases"][0]["test"] = "rvv:other"
        self.write(path, plan)
        self.assertEqual(self.run_report()["status"], "NOT_PROVEN")

    def test_reuse_cannot_cross_image_identity(self):
        self.make_continuation()
        self.identity["generator"] = "different-generator"
        self.write(self.batch / "identity.json", self.identity)
        self.assertEqual(self.run_report()["status"], "NOT_PROVEN")

    def test_partial_uses_retired_gpr_vtype_and_explicit_vstart(self):
        result = self.run_report()
        self.assertEqual(result["status"], "PARTIAL")
        self.assertFalse(result["batch_complete"])
        self.assertEqual(result["counts"]["accepted"], 1)
        self.assertEqual(result["axes"]["sew"]["bins"]["e32"]["retired_instructions"], 1)
        self.assertEqual(result["axes"]["lmul"]["bins"]["m2"]["retired_instructions"], 1)
        self.assertEqual(result["axes"]["explicit_vstart"]["observed_bins"], 1)
        self.assertEqual(result["axes"]["explicit_vstart"]["unobserved_bins"], ["linked_known_zero"])
        self.assertEqual(result["mnemonics"]["retired_counts"], {"vadd.vv": 1, "vsetvl": 1})
        self.assertEqual(result["axes"]["mask_operand"]["bins"]["v0.t"]["retired_instructions"], 1)
        self.assertFalse(result["source_generated_activity"]["included"])
        self.assertIsNone(result["mnemonics"]["target_bins"])

    def test_no_observed_types_without_known_runtime_source(self):
        self.trace.write_text(self.trace.read_text().replace(
            "retire,1000,01100293,0,5,11\n", ""))
        result = self.run_report()
        self.assertEqual(result["axes"]["sew"]["observed_bins"], 0)
        self.assertEqual(result["unresolved_vtype_configurations"], 1)

    def test_failed_case_not_parsed_or_counted(self):
        self.checkpoint["cases"]["directed"]["status"] = "VECTOR_MISMATCH"
        self.checkpoint["passed"] = 0
        self.write(self.batch / "checkpoint.json", self.checkpoint)
        with patch.object(activity, "case_activity", side_effect=AssertionError("must not parse FAIL")):
            result = self.run_report()
        self.assertEqual(result["counts"]["accepted"], 0)
        self.assertEqual(result["retired_vector_instructions"], 0)

    def test_complete_with_failures_is_not_batch_pass(self):
        self.checkpoint.update(status="COMPLETE_WITH_FAILURES", completed=2)
        self.checkpoint["cases"]["pending"] = {"status": "RTL_TIMEOUT"}
        self.write(self.batch / "checkpoint.json", self.checkpoint)
        result = self.run_report()
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["campaign_status"], "COMPLETE_WITH_FAILURES")
        self.assertEqual(result["counts"]["accepted"], 1)

    def test_missing_audit_is_not_proven(self):
        (self.run / "independent_audit.json").unlink()
        result = self.run_report()
        self.assertEqual(result["status"], "NOT_PROVEN")
        self.assertEqual(result["counts"]["accepted"], 0)

    def test_other_case_audit_is_rejected(self):
        self.audit["cases"][0]["artifact_dir"] = str(self.run)
        self.write(self.run / "independent_audit.json", self.audit)
        self.assertEqual(self.run_report()["status"], "NOT_PROVEN")

    def test_partial_run_with_pass_summary_is_rejected(self):
        self.write(self.run / "run.json", {"status": "RUNNING"})
        self.assertEqual(self.run_report()["status"], "NOT_PROVEN")

    def test_elf_drift_is_rejected(self):
        self.elf.write_bytes(b"changed ELF")
        self.assertEqual(self.run_report()["status"], "NOT_PROVEN")

    def test_different_image_is_rejected(self):
        self.inputs["simv"]["image_sha256"] = {str(self.simv): "different"}
        self.write(self.case / "inputs.json", self.inputs)
        self.assertEqual(self.run_report()["status"], "NOT_PROVEN")

    def test_global_identity_failure_excludes_every_pass(self):
        with patch.object(activity, "prove_identity", side_effect=ValueError("source drift")):
            result = activity.report(self.batch, self.tool)
        self.assertEqual(result["status"], "NOT_PROVEN")
        self.assertEqual(result["counts"]["accepted"], 0)
        self.assertIn("source drift", result["errors"][0])

    def test_duplicate_plan_names_rejected(self):
        self.write(self.batch / "plan.json", {"cases": [self.row, self.row]})
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.run_report()

    def test_checkpoint_count_mismatch_rejected(self):
        self.checkpoint["passed"] = 2
        self.write(self.batch / "checkpoint.json", self.checkpoint)
        with self.assertRaisesRegex(ValueError, "PASS count"):
            self.run_report()

    def test_prefix_not_accepted_as_complete_activity(self):
        with patch.object(activity, "audit_case", return_value={"evidence_kind": "random_spike_prefix"}):
            result = self.run_report()
        self.assertEqual(result["status"], "NOT_PROVEN")
        self.assertEqual(result["counts"]["accepted"], 0)

    def test_mutating_trace_during_read_rejected(self):
        original = activity.collect_vstart

        def mutate(rows, decoded):
            result = original(rows, decoded)
            self.trace.write_text(self.trace.read_text() + "\n")
            return result

        with patch.object(activity, "collect_vstart", side_effect=mutate):
            self.assertEqual(self.run_report()["status"], "NOT_PROVEN")

    def test_source_inventory_or_image_drift_rejected(self):
        manifest = self.root / "sources.json"
        sources = [{"path": str(self.elf), "sha256": activity.digest(self.elf)}]
        self.write(manifest, {"files": sources, "filelist": "unused", "repo_root": str(self.root),
                              "extra_sources": []})
        config = self.root / "simulator.conf"
        config.write_text("config")
        identity = {**self.identity, "source_manifest": str(manifest), "sources": sources,
                    "files": {str(p): activity.digest(p) for p in
                              (manifest, config, self.batch / "plan.json")}}
        with patch.object(activity, "collect", return_value=sources):
            self.assertEqual(activity.prove_identity(self.batch, identity)["status"], "PROVEN")
        identity["reused_evidence"] = {str(self.trace): "invalid-pin"}
        with self.assertRaisesRegex(ValueError, "reused evidence drift"):
            activity.prove_identity(self.batch, identity)
        del identity["reused_evidence"]
        with patch.object(activity, "collect", return_value=[]):
            with self.assertRaisesRegex(ValueError, "source inventory/hash drift"):
                activity.prove_identity(self.batch, identity)
        self.simv.write_bytes(b"changed")
        with patch.object(activity, "collect", return_value=sources):
            with self.assertRaisesRegex(ValueError, "runtime image drift"):
                activity.prove_identity(self.batch, identity)


if __name__ == "__main__":
    unittest.main()
