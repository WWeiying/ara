#!/usr/bin/env python3

import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("check-goal-closure.py")
SPEC = importlib.util.spec_from_file_location("check_goal_closure", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def write_single_csv(path, row):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)


class GoalClosureTest(unittest.TestCase):
    def test_shape_matrix_requires_exact_cartesian_product(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.json"
            path.write_text(json.dumps({
                "status": "completed", "cases": ["akv-v2/derived-real/d64-g1-kv16"],
                "modes": ["ref", "rvv"], "expected_results": 2,
                "completed_results": 2, "passed": 2, "failed": 0, "remaining": 0,
                "results": [
                    {"case": "akv-v2/derived-real/d64-g1-kv16", "mode": mode,
                     "passed": True, "build_rc": 0, "run_rc": 0}
                    for mode in ("ref", "rvv")
                ],
            }))
            result = MODULE.check_shape_matrix({
                "summary": str(path), "head_dims": [64], "gqa_rows": [1],
                "kv_lengths": [16], "modes": ["ref", "rvv"],
            })
            self.assertEqual(result["results"], 2)

    def test_lifetime_rejects_byte_accounting_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = {
                "provenance": {"tool": {"sha256": MODULE.file_sha256(
                    "hardware/scripts/qbs/compare_activation_lifetime_runs.py")}},
                "semantic_command_stream_equal": True,
                "baseline": {"quantizations": 2, "activation_bytes": 20,
                             "quantization_input_bytes": 32},
                "cross_operator": {"quantizations": 1, "quantizations_eliminated": 1,
                                   "activation_bytes": 10, "activation_bytes_eliminated": 10,
                                   "quantization_input_bytes": 16,
                                   "quantization_input_bytes_eliminated": 16},
                "eliminated_quantizations": [{
                    "activation_profile": 1, "family": "attention_qkv", "graph_epoch": 1,
                    "input_bytes": 15, "input_elements": 4, "k": 4, "m": 1, "n": 4,
                    "op": "Kcur-0", "quantized_bytes": 10, "weight": "k", "weight_type": "Q4_K",
                }],
                "families": {"attention_qkv": {"removable_quantizations": 1},
                             "ffn_gate_up": {"removable_quantizations": 0}},
            }
            rtl = {"status": "PASS", "baseline_quantizations": 2,
                   "cross_op_quantizations": 1, "quantizations_eliminated": 1,
                   "quantization_input_bytes_saved": 16, "activation_axi_bytes_saved": 10,
                   "logical_read_bytes_saved": 26, "baseline_cycles": 20,
                   "cross_op_cycles": 10, "cycle_reduction": 0.5, "speedup": 2.0}
            (root / "model.json").write_text(json.dumps(model))
            (root / "rtl.json").write_text(json.dumps(rtl))
            with self.assertRaisesRegex(MODULE.ClosureError, "F32 input-byte"):
                MODULE.check_lifetime({"summary": str(root / "model.json"),
                                       "controlled_rtl": str(root / "rtl.json")})

    def test_qbs_regression_requires_matching_context_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = {"case": "q4", "result": "PASS", "mismatches": "0",
                      "timed_cycles": "100", "tiles": "2"}
            write_single_csv(root / "baseline.csv", result)
            write_single_csv(root / "current.csv", result)
            write_single_csv(root / "perf.csv", {
                "context_fill_count": "0", "context_reuse_count": "0",
                "context_read_bytes": "0", "activation_axi_bytes_saved": "0",
            })
            (root / "console.log").write_text("activation_context=0\n")
            with self.assertRaisesRegex(MODULE.ClosureError, "required context mode"):
                MODULE.check_qbs_representative({
                    "name": "q4", "baseline": str(root / "baseline.csv"),
                    "current": str(root / "current.csv"), "current_perf": str(root / "perf.csv"),
                    "current_console": str(root / "console.log"),
                    "required_context": True, "max_regression": 0.01,
                })

    def test_key_value_parser(self):
        self.assertEqual(MODULE.parse_key_values("x=1 y=-2 label=text"), {"x": 1, "y": -2})

    def test_projection_ablation_isolates_qbs_cycles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fields = ("phase", "category", "instances", "projected_cycles",
                      "share_of_calibrated_cycles")
            before = [
                {"phase": "decode", "category": "qbs", "instances": "2",
                 "projected_cycles": "80", "share_of_calibrated_cycles": "0.8"},
                {"phase": "decode", "category": "rvv", "instances": "1",
                 "projected_cycles": "20", "share_of_calibrated_cycles": "0.2"},
            ]
            after = [
                {"phase": "decode", "category": "qbs", "instances": "2",
                 "projected_cycles": "70", "share_of_calibrated_cycles": str(70 / 90)},
                {"phase": "decode", "category": "rvv", "instances": "1",
                 "projected_cycles": "20", "share_of_calibrated_cycles": str(20 / 90)},
            ]
            for name, rows in (("before.csv", before), ("after.csv", after)):
                with (root / name).open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)
            result = MODULE.check_projection_ablation(root / "before.csv", root / "after.csv")
            self.assertEqual(result["cycles_saved"], 10)
            self.assertAlmostEqual(result["speedup"], 100 / 90)


if __name__ == "__main__":
    unittest.main()
