import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ara_verify.uvm_coverage import (audit_evidence, bins_for, collect,
                                     custom_instruction_activity)


class UvmCoverageTests(unittest.TestCase):
    def test_custom_activity_matches_backend_allocations_and_completions(self):
        with tempfile.TemporaryDirectory() as temporary:
            trace = Path(temporary) / "vector_trace.csv"
            trace.write_text(
                "cycle,event,seq,vid,lane,source,insn\n"
                "1,alloc,1,0,0,0,00b5045b\n"
                "2,alloc,2,0,0,0,00b5605b\n"
                "3,alloc,3,0,0,0,0005745b\n"
                "4,alloc,4,0,0,0,0205375b\n"
                "5,alloc,5,0,0,0,0000505b\n"
                "6,write,3,0,0,0,0005745b\n"
                "7,done,1,0,0,0,00b5045b\n"
                "8,done,2,0,0,0,00b5605b\n"
                "9,done,3,0,0,0,0005745b\n"
                "10,done,4,0,0,0,0205375b\n"
                "11,done,5,0,0,0,0000505b\n", encoding="utf-8")
            activity = custom_instruction_activity(trace)
            self.assertEqual(activity, {
                "qbs_m1": 1, "akv_v2_fill": 1, "akv_v2_column": 1,
                "akv_value_load": 1, "akv_release": 1,
                "qbs_m1_completed": 1, "akv_v2_fill_completed": 1,
                "akv_v2_column_completed": 1, "akv_value_load_completed": 1,
                "akv_release_completed": 1})
            self.assertTrue(all(bins_for({"custom_instruction_activity": activity})[
                name] for name in ("qbs_m1_allocated", "akv_v2_fill_allocated",
                                  "akv_v2_column_allocated",
                                  "akv_value_load_allocated",
                                  "akv_release_allocated", "qbs_m1_completed",
                                  "akv_v2_fill_completed", "akv_v2_column_completed",
                                  "akv_value_load_completed", "akv_release_completed")))

    def test_custom_completion_requires_matching_allocation_in_same_epoch(self):
        with tempfile.TemporaryDirectory() as temporary:
            trace = Path(temporary) / "vector_trace.csv"
            trace.write_text(
                "1,alloc,1,0,0,0,00b5045b\n"
                "2,done,1,0,0,0,0005745b\n"
                "3,reset,0,0,0,0,00000000\n"
                "4,done,1,0,0,0,00b5045b\n"
                "5,alloc,2,0,0,0,0005745b\n"
                "6,done,2,0,0,0,0005745b\n", encoding="utf-8")
            activity = custom_instruction_activity(trace)
            self.assertEqual(activity["qbs_m1"], 1)
            self.assertEqual(activity["qbs_m1_completed"], 0)
            self.assertEqual(activity["akv_v2_column_completed"], 1)

    def test_audit_rejects_changed_input_and_missing_axi_observation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work = root / "work"
            work.mkdir()
            log = work / "run.vcs.log"
            elf = work / "input.elf"
            vector = work / "vector_trace.csv"
            simv = root / "simv"
            log_bytes = b"[DUT_BOUNDARY_CONTRACT] atomic_cvxif=1 b_always_ready=1\n"
            for path, contents in ((log, log_bytes), (elf, b"elf"),
                                   (vector, b"vector"), (simv, b"simv")):
                path.write_bytes(contents)
            image = {str(simv): "image-digest"}
            fresh = {"status": "PASS", "issues": [], "axi_stall_counts": {"ar": 0},
                     "axi_read_counts": {}, "axi_write_counts": {},
                     "coverage_observations": {}, "log_sha256": hashlib.sha256(log_bytes).hexdigest()}
            saved = dict(fresh, sim_image_sha256=image,
                         elf_sha256=hashlib.sha256(b"elf").hexdigest(),
                         vector_trace_sha256=hashlib.sha256(b"vector").hexdigest())
            audit = root / "uvm_result.json"
            audit.write_text(json.dumps(saved), encoding="utf-8")
            with patch("ara_verify.uvm_coverage.simulation_image", return_value=image), \
                 patch("ara_verify.uvm_coverage.check_real_uvm_log", return_value=fresh) as check:
                result, errors = audit_evidence(audit)
                self.assertEqual(errors, [])
                self.assertIs(result, fresh)
                self.assertNotIn("require_axi", check.call_args.kwargs)
                self.assertNotIn("require_axi_write", check.call_args.kwargs)
                log.write_bytes(b"old real-DUT log without boundary assertions")
                digest = hashlib.sha256(log.read_bytes()).hexdigest()
                fresh["log_sha256"] = digest
                saved["log_sha256"] = digest
                audit.write_text(json.dumps(saved), encoding="utf-8")
                result, errors = audit_evidence(audit)
                self.assertIsNone(result)
                self.assertTrue(any("boundary contract assertions" in error
                                    for error in errors))
                log.write_bytes(log_bytes)
                digest = hashlib.sha256(log_bytes).hexdigest()
                fresh["log_sha256"] = digest
                saved["log_sha256"] = digest
                audit.write_text(json.dumps(saved), encoding="utf-8")
                elf.write_bytes(b"changed")
                result, errors = audit_evidence(audit)
                self.assertIsNone(result)
                self.assertTrue(any("ELF" in error for error in errors))
                elf.write_bytes(b"elf")
                fresh["axi_stall_counts"] = None
                result, errors = audit_evidence(audit)
                self.assertIsNone(result)
                self.assertTrue(any("stall summary" in error for error in errors))
                fresh["axi_stall_counts"] = {"ar": 0}
                fresh["axi_read_counts"] = None
                result, errors = audit_evidence(audit)
                self.assertIsNone(result)
                self.assertTrue(any("AXI read summary" in error for error in errors))
                fresh["axi_read_counts"] = {}
                fresh["axi_write_counts"] = None
                result, errors = audit_evidence(audit)
                self.assertIsNone(result)
                self.assertTrue(any("AXI write summary" in error for error in errors))

    def test_missing_observations_cannot_close_bins(self):
        bins = bins_for({"coverage_observations": {
            "axi_read_r_beats": 10, "axi_write_w_beats": 10,
        }, "axi_read_counts": {"aborted": 0, "pending": 0},
            "axi_write_counts": {"aborted": 0, "pending": 0,
                                 "w_bursts": 2, "matched": 2}})
        self.assertFalse(bins["axi_read_multibeat"])
        self.assertFalse(bins["axi_write_multibeat"])
        self.assertFalse(any(bins.values()))

    def test_atomic_cvxif_and_always_ready_b_require_real_traffic(self):
        evidence = {
            "uvm_counts": {"requests": 3, "responses": 3, "immediate": 3,
                           "aborted": 0, "reused": 0},
            "axi_write_counts": {"b": 2},
            "coverage_observations": {"cvxif_requests": 3,
                                      "axi_b_stall_cycles": 0},
        }
        bins = bins_for(evidence)
        self.assertTrue(bins["cvxif_atomic_req_resp"])
        self.assertTrue(bins["axi_b_always_ready"])
        evidence["uvm_counts"]["immediate"] = 2
        evidence["coverage_observations"]["axi_b_stall_cycles"] = 1
        bins = bins_for(evidence)
        self.assertFalse(bins["cvxif_atomic_req_resp"])
        self.assertFalse(bins["axi_b_always_ready"])

    def test_reset_bins_require_matching_audited_mode(self):
        evidence = {
            "coverage_observations": {},
            "axi_read_counts": {"aborted": 1},
            "axi_write_counts": {"aborted": 1},
        }
        self.assertFalse(bins_for(evidence)["axi_reset_aborts_read"])
        self.assertFalse(bins_for(evidence)["axi_reset_aborts_write"])
        evidence["reset_kind"] = "read"
        self.assertTrue(bins_for(evidence)["axi_reset_aborts_read"])
        self.assertFalse(bins_for(evidence)["axi_reset_aborts_write"])
        evidence["reset_kind"] = "write"
        self.assertFalse(bins_for(evidence)["axi_reset_aborts_read"])
        self.assertTrue(bins_for(evidence)["axi_reset_aborts_write"])

    def test_multibeat_requires_clean_completed_bursts(self):
        result = {"coverage_observations": {
            "axi_read_completed": 2, "axi_read_r_beats": 3,
            "axi_write_completed": 2, "axi_write_matched_bursts": 2,
            "axi_write_w_beats": 3,
        }, "axi_read_counts": {"aborted": 0, "pending": 0},
            "axi_write_counts": {"aborted": 0, "pending": 0,
                                 "w_bursts": 2, "matched": 2}}
        self.assertTrue(bins_for(result)["axi_read_multibeat"])
        self.assertTrue(bins_for(result)["axi_write_multibeat"])
        result["axi_read_counts"]["pending"] = 1
        result["axi_write_counts"]["aborted"] = 1
        self.assertFalse(bins_for(result)["axi_read_multibeat"])
        self.assertFalse(bins_for(result)["axi_write_multibeat"])

    def test_smoke_or_missing_evidence_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, errors = audit_evidence(Path(temporary) / "missing.json")
        self.assertIsNone(result)
        self.assertTrue(errors)

    def test_collector_keeps_unhit_bins_incomplete(self):
        with patch("ara_verify.uvm_coverage.audit_evidence", return_value=(
            {"coverage_observations": {"cvxif_requests": 2}, "log_sha256": "abc",
             "sim_image_identity": "image1"}, []
        )):
            report = collect([Path("run/uvm_result.json")])
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(report["run_count"], 1)
        self.assertEqual(report["bin_hits"]["cvxif_request"], 1)
        self.assertIn("axi_ar_backpressure", report["missing_bins"])

    def test_disjoint_images_cannot_fake_coverage_closure(self):
        first = {"sim_image_identity": "image1", "log_sha256": "one",
                 "custom_instruction_activity": {
                     "qbs_m1": 1, "akv_v2_fill": 1, "akv_v2_column": 1,
                     "akv_value_load": 1, "akv_release": 1,
                     "qbs_m1_completed": 1, "akv_v2_fill_completed": 1,
                     "akv_v2_column_completed": 1,
                     "akv_value_load_completed": 1,
                     "akv_release_completed": 1},
                 "uvm_counts": {"requests": 1, "responses": 1, "immediate": 1,
                                "aborted": 0, "reused": 0},
                 "coverage_observations": {
                     "cvxif_requests": 1, "cvxif_immediate_response": 1,
                     "backend_vid_max_live": 2,
                     "axi_read_completed": 1, "axi_read_r_beats": 2,
                     "axi_write_completed": 1, "axi_write_w_beats": 2,
                     "axi_write_matched_bursts": 1,
                     **{f"axi_{channel}_stall_cycles": 1
                        for channel in ("ar", "r", "aw", "w")},
                     "axi_b_stall_cycles": 0,
                 },
                 "axi_read_counts": {"aborted": 0, "pending": 0},
                 "axi_write_counts": {"aborted": 0, "pending": 0, "b": 1,
                                      "w_bursts": 1, "matched": 1}}
        second = {"sim_image_identity": "image2", "log_sha256": "two",
                  "reset_kind": "read",
                  "coverage_observations": {},
                  "axi_read_counts": {"aborted": 1, "pending": 0},
                  "axi_write_counts": {"aborted": 0, "pending": 0}}
        third = {"sim_image_identity": "image2", "log_sha256": "three",
                 "reset_kind": "write",
                 "coverage_observations": {},
                 "axi_read_counts": {"aborted": 0, "pending": 0},
                 "axi_write_counts": {"aborted": 1, "pending": 0}}
        with patch("ara_verify.uvm_coverage.audit_evidence",
                   side_effect=[(first, []), (second, []), (third, [])]):
            report = collect([Path("run/one.json"), Path("run/two.json"),
                              Path("run/three.json")])
        self.assertEqual(report["missing_bins"], [])
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(report["closed_images"], [])
        self.assertEqual(len(report["image_groups"]), 2)


if __name__ == "__main__":
    unittest.main()
