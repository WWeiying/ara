import json
from pathlib import Path
import unittest

from estimate import amdahl, audit_board_projection, summarize


class WorkEstimateTest(unittest.TestCase):
    def setUp(self):
        self.model = json.loads(Path(__file__).with_name(
            "model_inventory_20261108.json").read_text())

    def test_inventory_and_byte_units(self):
        report = summarize(self.model, [137, 4096])
        self.assertEqual(report["projection_macs_per_decode_token"], 1720451072)
        self.assertEqual(report["projection_stored_weight_bytes"], 1100961792)
        self.assertEqual(report["bus_payload_ceiling_bytes_per_second"], 400000000)
        self.assertEqual(report["contexts"][0]["ideal_f16_kv_read_bytes"], 15712256)
        self.assertEqual(report["contexts"][1]["ideal_f16_kv_read_mib"], 448)
        self.assertAlmostEqual(sum(g["projection_weight_fraction"] for g in
                                   report["projection_groups"].values()), 1)

    def test_amdahl(self):
        self.assertEqual(amdahl(0, 4), 1)
        self.assertEqual(amdahl(1, 4), 4)
        self.assertAlmostEqual(amdahl(0.4, 2), 1.25)
        with self.assertRaises(ValueError):
            amdahl(1.1, 2)
        with self.assertRaises(ValueError):
            amdahl(0.1, 0)

    def test_independent_toy_geometry(self):
        # Two layers, hidden=4, Q=2, KV=1, D=2, FFN=6, vocabulary=8.
        model = {"layers": 2, "hidden": 4, "query_heads": 2,
                 "kv_heads": 1, "head_dim": 2, "intermediate": 6,
                 "vocabulary": 8, "groups": {
                     "attention_projection": {"elements": 96, "bytes": 96},
                     "ffn_projection": {"elements": 144, "bytes": 144},
                     "output": {"elements": 32, "bytes": 32}}}
        report = summarize(model, [3], 10, 8)
        self.assertEqual(report["projection_macs_per_decode_token"], 272)
        self.assertEqual(report["contexts"][0]["attention_macs"], 48)
        self.assertEqual(report["contexts"][0]["ideal_f16_kv_read_bytes"], 48)
        self.assertEqual(report["bus_payload_ceiling_bytes_per_second"], 10)

    def test_reject_bad_inputs(self):
        with self.assertRaises(ValueError):
            summarize(self.model, [0])
        with self.assertRaises(ValueError):
            summarize(self.model, [1], bus_bits=7)
        self.model["hidden"] += 1
        with self.assertRaises(ValueError):
            summarize(self.model, [1])

    def test_board_identity_rejects_unrelated_file(self):
        with self.assertRaisesRegex(ValueError, "sealed board log"):
            audit_board_projection(self.model, Path(__file__))


if __name__ == "__main__":
    unittest.main()
