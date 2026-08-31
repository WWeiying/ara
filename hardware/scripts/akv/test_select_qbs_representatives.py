#!/usr/bin/env python3

import unittest

from select_qbs_representatives import project, select, sensitivity_coverage


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
    def test_projection_selection_and_sensitivity(self):
        rows = [
            {"profile": "Q4_K", "k": 1, "m": 1, "n": 8,
             "weight_logical_bytes": 8, "activation_elements": 1},
            {"profile": "Q4_K", "k": 1, "m": 1, "n": 2,
             "weight_logical_bytes": 2, "activation_elements": 1},
            {"profile": "Q5_0", "k": 1, "m": 1, "n": 1,
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
