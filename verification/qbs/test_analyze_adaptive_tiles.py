#!/usr/bin/env python3

import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyze_adaptive_tiles import Geometry, estimate


ROOT = Path(__file__).resolve().parents[2]


class AdaptiveTileModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.abi = json.loads(
            (ROOT / "config/qbs_abi.json").read_text(encoding="utf-8")
        )

    def test_q4_m4_matches_measured_counter_contract(self):
        result = estimate(
            self.abi,
            "prefill_attn_q_qbs",
            "Q4_K",
            m=4,
            n=1536,
            k=1536,
            geometry=Geometry("m4n32", 4, 32),
        )
        self.assertEqual(result.command_count, 48)
        self.assertEqual(result.weight_bytes, 1_327_104)
        self.assertEqual(result.activation_bytes, 336_384)
        self.assertEqual(result.ideal_dot_cycles, 294_912)

    def test_q6_m4_matches_measured_counter_contract(self):
        result = estimate(
            self.abi,
            "prefill_ffn_down_qbs",
            "Q6_K",
            m=4,
            n=64,
            k=8960,
            geometry=Geometry("m4n32", 4, 32),
        )
        self.assertEqual(result.command_count, 2)
        self.assertEqual(result.weight_bytes, 470_400)
        self.assertEqual(result.activation_bytes, 81_760)
        self.assertEqual(result.ideal_dot_cycles, 71_680)

    def test_m8n16_preserves_compute_capacity_and_reduces_q6_input(self):
        current = estimate(
            self.abi,
            "qwen25_ffn_down",
            "Q6_K",
            m=8,
            n=1536,
            k=8960,
            geometry=Geometry("m4n32", 4, 32),
        )
        adaptive = estimate(
            self.abi,
            "qwen25_ffn_down",
            "Q6_K",
            m=8,
            n=1536,
            k=8960,
            geometry=Geometry("m8n16", 8, 16),
        )
        self.assertEqual(current.pair_capacity, adaptive.pair_capacity)
        self.assertEqual(current.command_count, adaptive.command_count)
        self.assertEqual(adaptive.max_command_results, 128)
        reduction = (current.input_bytes - adaptive.input_bytes) / current.input_bytes
        self.assertTrue(math.isclose(reduction, 0.27789046653144016))

    def test_m8n16_is_not_selected_for_m4(self):
        current = estimate(
            self.abi,
            "qwen25_attn_q",
            "Q4_K",
            m=4,
            n=1536,
            k=1536,
            geometry=Geometry("m4n32", 4, 32),
        )
        adaptive = estimate(
            self.abi,
            "qwen25_attn_q",
            "Q4_K",
            m=4,
            n=1536,
            k=1536,
            geometry=Geometry("m8n16", 8, 16),
        )
        self.assertGreater(adaptive.input_bytes, current.input_bytes)


if __name__ == "__main__":
    unittest.main()
