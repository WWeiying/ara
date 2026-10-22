import json
from pathlib import Path
import tempfile
import unittest

from unittest.mock import patch

from ara_verify.artifacts import simulation_image
from ara_verify.coverage_matrix import (
    audit_cases, case_image_identity, image_fingerprint, reaudit_prefix_case, summarize_activity,
)


PLAN = {"coverage_dimensions": {
    "sew": ["e8", "e16"], "lmul": ["m1", "m2"],
    "memory_mode": ["unit_stride", "indexed"],
    "tail_policy": ["ta", "tu"], "mask_policy": ["ma", "mu"],
}, "coverage_constraints": {"elen_bits": 64}}


def case(name, kind="random_spike_complete_result", **overrides):
    result = {
        "case": name, "status": "PASS", "evidence_kind": kind,
        "sha256": {"commit_trace": name},
        "memory_modes": {"unit_stride": 2},
        "sew_lmul_known": {"e8/m1": 3},
        "statically_selected_policy_for_retired_nonconfig": {"tu/mu": 3},
        "retired_nonconfig_with_unknown_policy": 1,
        "configurations_without_static_type": 1,
    }
    result.update(overrides)
    return result


class CoverageMatrixTests(unittest.TestCase):
    def test_parallel_audit_preserves_case_order(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ("slow", "fast", "last")]
            with patch("ara_verify.coverage_matrix.audit_case",
                       side_effect=lambda path, objdump: {"case": path.name}):
                self.assertEqual(audit_cases(paths, Path("/objdump"), 3),
                                 [{"case": path.name} for path in paths])
                self.assertEqual(audit_cases(paths, Path("/objdump"), 1),
                                 [{"case": path.name} for path in paths])

    def test_reports_missing_bins_without_claiming_functional_closure(self):
        report = summarize_activity([case("strict"), case("prefix", "random_spike_prefix")], PLAN)
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(len(report["accepted_cases"]), 1)
        self.assertEqual(len(report["excluded_cases"]), 1)
        self.assertEqual(report["axes"]["memory_mode"]["unobserved_bins"], ["indexed"])
        self.assertEqual(report["axes"]["sew"]["bins"]["e8"]["case_count"], 1)
        self.assertEqual(report["unresolved_policy_instructions"], 1)
        self.assertIn("not functional", report["scope"])

    def test_rejects_duplicate_cases_and_unknown_bins(self):
        with self.assertRaisesRegex(ValueError, "duplicate case"):
            summarize_activity([case("same"), case("same")], PLAN)
        with self.assertRaisesRegex(ValueError, "unplanned memory_mode"):
            summarize_activity([case("bad", memory_modes={"segment": 1})], PLAN)

    def test_all_axes_observed_does_not_hide_missing_crosses(self):
        extra = case("directed", "directed_program_selfcheck",
                     memory_modes={"indexed": 1}, sew_lmul_known={"e16/m2": 1},
                     statically_selected_policy_for_retired_nonconfig={
                         "ta/ma": 1, "ta/mu": 1, "tu/ma": 1})
        report = summarize_activity([case("strict"), extra], PLAN)
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertEqual(report["axis_status"], "ACTIVITY_OBSERVED")
        self.assertEqual(report["axes"]["policy_pair"]["observed_bins"], 4)
        self.assertEqual(report["axes"]["memory_mode"]["bins"]["indexed"]["case_count"], 1)

    def test_complete_cross_and_axes_remains_activity_only(self):
        combinations = {
            f"{sew}/{lmul}/{tail}/{mask}": 1
            for sew in ("e8", "e16") for lmul in ("m1", "m2")
            for tail in ("ta", "tu") for mask in ("ma", "mu")
        }
        complete = case("complete", memory_modes={"unit_stride": 1, "indexed": 1},
                        sew_lmul_known={"e8/m1": 1, "e16/m2": 1},
                        statically_selected_policy_for_retired_nonconfig={
                            "ta/ma": 1, "ta/mu": 1, "tu/ma": 1, "tu/mu": 1},
                        resolved_sew_lmul_policy=combinations)
        report = summarize_activity([complete], PLAN)
        self.assertEqual(report["status"], "ACTIVITY_OBSERVED")
        self.assertEqual(report["crosses"]["sew_lmul_policy"]["status"], "OBSERVED")
        self.assertIn("not functional", report["scope"])

    def test_writeback_evidence_is_not_confused_with_activity(self):
        strict = case("strict", vector_writeback_comparison={
            "status": "PASS", "compared_bytes": 8,
            "skipped_unknown_bytes": 24})
        directed = case("directed", "directed_program_selfcheck")
        report = summarize_activity([strict, directed], PLAN)
        self.assertEqual(report["vector_writeback_evidence"]["case_count"], 1)
        self.assertEqual(report["vector_writeback_evidence"]["compared_bytes"], 8)
        self.assertEqual(report["vector_writeback_evidence"]["skipped_unknown_bytes"], 24)
        self.assertIn("not functional coverage",
                      report["vector_writeback_evidence"]["scope"])

    def test_cross_bins_require_same_retired_instruction(self):
        strict = case("strict", resolved_sew_lmul_policy={"e8/m1/tu/mu": 3})
        report = summarize_activity([strict], PLAN)
        cross = report["crosses"]["sew_lmul_policy"]
        self.assertEqual(cross["status"], "INCOMPLETE")
        self.assertEqual(cross["target_bins"], 16)
        self.assertEqual(cross["observed_bins"], 1)
        self.assertEqual(cross["bins"]["e8/m1/tu/mu"]["retired_instructions"], 3)
        self.assertIn("e16/m2/ta/ma", cross["unobserved_bins"])

    def test_unsupported_fractional_lmul_is_excluded(self):
        plan = {"coverage_dimensions": {
            "sew": ["e8", "e64"], "lmul": ["mf8", "m1"],
            "memory_mode": ["unit_stride"],
            "tail_policy": ["ta", "tu"], "mask_policy": ["ma", "mu"],
        }, "coverage_constraints": {"elen_bits": 64}}
        report = summarize_activity([case("strict")], plan)
        cross = report["crosses"]["sew_lmul_policy"]
        self.assertEqual(cross["target_bins"], 12)
        self.assertEqual(len(cross["excluded_illegal_bins"]), 4)
        self.assertIn("e64/mf8/ta/ma", cross["excluded_illegal_bins"])

    def test_prefix_requires_successful_recomputed_terminal_audit(self):
        prefix = case("prefix", "random_spike_prefix")
        with patch("ara_verify.coverage_matrix.audit_terminal_tohost", return_value={
            "status": "FAIL", "issues": ["not complete"]}):
            with self.assertRaisesRegex(ValueError, "terminal re-audit failed"):
                reaudit_prefix_case(prefix, None)
        with patch("ara_verify.coverage_matrix.audit_terminal_tohost", return_value={
            "status": "PASS", "comparison": {"status": "TERMINAL_TOHOST_MATCH"},
            "input_sha256": {"elf": "a"}, "simv_image_sha256": {"simv": "b"},
        }):
            promoted = reaudit_prefix_case(prefix, None)
        self.assertEqual(promoted["evidence_kind"], "random_spike_complete_reaudit")
        self.assertEqual(promoted["terminal_reaudit"]["input_sha256"]["elf"], "a")

    def test_image_groups_do_not_hide_mixed_rtl_evidence(self):
        def with_image(name, fingerprint):
            return case(name, image_identity={
                "fingerprint": fingerprint, "simv_path": f"/{name}/simv",
                "provenance": "recorded_input_manifest",
                "component_count": 3, "config_sha256": "config",
            })

        report = summarize_activity([with_image("a", "image-a"),
                                     with_image("b", "image-b")], PLAN)
        self.assertEqual(report["image_groups"]["status"], "MIXED_OR_UNKNOWN")
        self.assertEqual(report["image_groups"]["group_count"], 2)
        self.assertEqual(report["image_groups"]["groups"]["image-a"]["case_count"], 1)

    def test_image_identity_includes_libraries_and_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identities = []
            for name, library, config in (("a", b"lib", b"cfg"),
                                           ("b", b"lib", b"cfg"),
                                           ("c", b"changed", b"cfg"),
                                           ("d", b"lib", b"changed")):
                image_dir = root / name
                image_dir.mkdir()
                simv = image_dir / "simv"
                simv.write_bytes(b"launcher")
                libraries = image_dir / "simv.daidir"
                libraries.mkdir()
                (libraries / "design.so").write_bytes(library)
                (image_dir / "simulator.conf").write_bytes(config)
                identities.append(image_fingerprint(simv)[0])
            self.assertEqual(identities[0], identities[1])
            self.assertNotEqual(identities[0], identities[2])
            self.assertNotEqual(identities[0], identities[3])

    def test_directed_image_identity_rejects_changed_recorded_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            simv = root / "simv"
            simv.write_bytes(b"launcher")
            libraries = root / "simv.daidir"
            libraries.mkdir()
            (libraries / "design.so").write_bytes(b"original")
            (root / "simulator.conf").write_bytes(b"cfg")
            case_dir = root / "case"
            case_dir.mkdir()
            (case_dir / "inputs.json").write_text(json.dumps({
                "simv": {"path": str(simv), "image_sha256": simulation_image(simv)},
            }), encoding="utf-8")
            self.assertEqual(case_image_identity(case_dir)["provenance"],
                             "recorded_input_manifest")
            (libraries / "design.so").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "recorded simulator image changed"):
                case_image_identity(case_dir)
