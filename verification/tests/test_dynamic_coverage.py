import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ara_verify.artifacts import sha256
from ara_verify.dynamic_coverage import (audit_case, decode_committed_vtype,
                                         vector_writeback_evidence)


class DynamicCoverageTests(unittest.TestCase):
    def test_vector_writeback_counts_checked_and_unknown_bytes_separately(self):
        instructions = {0x1004: (0x020d7007, "vle64.v", "v0,(s10)")}
        result = {"vector_commit": {
            "status": "PASS", "compared_instructions": 2,
            "compared_bytes": 8, "skipped_unknown_bytes": 16,
            "instructions": [
                {"pc": "0x1004", "instruction": "0x020d7007", "status": "PASS",
                 "compared_bytes": 8, "skipped_unknown_bytes": 8},
                {"pc": "0x1004", "instruction": "0x020d7007", "status": "UNOBSERVABLE",
                 "compared_bytes": 0, "skipped_unknown_bytes": 8},
            ]}}
        evidence = vector_writeback_evidence(result, instructions)
        self.assertEqual(evidence["compared_bytes"], 8)
        self.assertEqual(evidence["skipped_unknown_bytes"], 16)
        self.assertEqual(evidence["per_mnemonic"]["vle64.v"], {
            "destination_requests": 2, "requests_with_checked_bytes": 1,
            "compared_bytes": 8, "skipped_unknown_bytes": 16})
        self.assertEqual(vector_writeback_evidence({}, instructions)["status"], "NOT_RUN")
        result["vector_commit"]["compared_bytes"] = 9
        with self.assertRaisesRegex(ValueError, "totals differ"):
            vector_writeback_evidence(result, instructions)
        result["vector_commit"]["compared_bytes"] = 8
        result["vector_commit"]["instructions"][0]["instruction"] = "0x00000057"
        with self.assertRaisesRegex(ValueError, "differs from ELF"):
            vector_writeback_evidence(result, instructions)
        result["vector_commit"]["instructions"][0]["instruction"] = "0x020d7007"
        result["vector_commit"]["instructions"][0]["status"] = "MISMATCH"
        with self.assertRaisesRegex(ValueError, "invalid instruction status"):
            vector_writeback_evidence(result, instructions)

    def make_case(self, root: Path, *, status: str = "PASS") -> Path:
        case = root / "case"
        case.mkdir()
        elf = root / "test.o"
        elf.write_bytes(b"elf")
        (case / "result.json").write_text(json.dumps({
            "status": status, "elf": str(elf),
            "comparison": {"status": "PREFIX", "matched_instructions": 2},
        }), encoding="utf-8")
        (case / "ara_commit_trace.csv").write_text(
            "event,pc,insn,trap\n"
            "retire,0000000000001000,01897d57,0\n"
            "retire,0000000000001004,020d7007,0\n"
            "retire,0000000000001008,00000057,0\n"
            "retire,000000000000100c,00000057,1\n"
            "cvx_resp,0000000000000000,00000000,1\n",
            encoding="utf-8",
        )
        return case

    def test_counts_only_retired_activity_and_keeps_prefix_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = self.make_case(root)
            tool = root / "objdump"
            tool.write_bytes(b"tool")
            decoded = {
                0x1000: (0x01897d57, "vsetvli", "s10,s2,e64,m1,tu,mu"),
                0x1004: (0x020d7007, "vle64.v", "v0,(s10)"),
                0x1008: (0x00000057, "vadd.vv", "v1,v2,v3,v0.t"),
            }
            with patch("ara_verify.dynamic_coverage.disassemble", return_value=decoded):
                report = audit_case(case, tool)
            self.assertEqual(report["dut_retired_vector_instructions"], 3)
            self.assertEqual(report["cvxif_exception_responses"], 1)
            self.assertEqual(report["dut_retired_configurations"], 1)
            self.assertEqual(report["dut_retired_masked_instructions"], 1)
            self.assertEqual(report["memory_modes"], {"unit_stride": 1})
            self.assertEqual(report["sew_lmul_known"], {"e64/m1": 2})
            self.assertEqual(report["resolved_sew_lmul_policy"], {"e64/m1/tu/mu": 2})
            self.assertEqual(report["retired_mnemonic_type_policy"], {
                "vadd.vv/e64/m1/tu/mu": 1, "vle64.v/e64/m1/tu/mu": 1})
            self.assertEqual(report["retired_masked_mnemonic_type_policy"], {
                "vadd.vv/e64/m1/tu/mu": 1})
            self.assertEqual(report["statically_selected_policy_for_retired_nonconfig"],
                             {"tu/mu": 2})
            self.assertEqual(report["statically_selected_policy_for_retired_v0t"],
                             {"tu/mu": 1})
            self.assertEqual(report["retired_nonconfig_with_unknown_policy"], 0)
            self.assertEqual(report["spike_matched_prefix_instructions"], 2)

            trace = case / "ara_commit_trace.csv"
            trace.write_text(trace.read_text().replace(
                "cvx_resp,0000000000000000,00000000,1",
                "cvx_resp,0000000000000000,00000000,x"))
            with patch("ara_verify.dynamic_coverage.disassemble", return_value=decoded):
                with self.assertRaisesRegex(ValueError, "invalid CVXIF response trap bit"):
                    audit_case(case, tool)

    def test_accepts_completed_tohost_comparison_without_prefix_label(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = self.make_case(root)
            result_path = case / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["comparison"].update({
                "status": "TERMINAL_TOHOST_MATCH", "mismatch": None,
                "matched_instructions": 3, "ara_committed_instructions": 3,
                "terminal_tohost": {
                    "pc": "0x1008", "instruction": "0x00000057",
                    "address": "0x2000", "write_value": "0x1",
                },
                "last_matched": {
                    "pc": "0x1008", "instruction": "0x00000057",
                    "memory_accesses": [{"address": "0x2000", "write_value": "0x1"}],
                },
            })
            result_path.write_text(json.dumps(result), encoding="utf-8")
            tool = root / "objdump"
            tool.write_bytes(b"tool")
            decoded = {
                0x1000: (0x01897d57, "vsetvli", "s10,s2,e64,m1,tu,mu"),
                0x1004: (0x020d7007, "vle64.v", "v0,(s10)"),
                0x1008: (0x00000057, "vadd.vv", "v1,v2,v3,v0.t"),
            }
            with patch("ara_verify.dynamic_coverage.disassemble", return_value=decoded):
                report = audit_case(case, tool)
            self.assertEqual(report["evidence_kind"], "random_spike_complete_result")
            self.assertEqual(report["comparison_status"], "TERMINAL_TOHOST_MATCH")

    def test_rejects_failed_case_and_instruction_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = self.make_case(root, status="FAIL")
            tool = root / "objdump"
            tool.write_bytes(b"tool")
            with self.assertRaisesRegex(ValueError, "not PASS"):
                audit_case(case, tool)
            record = json.loads((case / "result.json").read_text())
            record["status"] = "PASS"
            (case / "result.json").write_text(json.dumps(record))
            with patch("ara_verify.dynamic_coverage.disassemble", return_value={
                0x1000: (0x00000057, "vsetvli", "s10,s2,e64,m1,tu,mu")
            }):
                with self.assertRaisesRegex(ValueError, "differs from ELF"):
                    audit_case(case, tool)

    def test_directed_selfcheck_is_not_reported_as_spike_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = root / "tests" / "directed"
            case.mkdir(parents=True)
            elf = case / "input.elf"
            simv = root / "simv"
            tool = root / "objdump"
            for path in (elf, simv, tool):
                path.write_bytes(b"test")
            (root / "summary.json").write_text(json.dumps([
                {"artifact_dir": str(case), "status": "PASS"}
            ]), encoding="utf-8")
            (case / "trace_summary.json").write_text(
                '{"status":"VALID"}', encoding="utf-8"
            )
            (case / "inputs.json").write_text(json.dumps({
                "binary": {"path": str(elf), "sha256": sha256(elf)},
                "simv": {"path": str(simv),
                          "image_sha256": {str(simv): sha256(simv)}},
            }), encoding="utf-8")
            (case / "commit_trace.csv").write_text(
                "event,pc,insn,trap\nretire,1000,01897d57,0\n"
                "retire,1004,020d7007,0\n", encoding="utf-8"
            )
            decoded = {
                0x1000: (0x01897d57, "vsetvli", "s10,s2,e32,m4,tu,mu"),
                0x1004: (0x020d7007, "vlseg2e32.v", "v8,(s10)"),
            }
            with patch("ara_verify.dynamic_coverage.disassemble", return_value=decoded):
                report = audit_case(case, tool)
            self.assertEqual(report["evidence_kind"], "directed_program_selfcheck")
            self.assertEqual(report["comparison_status"], "NOT_RUN")
            self.assertIsNone(report["spike_matched_prefix_instructions"])
            self.assertEqual(report["memory_modes"], {"segment": 1})
            self.assertEqual(report["sew_lmul_known"], {"e32/m4": 1})
            self.assertEqual(report["statically_selected_policy_for_retired_nonconfig"],
                             {"tu/mu": 1})
            self.assertEqual(report["statically_selected_policy_for_retired_v0t"], {})

            elf.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "input identity differs"):
                audit_case(case, tool)

    def test_dynamic_vsetvl_does_not_infer_type_or_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = self.make_case(root)
            tool = root / "objdump"
            tool.write_bytes(b"tool")
            decoded = {
                0x1000: (0x01897d57, "vsetvl", "s10,s2,s3"),
                0x1004: (0x020d7007, "vle64.v", "v0,(s10)"),
                0x1008: (0x00000057, "vadd.vv", "v1,v2,v3,v0.t"),
            }
            with patch("ara_verify.dynamic_coverage.disassemble", return_value=decoded):
                report = audit_case(case, tool)
            self.assertEqual(report["dut_retired_configurations"], 1)
            self.assertEqual(report["configurations_without_static_type"], 1)
            self.assertEqual(report["sew_lmul_known"], {})
            self.assertEqual(report["statically_selected_policy_for_retired_nonconfig"], {})
            self.assertEqual(report["statically_selected_policy_for_retired_v0t"], {})
            self.assertEqual(report["retired_nonconfig_with_unknown_policy"], 2)

    def test_dynamic_vsetvl_uses_prior_committed_rs2_value(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = self.make_case(root)
            (case / "ara_commit_trace.csv").write_text(
                "event,pc,insn,trap,rd,rd_wdata\n"
                "retire,0000000000001000,0c100a13,0,20,00000000000000c1\n"
                "retire,0000000000001004,814579d7,0,19,000000000000002b\n"
                "retire,0000000000001008,020d7007,0,0,0000000000000000\n",
                encoding="utf-8",
            )
            tool = root / "objdump"
            tool.write_bytes(b"tool")
            decoded = {
                0x1004: (0x814579d7, "vsetvl", "s3,a0,s4"),
                0x1008: (0x020d7007, "vle8.v", "v0,(a0)"),
            }
            with patch("ara_verify.dynamic_coverage.disassemble", return_value=decoded):
                report = audit_case(case, tool)
            self.assertEqual(report["configurations_without_static_type"], 1)
            self.assertEqual(report["configurations_inferred_from_committed_gpr"], 1)
            self.assertEqual(report["sew_lmul_known"], {"e8/m2": 1})
            self.assertEqual(report["resolved_sew_lmul_policy"], {"e8/m2/ta/ma": 1})
            self.assertEqual(report["resolved_policy_for_retired_nonconfig"], {"ta/ma": 1})
            self.assertEqual(report["statically_selected_policy_for_retired_nonconfig"], {})
            self.assertEqual(report["retired_nonconfig_with_unknown_policy"], 0)

    def test_runtime_vtype_rejects_reserved_encodings(self):
        self.assertEqual(decode_committed_vtype(0xc1), ("e8/m2", "ta/ma"))
        for raw in (None, 0x1c1, 0x04, 0x20):
            with self.subTest(raw=raw):
                self.assertIsNone(decode_committed_vtype(raw))


if __name__ == "__main__":
    unittest.main()
