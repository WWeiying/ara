#!/usr/bin/env python3

import unittest

from hardware.scripts.qbs import compare_activation_lifetime_runs as compare


class CompareActivationLifetimeRunsTest(unittest.TestCase):
    def setUp(self):
        self.baseline_summary = {
            "quantizations": 3,
            "quantized_bytes": 300,
            "removable_quantizations": 2,
            "removable_quantized_bytes": 200,
            "removable_quantize_time_us": 20,
            "eligible_groups": 1,
            "unlinked_commands": 0,
            "families": {"attention_qkv": {"groups": 1}},
        }
        self.optimized_summary = {
            "quantizations": 1,
            "quantized_bytes": 100,
            "unlinked_commands": 0,
        }
        self.command = {
            "seq": 1,
            "graph_epoch": 2,
            "weight_type": "q4_K",
            "weight_profile": 1,
            "activation_profile": 1,
            "m": 1,
            "n": 32,
            "k_blocks": 6,
            "segmented": 0,
            "emulated": 0,
        }
        self.cross = {
            "chains": 1,
            "fills": 1,
            "releases": 1,
            "reuses": 2,
            "quantization_skips": 2,
            "activation_bytes_saved": 200,
        }
        self.baseline_trace = {"quantize_time_us": 40}
        self.optimized_trace = {"quantize_time_us": 20}

    def test_balanced_pair(self):
        result = compare.compare_data(
            self.baseline_summary,
            self.optimized_summary,
            [self.command],
            [self.command],
            self.cross,
            self.baseline_trace,
            self.optimized_trace,
        )
        self.assertTrue(result["semantic_command_stream_equal"])
        self.assertEqual(result["cross_operator"]["quantizations_eliminated"], 2)
        self.assertEqual(result["cross_operator"]["activation_bytes_eliminated"], 200)

    def test_command_work_change_is_rejected(self):
        changed = {**self.command, "k_blocks": 7}
        with self.assertRaisesRegex(ValueError, "semantic work fields"):
            compare.compare_data(
                self.baseline_summary,
                self.optimized_summary,
                [self.command],
                [changed],
                self.cross,
                self.baseline_trace,
                self.optimized_trace,
            )


if __name__ == "__main__":
    unittest.main()
