import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from final_signoff_report import (audited_cases, check_coverage_closure,
                                 check_incremental_coverage,
                                 check_pair_campaign, check_random_stimulus,
                                 check_rvv_activity, count_audit,
                                 digest, evidence, render_markdown)
import final_signoff_report


class FinalSignoffReportTests(unittest.TestCase):
    def test_markdown_preserves_gate_status_and_evidence(self):
        report = {"status": "INCOMPLETE", "source_commit": "abc",
                  "source_worktree_dirty": True, "source_manifest_sha256": "manifest",
                  "vcs_simv": "/simv",
                  "vcs_simv_sha256": "123", "gates": {"test": {
                      "status": "PENDING", "path": "/audit.json", "expected": "strict audit"}}}
        rendered = render_markdown(report)
        self.assertIn("Overall: **INCOMPLETE**", rendered)
        self.assertIn("Tracked worktree changes: `True`", rendered)
        self.assertIn("| `test` | PENDING | `/audit.json` | strict audit |", rendered)

    def test_missing_and_failed_evidence_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.json"
            self.assertEqual(evidence(path, lambda _: (True, "ok"), "test")["status"],
                             "PENDING")
            path.write_text(json.dumps({"status": "FAIL"}))
            result = evidence(path, lambda value: count_audit(value, 2), "test")
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["sha256"], digest(path))

    def test_case_count_and_errors_are_strict(self):
        value = {"status": "PASS", "case_count": 2, "passed_cases": 2,
                 "failed_cases": 0, "errors": []}
        self.assertTrue(count_audit(value, 2)[0])
        self.assertFalse(count_audit(value, 3)[0])
        value["errors"] = ["bad input"]
        self.assertFalse(count_audit(value, 2)[0])

    def test_audited_case_requires_frozen_elf_and_final_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = root / "case"
            case.mkdir()
            elf = case / "input.elf"
            elf.write_bytes(b"frozen program")
            simv = root / "simv"
            simv.write_bytes(b"final image")
            image = {str(simv): digest(simv)}
            inputs = {"binary": {"path": str(elf), "sha256": digest(elf)},
                      "simv": {"path": str(simv), "image_sha256": image}}
            (case / "inputs.json").write_text(json.dumps(inputs))
            report = root / "audit.json"
            report.write_text(json.dumps({"status": "PASS", "case_count": 1,
                                          "passed_cases": 1, "failed_cases": 0,
                                          "errors": [], "policy": {"require_trace": True}, "cases": [
                                              {"name": "case", "status": "PASS",
                                               "errors": [], "artifact_dir": str(case)}]}))
            with patch.object(final_signoff_report, "VCS", simv):
                self.assertEqual(audited_cases(report, 1, image)["status"], "PASS")
                self.assertEqual(audited_cases(report, 1, image,
                                 ("require_trace", "require_vector", "require_full_match"))["status"],
                                 "FAIL")
                self.assertEqual(audited_cases(report, 1, {str(simv): "wrong"})["status"],
                                 "FAIL")
                elf.write_bytes(b"changed program")
                self.assertEqual(audited_cases(report, 1, image)["status"], "FAIL")

    def test_paired_campaign_rejects_wrong_image_and_changed_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            simv = root / "simv"
            simv.write_bytes(b"final image")
            elf = root / "input.elf"
            elf.write_bytes(b"frozen program")
            model = root / "model.bin"
            model.write_bytes(b"frozen model")
            image = {str(simv): digest(simv)}
            case = {"name": "test", "mode": "rvv", "status": "PASS", "elf": str(elf),
                    "elf_sha256": digest(elf),
                    "app_inputs_sha256": {str(model): digest(model)}}
            plan = {"status": "PASS", "simv": str(simv), "simv_sha256": digest(simv),
                    "cases": [case] * 22}
            pair = {"vcs_image_components": {"simv": digest(simv)}}
            audit = {"status": "PASS", "image_match": True, "issues": [],
                     "qbs_pair_count": 10, "missing_qbs_formats": [],
                     "pairs": {str(i): pair for i in range(11)}}
            with patch.object(final_signoff_report, "VCS", simv):
                self.assertTrue(check_pair_campaign(audit, plan, image)[0])
                pair["vcs_image_components"]["simv"] = "wrong"
                self.assertFalse(check_pair_campaign(audit, plan, image)[0])
                pair["vcs_image_components"]["simv"] = digest(simv)
                model.write_bytes(b"changed model")
                self.assertFalse(check_pair_campaign(audit, plan, image)[0])

    def test_coverage_integrity_does_not_replace_risk_review(self):
        with tempfile.TemporaryDirectory() as directory:
            review = Path(directory) / "review.json"
            review.write_text(json.dumps({"status": "REVIEW_REQUIRED",
                                          "points_total": 100,
                                          "points_missed": 20}))
            closure = {"schema_version": 1, "status": "PASS",
                       "review_sha256": digest(review), "points_total": 100,
                       "points_missed": 20, "reviewer": "verification owner",
                       "risk_decisions": {name: {
                           "disposition": "COVERED", "evidence": "case/audit.json",
                           "rationale": "Targeted branch reached"}
                           for name in ("axi_errors", "mmu_exceptions", "rvv_restart",
                                        "qbs_akv_fallback", "resource_backpressure")}}
            self.assertTrue(check_coverage_closure(closure, review)[0])
            del closure["risk_decisions"]["axi_errors"]
            self.assertFalse(check_coverage_closure(closure, review)[0])
            closure["risk_decisions"]["axi_errors"] = {
                "disposition": "COVERED", "evidence": "case/audit.json",
                "rationale": "Targeted branch reached"}
            review.write_text(json.dumps({"points_total": 100, "points_missed": 19}))
            self.assertFalse(check_coverage_closure(closure, review)[0])

    def test_incremental_coverage_requires_qbs_case_and_matching_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            merged_dir = root / "integrated-coverage-pass13-qbs-control-20260925-01"
            merged_dir.mkdir()
            simv = root / "simv"
            simv.write_bytes(b"coverage image")
            qbs_result = (root / "integrated-qbs-control-coverage-20260925-01" /
                          "app_qbs_control_smoke/result.json")
            cases = [{"result": str(root / f"case-{i}.json")} for i in range(12)]
            cases.append({"result": str(qbs_result)})
            merge = merged_dir / "audit.json"
            merge.write_text(json.dumps({"status": "PASS", "cases": cases,
                                         "hierarchy_coverage": {"points_hit": 19799}}))
            (merged_dir / "review.json").write_text(json.dumps({
                "status": "REVIEW_REQUIRED", "case_count": 13,
                "merge_audit_sha256": digest(merge)}))
            value = {"status": "PASS", "case_count": 13, "issues": [],
                     "simv_sha256": digest(simv), "merge_audit_sha256": digest(merge)}
            self.assertTrue(check_incremental_coverage(value, merged_dir, simv)[0])
            cases[-1] = {"result": str(root / "unrelated.json")}
            merge.write_text(json.dumps({"status": "PASS", "cases": cases,
                                         "hierarchy_coverage": {"points_hit": 19799}}))
            value["merge_audit_sha256"] = digest(merge)
            (merged_dir / "review.json").write_text(json.dumps({
                "status": "REVIEW_REQUIRED", "case_count": 13,
                "merge_audit_sha256": digest(merge)}))
            self.assertFalse(check_incremental_coverage(value, merged_dir, simv)[0])
            cases[-1] = {"result": str(qbs_result)}
            merge.write_text(json.dumps({"status": "PASS", "cases": cases,
                                         "hierarchy_coverage": {"points_hit": 19799}}))
            value["merge_audit_sha256"] = digest(merge)
            (merged_dir / "review.json").write_text(json.dumps({
                "status": "REVIEW_REQUIRED", "case_count": 13,
                "merge_audit_sha256": digest(merge)}))
            simv.write_bytes(b"different image")
            self.assertFalse(check_incremental_coverage(value, merged_dir, simv)[0])

    def test_random_stimulus_cannot_pass_on_counts_without_frozen_cases(self):
        report = {"status": "PASS", "profile_count": 7,
                  "audited_profile_count": 7, "profiles": [],
                  "merged": {"source_count": 70, "vector_instruction_count": 100,
                             "aggregate": {"sew": {name: 1 for name in
                                                   ("e8", "e16", "e32", "e64")},
                                           "lmul": {name: 1 for name in
                                                    ("mf8", "mf4", "mf2", "m1",
                                                     "m2", "m4", "m8")}}}}
        self.assertFalse(check_random_stimulus(report)[0])

    def test_rvv_activity_requires_final_image_full_union_and_unchanged_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            simv = root / "simv"
            simv.write_bytes(b"simulator")
            reports = {}
            for name in ("random", "policy"):
                path = root / f"{name}.json"
                path.write_text("{}")
                reports[f"{name}_report"] = str(path)
                reports[f"{name}_report_sha256"] = digest(path)
            axes = {name: {"target_bins": count, "observed_bins": count,
                           "unobserved_bins": []}
                    for name, count in (("sew", 4), ("lmul", 7),
                                        ("memory_mode", 7), ("policy_pair", 4))}
            value = {"status": "ACTIVITY_OBSERVED", "case_count": 71,
                     "random_case_count": 70, "directed_case_count": 1,
                     "axes": axes, "sew_lmul_policy": {
                         "target_bins": 88, "observed_bins": 88,
                         "unobserved_bins": []}, **reports}
            with patch.object(final_signoff_report, "VCS", simv), patch.object(
                    final_signoff_report, "image_fingerprint", return_value=("final", 1, None)):
                value["image_fingerprint"] = "final"
                self.assertTrue(check_rvv_activity(value)[0])
                value["axes"]["policy_pair"]["observed_bins"] = 3
                self.assertFalse(check_rvv_activity(value)[0])
                value["axes"]["policy_pair"]["observed_bins"] = 4
                (root / "policy.json").write_text('{"changed": true}')
                self.assertFalse(check_rvv_activity(value)[0])


if __name__ == "__main__":
    unittest.main()
