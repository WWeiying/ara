import json
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ara_verify.catalog import load_catalog
from ara_verify.plan import (PlanError, _full_vector_match, _load_fault_evidence_errors,
                             audit_run, load_plan, validate_plan)
from ara_verify.stimulus_coverage import write_stimulus_coverage
from fpga.check_run import check_manifest as check_fpga_manifest
from linux.check_boot import check_boot


ROOT = Path(__file__).resolve().parents[2]


class VerificationPlanTests(unittest.TestCase):
    @staticmethod
    def _partial_load_proof():
        return {"arch_seq": 126, "index": 100, "pc": "0x800005c2", "instruction": "0xeece8a07",
                "vstart_before": 1, "vstart_after": 2, "probe_next_time": 20720000,
                "expected_fault_csrs": {"0x341": 0x800005c2, "0x342": 4, "0x343": 0x800050d1},
                "accepted_byte_events": 928, "final_written_bytes": 900,
                "required_load_bytes": 32, "verified_load_bytes": 32,
                "maintenance_bytes": 896, "preserved_unknown_bytes": 0,
                "duplicate_bytes": 28, "full_destination_bytes": 1024,
                "inputs": {str(i): "a" * 64 for i in range(4)}}

    def test_full_vector_match_recognizes_only_complete_probed_faults(self):
        proof = self._partial_load_proof()
        vector = {"status": "PASS", "vector_destination_requests": 3,
                  "prefix_vector_destination_requests": 3, "compared_instructions": 2,
                  "trapped_requests": [126], "verified_trapped_destination_requests": [126],
                  "verified_probed_load_faults": [proof]}
        self.assertTrue(_full_vector_match(vector))
        for key, value in (("required_load_bytes", 33), ("verified_load_bytes", 0),
                           ("preserved_unknown_bytes", 1), ("vstart_after", 1),
                           ("duplicate_bytes", 29), ("inputs", {}),
                           ("expected_fault_csrs", {}), ("maintenance_bytes", -1)):
            with self.subTest(key=key):
                self.assertFalse(_full_vector_match({**vector,
                    "verified_probed_load_faults": [{**proof, key: value}]}))
        self.assertFalse(_full_vector_match({**vector, "verified_zero_write_traps": [126]}))
        self.assertFalse(_full_vector_match({**vector, "verified_probed_load_faults": [proof, proof]}))
        impossible = {**proof, "required_load_bytes": 1, "verified_load_bytes": 1,
                      "accepted_byte_events": 897, "final_written_bytes": 896, "duplicate_bytes": 1}
        self.assertFalse(_full_vector_match({**vector, "verified_probed_load_faults": [impossible]}))

    def test_probed_fault_audit_checks_scalar_binding_and_original_trace_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proof = self._partial_load_proof()
            proof["inputs"] = {}
            for name in ("spike_commit.log", "ara_commit_trace.csv", "ara_vector_trace.csv", "run.vcs.log"):
                path = root / name
                path.write_bytes(name.encode())
                proof["inputs"][str(path.resolve())] = hashlib.sha256(path.read_bytes()).hexdigest()
            vector = {"verified_probed_load_faults": [proof]}
            scalar = {"aligned_vector_faults": [{"load_fault_proof": copy.deepcopy(proof),
                       **{key: proof[key] for key in ("index", "pc", "instruction")},
                       "matched_fault_csrs": copy.deepcopy(proof["expected_fault_csrs"])}]}
            self.assertEqual(_load_fault_evidence_errors(root, scalar, vector), [])
            self.assertTrue(_load_fault_evidence_errors(root, {}, vector))
            damaged = copy.deepcopy(scalar)
            damaged["aligned_vector_faults"][0]["matched_fault_csrs"]["0x342"] = 5
            self.assertTrue(_load_fault_evidence_errors(root, damaged, vector))
            for key in ("index", "pc", "instruction"):
                for missing in (False, True):
                    damaged = copy.deepcopy(scalar)
                    if missing:
                        del damaged["aligned_vector_faults"][0][key]
                    else:
                        damaged["aligned_vector_faults"][0][key] = "incorrect"
                    self.assertTrue(_load_fault_evidence_errors(root, damaged, vector))
            for value in (None, 3, {}):
                self.assertTrue(_load_fault_evidence_errors(root, {"aligned_vector_faults": value}, vector))
            (root / "run.vcs.log").write_text("changed")
            self.assertTrue(_load_fault_evidence_errors(root, scalar, vector))

    def test_full_vector_match_requires_evidence_for_trapped_destination(self):
        vector = {
            "status": "PASS", "selected_index": None,
            "stopped_at_spike_index": None,
            "vector_destination_requests": 3,
            "prefix_vector_destination_requests": 3,
            "compared_instructions": 2,
            "incomplete_requests": [], "unretired_requests": [],
            "trapped_requests": [7],
            "verified_identity_write_traps": [{"arch_seq": 7, "compared_bytes": 256}],
            "verified_trapped_destination_requests": [7],
        }
        self.assertTrue(_full_vector_match(vector))
        for field, value in (
            ("trapped_requests", []),
            ("verified_identity_write_traps", []),
            ("verified_trapped_destination_requests", [7, 7]),
            ("compared_instructions", 1),
        ):
            with self.subTest(field=field, value=value):
                self.assertFalse(_full_vector_match({**vector, field: value}))

    @staticmethod
    def _audit_fixture(root: Path, comparison: dict, vector: dict) -> Path:
        artifact = root / "tests" / "case"
        artifact.mkdir(parents=True)
        for name, payload in (
            ("rtl.command.json", {}),
            ("trace_summary.json", {"status": "VALID"}),
            ("commit_comparison.json", comparison),
            ("vector_commit_comparison.json", vector),
        ):
            (artifact / name).write_text(json.dumps(payload), encoding="utf-8")
        (root / "run.json").write_text(json.dumps({
            "status": "COMPLETE", "invocation": ["run"], "git": {"commit": "abc"},
        }), encoding="utf-8")
        (root / "summary.json").write_text(json.dumps([{
            "name": "random_0", "status": "PASS", "artifact_dir": str(artifact),
        }]), encoding="utf-8")
        return artifact

    def test_plan_references_current_catalog(self):
        catalog = load_catalog(ROOT, ROOT / "verification/suites.json")
        summary = validate_plan(catalog, load_plan(ROOT / "verification/verification_plan.json"))
        self.assertEqual(summary["status"], "VALID")
        self.assertEqual(summary["requirement_count"], 13)
        self.assertEqual(summary["random_profile_count"], 8)
        self.assertEqual(summary["linux_level_count"], 3)
        self.assertGreater(summary["coverage_dimensions"]["lmul"].__len__(), 1)
        self.assertEqual(summary["coverage_constraints"]["elen_bits"], 64)

    def test_masked_indexed_requirement_selects_load_store_and_fault(self):
        catalog = load_catalog(ROOT, ROOT / "verification/suites.json")
        names = [test.name for test in catalog.resolve_suite("rvv-masked-indexed")]
        self.assertEqual(names, [
            "rvv:vmasked_indexed_alignment",
            "rvv:vmasked_indexed_store_alignment",
            "rvv:vindexed_fault_vstart",
        ])
        summary = validate_plan(catalog, load_plan(ROOT / "verification/verification_plan.json"))
        requirement = next(item for item in summary["requirements"]
                           if item["id"] == "RVV-MASKED-INDEXED")
        self.assertEqual(requirement["test_count"], 3)
        self.assertEqual(requirement["risk"], "critical")

    def test_linux_fast_prereq_selects_distinct_directed_cases(self):
        catalog = load_catalog(ROOT, ROOT / "verification/suites.json")
        names = [test.name for test in catalog.resolve_suite("linux-fast-prereq")]
        self.assertEqual(names, [
            "rvv:linux_state_prereq",
            "rvv:stvec_readback",
            "rvv:trap_state_prereq",
            "rvv:sv39_state_prereq",
            "rvv:linux_mmu_relocate",
            "rvv:linux_vector_context",
        ])

    def test_plan_rejects_invalid_elen_constraint(self):
        catalog = load_catalog(ROOT, ROOT / "verification/suites.json")
        plan = load_plan(ROOT / "verification/verification_plan.json")
        plan["coverage_constraints"] = {"elen_bits": 48}
        with self.assertRaisesRegex(PlanError, "elen_bits"):
            validate_plan(catalog, plan)

    def test_audit_rejects_non_pass_and_missing_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "tests" / "case"
            artifact.mkdir(parents=True)
            (artifact / "command.json").write_text("{}\n", encoding="utf-8")
            (root / "run.json").write_text(
                '{"status":"COMPLETE","invocation":["run"],'
                '"git":{"commit":"abc"}}\n', encoding="utf-8"
            )
            (root / "summary.json").write_text(json.dumps([{
                "name": "rvv:case",
                "status": "PASS",
                "artifact_dir": str(artifact),
            }]) + "\n", encoding="utf-8")
            result = audit_run(root, require_trace=True, require_vector=True)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["failed_cases"], 1)

    def test_audit_accepts_complete_vector_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "tests" / "case"
            artifact.mkdir(parents=True)
            (artifact / "rtl.command.json").write_text("{}\n", encoding="utf-8")
            (artifact / "trace_summary.json").write_text(
                '{"status":"VALID"}\n', encoding="utf-8"
            )
            (artifact / "commit_comparison.json").write_text(
                '{"status":"MATCH"}\n', encoding="utf-8"
            )
            (artifact / "vector_commit_comparison.json").write_text(
                '{"status":"PASS"}\n', encoding="utf-8"
            )
            (root / "run.json").write_text(
                '{"status":"COMPLETE","invocation":["run"],'
                '"git":{"commit":"abc"}}\n', encoding="utf-8"
            )
            (root / "summary.json").write_text(json.dumps([{
                "name": "random_0",
                "status": "PASS",
                "artifact_dir": str(artifact),
            }]) + "\n", encoding="utf-8")
            result = audit_run(root, require_trace=True, require_vector=True)
            self.assertEqual(result["status"], "PASS")

    def test_profile_coverage_rechecks_generated_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._audit_fixture(root, {"status": "MATCH"}, {"status": "PASS"})
            asm = root / "asm_test"
            asm.mkdir()
            (asm / "random_0.S").write_text(
                ".section .text\nmain:\n  vsetvli x1, x2, e32,m1,ta,ma\n"
                "  vadd.vv v1, v2, v3\ntest_done:\n", encoding="utf-8",
            )
            path = write_stimulus_coverage(root, "random")
            self.assertEqual(audit_run(root, require_coverage=True)["status"], "PASS")
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["vector_instruction_count"] += 1
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = audit_run(root, require_coverage=True)
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("stimulus coverage differs", str(result["errors"]))

    def test_strict_match_rejects_unobservable_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._audit_fixture(root, {
                "status": "PREFIX", "mismatch": None,
                "matched_instructions": 20, "ara_committed_instructions": 100,
                "stopped_at_unobservable": {"index": 20},
            }, {"status": "PREFIX"})
            result = audit_run(root, require_full_match=True)
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("architectural comparison stops", str(result["errors"]))
            self.assertIn("full vector-state evidence", str(result["errors"]))

            comparison = {
                "status": "PREFIX", "mismatch": None,
                "matched_instructions": 100, "ara_committed_instructions": 100,
                "stopped_at_unobservable": None,
            }
            vector = {
                "status": "PASS", "selected_index": None,
                "stopped_at_spike_index": None,
                "vector_destination_requests": 12,
                "prefix_vector_destination_requests": 12,
                "compared_instructions": 12,
                "incomplete_requests": [], "unretired_requests": [],
            }
            (artifact / "commit_comparison.json").write_text(json.dumps(comparison), encoding="utf-8")
            (artifact / "vector_commit_comparison.json").write_text(json.dumps(vector), encoding="utf-8")
            self.assertEqual(audit_run(root, require_full_match=True)["status"], "FAIL")

            comparison["status"] = "TERMINAL_MATCH"
            comparison["terminal_ecall"] = {
                "pc": "0x0000000080003e70", "instruction": "0x00000073", "trap": True,
            }
            (artifact / "commit_comparison.json").write_text(json.dumps(comparison), encoding="utf-8")
            (artifact / "rtl.command.json").write_text(json.dumps({
                "command": ["simv", "+COMMIT_EXIT_PC=0000000080003e70"],
            }), encoding="utf-8")
            self.assertEqual(audit_run(root, require_full_match=True)["status"], "PASS")

            (artifact / "rtl.command.json").write_text(json.dumps({
                "command": ["simv", "+COMMIT_EXIT_PC=0000000080003e74"],
            }), encoding="utf-8")
            wrong_exit = audit_run(root, require_full_match=True)
            self.assertEqual(wrong_exit["status"], "FAIL")
            self.assertIn("terminal ecall does not match", str(wrong_exit["errors"]))
            (artifact / "rtl.command.json").write_text(json.dumps({
                "command": ["simv", "+COMMIT_EXIT_PC=0000000080003e70"],
            }), encoding="utf-8")

            vector["selected_index"] = 1
            (artifact / "vector_commit_comparison.json").write_text(json.dumps(vector), encoding="utf-8")
            self.assertEqual(audit_run(root, require_full_match=True)["status"], "FAIL")

    def test_terminal_recompute_requires_full_match(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(PlanError, "requires full-match"):
                audit_run(Path(directory), recompute_terminal_tohost=True)

    def test_terminal_recompute_rejects_failed_raw_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._audit_fixture(root, {
                "status": "PREFIX", "mismatch": None,
                "matched_instructions": 1, "ara_committed_instructions": 2,
            }, {"status": "PREFIX"})
            with patch("ara_verify.terminal_reaudit.audit", return_value={
                "status": "FAIL", "issues": ["raw trace does not reach tohost"],
            }):
                result = audit_run(root, require_full_match=True,
                                   recompute_terminal_tohost=True)
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("raw trace does not reach tohost", str(result["errors"]))
            self.assertEqual(result["cases"][0]["terminal_reaudit"]["status"], "FAIL")

    def test_strict_tohost_requires_matching_command_and_success_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = self._audit_fixture(root, {
                "status": "TERMINAL_TOHOST_MATCH", "mismatch": None,
                "matched_instructions": 10, "ara_committed_instructions": 10,
                "stopped_at_unobservable": None,
                "terminal_tohost": {
                    "pc": "0x0000000080001000", "instruction": "0x00102023",
                    "address": "0x0000000080003000", "write_value": "0x1",
                },
                "last_matched": {
                    "pc": "0x0000000080001000", "instruction": "0x00102023",
                    "memory_accesses": [{"address": "0x0000000080003000",
                                         "write_value": "0x1"}],
                },
            }, {
                "status": "PASS", "selected_index": None,
                "stopped_at_spike_index": None,
                "vector_destination_requests": 2,
                "prefix_vector_destination_requests": 2,
                "compared_instructions": 2,
                "incomplete_requests": [], "unretired_requests": [],
            })
            (artifact / "rtl.command.json").write_text(json.dumps({
                "command": ["simv", "+COMMIT_TOHOST=0000000080003000"],
            }), encoding="utf-8")
            self.assertEqual(audit_run(root, require_full_match=True)["status"], "FAIL")
            (artifact / "rtl_console.log").write_text("Core Test *** SUCCESS ***\n",
                                                        encoding="utf-8")
            self.assertEqual(audit_run(root, require_full_match=True)["status"], "PASS")
            (artifact / "rtl.command.json").write_text(json.dumps({
                "command": ["simv", "+COMMIT_TOHOST=0000000080003008"],
            }), encoding="utf-8")
            self.assertEqual(audit_run(root, require_full_match=True)["status"], "FAIL")


class LinuxBootCheckTests(unittest.TestCase):
    def test_requires_all_boot_markers_and_hashes_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "console.log"
            payload = root / "Image"
            log.write_text(
                "OpenSBI\nLinux version 6.x\n"
                "Ara DSA VCU118 Linux init reached\n"
                "Linux console, DDR and RVV handoff are alive\n",
                encoding="utf-8",
            )
            payload.write_bytes(b"payload")
            result = check_boot(log, list((
                "OpenSBI", "Linux version", "Ara DSA VCU118 Linux init reached",
                "Linux console, DDR and RVV handoff are alive",
            )), {"kernel": payload})
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(len(result["artifacts"]["kernel"]), 64)


class FpgaManifestTests(unittest.TestCase):
    def test_rejects_unverified_or_mismatched_board_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bitstream = root / "design.bit"
            software = root / "Image"
            console = root / "uart.log"
            bitstream.write_bytes(b"bitstream")
            software.write_bytes(b"Image")
            console.write_text("OpenSBI\nLinux version\n", encoding="utf-8")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "board": "VCU118",
                "bitstream_tool": "Vivado",
                "vivado_version": "2025.1",
                "rtl_commit": "abc",
                "clock_mhz": 100,
                "ddr_calibration": True,
                "reset_uart_smoke": True,
                "artifacts": {
                    "bitstream": {"path": str(bitstream)},
                    "software": {"path": str(software)},
                },
                "console_log": str(console),
                "console_markers": ["OpenSBI", "Linux version"],
                "tests": [{"name": "rvv_fallback", "status": "PASS"}],
            }) + "\n", encoding="utf-8")
            result = check_fpga_manifest(manifest)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(len(result["artifacts"]["bitstream"]["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
