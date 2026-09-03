#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("analyze_prefill_matrix.py")
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("analyze_prefill_matrix", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


def fake_summary(case_path: Path, _query_tiles: list[int]) -> dict:
    case = json.loads(case_path.read_text(encoding="utf-8"))
    past = case["P"]
    tokens = case["M"]
    common_strategy = lambda name, value: {"name": name, "external_kv_bytes": value}
    return {
        "shape": {
            "past_tokens": past,
            "query_tokens": tokens,
            "head_dim": 128,
            "query_heads": 12,
            "kv_heads": 2,
            "gqa_rows": 6,
            "kv_capacity": past + tokens,
        },
        "work": {"attention_macs": 1234},
        "payload": {
            "query_f32_bytes": 10,
            "mask_physical_bytes": 20,
            "output_f32_bytes": 30,
            "unique_visible_kv_bytes": 40,
        },
        "kv_outer_q2_exact": {
            "external_kv_bytes": 50,
            "replay_bytes": 60,
            "command_records": 70,
        },
        "kv_outer_q2_panel4_exact": {
            "external_kv_bytes": 50,
            "replay_bytes": 60,
            "command_records": 25,
            "v2_column_panel": 5,
            "v2_logical_column": 20,
            "v2_k_view_bank_cycles": 10,
        },
        "kv_outer_q2_panel4_vslice64_exact": {
            "implemented_fast_path": False,
            "supported_shape": True,
            "retention_status": "REJECTED_M15_RTL_REGRESSION",
            "external_kv_bytes": 50,
            "replay_bytes": 45,
            "row_replay_bytes": 15,
            "command_records": 25,
            "v2_row_load": 12,
            "q2_shared_v_rows": 4,
            "single_query_v_rows": 4,
            "row_busy_cycle_model": {"saved_row_busy_cycles": 96},
        },
        "strategies": [
            common_strategy("rvv_qhead_serial", 100),
            common_strategy("rvv_gqa_q4", 80),
            common_strategy("akv_gqa_serial", 70),
        ],
        "provenance": {"case_sha256": module.sha256(case_path)},
    }


class PrefillMatrixTest(unittest.TestCase):
    def make_root(self, root: Path, shapes: list[tuple[int, int]]) -> Path:
        entries = []
        for index, (past, tokens) in enumerate(shapes):
            case_id = f"operator/prefill/p{past}_m{tokens}/attention_core"
            case_dir = root / "replay" / "cases" / str(index)
            case_dir.mkdir(parents=True)
            (case_dir / "case.json").write_text(
                json.dumps({"P": past, "M": tokens}) + "\n", encoding="utf-8"
            )
            entries.append({"id": case_id, "path": f"replay/cases/{index}"})
        manifest = root / "replay" / "manifest.json"
        manifest.write_text(json.dumps({"cases": entries}) + "\n", encoding="utf-8")
        return root

    @mock.patch.object(module.single_case, "analyze", side_effect=fake_summary)
    def test_reports_exact_missing_cartesian_combinations(self, _analyze: mock.Mock) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_root(Path(temporary), [(0, 15), (512, 511)])
            result = module.analyze_matrix(
                root, [2, 4], required_m=(15, 512), required_p=(0, 512)
            )
        self.assertEqual(result["matrix_status"], "INCOMPLETE")
        self.assertEqual(
            result["missing_combinations"],
            [{"P": 0, "M": 512}, {"P": 512, "M": 15}, {"P": 512, "M": 512}],
        )

    @mock.patch.object(module.single_case, "analyze", side_effect=fake_summary)
    def test_binds_passing_reference_by_id_and_hash(self, _analyze: mock.Mock) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_root(Path(temporary) / "capture", [(0, 15)])
            case_path = root / "replay" / "cases" / "0" / "case.json"
            reference_path = Path(temporary) / "reference.json"
            reference_path.write_text(json.dumps({
                "status": "PASS",
                "case_count": 1,
                "failed_cases": 0,
                "cases": [{
                    "case_id": "operator/prefill/p0_m15/attention_core",
                    "case_sha256": module.sha256(case_path),
                    "status": "PASS",
                    "mismatches": 0,
                    "max_abs_error": {"value": 1e-5},
                }],
            }) + "\n", encoding="utf-8")
            result = module.analyze_matrix(
                root,
                [2, 4],
                required_m=(15,),
                required_p=(0,),
                reference_report=reference_path,
            )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["reference"]["bound_status"], "PASS")
        self.assertEqual(result["cases"][0]["reference_mismatches"], 0)
        self.assertEqual(result["cases"][0]["vslice64_replay_bytes"], 45)
        self.assertFalse(
            result["cases"][0]["vslice64_implemented_fast_path"]
        )
        self.assertEqual(
            result["cases"][0]["vslice64_retention_status"],
            "REJECTED_M15_RTL_REGRESSION",
        )
        self.assertEqual(
            result["cases"][0]["vslice64_external_kv_read_multiplier"], 1.25
        )
        self.assertEqual(
            result["cases"][0]["vslice64_replay_reduction_vs_panel4"], 0.25
        )
        self.assertEqual(
            result["cases"][0]["vslice64_saved_row_busy_cycles"], 96
        )

    @mock.patch.object(module.single_case, "analyze", side_effect=fake_summary)
    def test_rejects_reference_for_different_case_payload(self, _analyze: mock.Mock) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self.make_root(Path(temporary) / "capture", [(0, 15)])
            reference_path = Path(temporary) / "reference.json"
            reference_path.write_text(json.dumps({
                "status": "PASS",
                "cases": [{
                    "case_id": "operator/prefill/p0_m15/attention_core",
                    "case_sha256": "0" * 64,
                    "status": "PASS",
                    "mismatches": 0,
                }],
            }) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                module.analyze_matrix(
                    root,
                    [2, 4],
                    required_m=(15,),
                    required_p=(0,),
                    reference_report=reference_path,
                )


if __name__ == "__main__":
    unittest.main()
