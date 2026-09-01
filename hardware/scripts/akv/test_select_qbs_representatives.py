#!/usr/bin/env python3

import csv
import json
import tempfile
import unittest
from pathlib import Path

from select_qbs_representatives import collect_shapes, project, select, sensitivity_coverage


CALIBRATION = {
    "profiles": {
        "Q4_K": {
            "matmul_cycles": 2,
            "matmul_weight_logical_bytes": 1,
            "quantize_cycles": 1,
            "quantize_activation_elements": 1,
            "calibration_kind": "measured",
        },
        "Q5_0": {
            "matmul_cycles": 2,
            "matmul_weight_logical_bytes": 1,
            "quantize_cycles": 1,
            "quantize_activation_elements": 1,
            "calibration_kind": "proxy",
        },
    }
}


class RepresentativeSelectionTest(unittest.TestCase):
    def test_moe_activation_is_counted_once_per_source_row(self):
        shape = {
            "operation": "MUL_MAT_ID", "profile": "Q4_K",
            "k": 256, "m": 8, "n": 64, "activation_rows": 1,
            "dot_elements": 131072, "weight_bytes": 73728,
            "weight_unique_tensor_bytes": 589824, "activation_bytes": 292,
            "name": "ffn_moe_gate-0",
        }
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "complete").write_text("PASS\n", encoding="ascii")
            with (root / "dynamic_counts.csv").open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(
                    stream, fieldnames=("model", "effective_kv", "status"),
                    lineterminator="\n",
                )
                writer.writeheader()
                writer.writerows([
                    {"model": "moe", "effective_kv": 16, "status": "PASS"},
                    {"model": "moe", "effective_kv": 128, "status": "PASS"},
                ])
            for kv in (16, 128):
                case = root / "moe" / f"kv{kv}"
                case.mkdir(parents=True)
                (case / "summary.json").write_text(
                    json.dumps({"decode": {"qbs_shapes": [shape]}}), encoding="utf-8"
                )
            rows, models, kv_lengths = collect_shapes(root)
            self.assertEqual(models, ["moe"])
            self.assertEqual(kv_lengths, [16, 128])
            self.assertEqual(rows[0]["activation_rows"], 1)
            self.assertEqual(rows[0]["activation_elements"], 256)

    def test_projection_selection_and_sensitivity(self):
        rows = [
            {"operation": "MUL_MAT", "profile": "Q4_K", "k": 1, "m": 1, "n": 8,
             "weight_logical_bytes": 8, "activation_elements": 1},
            {"operation": "MUL_MAT", "profile": "Q4_K", "k": 1, "m": 1, "n": 2,
             "weight_logical_bytes": 2, "activation_elements": 1},
            {"operation": "MUL_MAT_ID", "profile": "Q5_0", "k": 1, "m": 1, "n": 1,
             "weight_logical_bytes": 1, "activation_elements": 1},
        ]
        project(rows, CALIBRATION)
        selected, coverage = select(rows, 0.65)
        self.assertEqual(len(selected), 1)
        self.assertGreater(coverage, 0.65)
        sensitivity = sensitivity_coverage(rows, selected, "Q5_0", [1.0, 4.0])
        self.assertGreater(sensitivity[0]["coverage"], sensitivity[1]["coverage"])


if __name__ == "__main__":
    unittest.main()
