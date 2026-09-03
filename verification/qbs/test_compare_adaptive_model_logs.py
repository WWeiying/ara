#!/usr/bin/env python3

import json
import tempfile
import unittest
from pathlib import Path

from compare_adaptive_model_logs import compare_logs


ROOT = Path(__file__).resolve().parents[2]


class AdaptiveModelLogComparisonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.abi = json.loads(
            (ROOT / "config/qbs_abi.json").read_text(encoding="utf-8")
        )

    def write_log(self, path: Path, m_field: str, model_nodes: int = 1) -> None:
        path.write_text(
            model_nodes
            * "GGML_RISCV_MODEL_NODE op=MUL_MAT type=f32 name=test\n"
            + "GGML_RISCV_QBS_CALL type=q4_K mode=gemm k=256 "
            "input_rows=8 output_rows=32 split_k=0\n"
            "GGML_RISCV_QBS_EXEC type=Q4_K gemv_calls=0 gemm_calls=1 "
            f"{m_field} native_qbexec=2 emulated_commands=0 "
            "command_dot_elements=65536\n",
            encoding="utf-8",
        )

    def test_matched_m8_log_reduces_exact_input_traffic(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = Path(directory) / "baseline.log"
            adaptive = Path(directory) / "adaptive.log"
            self.write_log(baseline, "commands_m4=2")
            self.write_log(adaptive, "commands_m8=2")
            report = compare_logs(baseline, adaptive, self.abi)

        self.assertEqual(report["baseline"]["commands_by_m"], {4: 2})
        self.assertEqual(report["adaptive"]["commands_by_m"], {8: 2})
        self.assertEqual(report["baseline"]["input_bytes"], 11552)
        self.assertEqual(report["adaptive"]["input_bytes"], 9280)
        self.assertAlmostEqual(
            report["reduction"]["input_bytes_reduction_pct"],
            19.667590027700832,
        )

    def test_counter_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = Path(directory) / "baseline.log"
            adaptive = Path(directory) / "adaptive.log"
            self.write_log(baseline, "commands_m4=1")
            self.write_log(adaptive, "commands_m8=2")
            with self.assertRaisesRegex(ValueError, "modeled M counts"):
                compare_logs(baseline, adaptive, self.abi)

    def test_model_graph_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = Path(directory) / "baseline.log"
            adaptive = Path(directory) / "adaptive.log"
            self.write_log(baseline, "commands_m4=2", model_nodes=2)
            self.write_log(adaptive, "commands_m8=2")
            with self.assertRaisesRegex(ValueError, "same model graph nodes"):
                compare_logs(baseline, adaptive, self.abi)


if __name__ == "__main__":
    unittest.main()
