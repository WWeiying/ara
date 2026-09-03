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
        self.assertEqual(
            report["adaptive"]["by_profile"]["Q4_K"]["commands_by_m"],
            {8: 2},
        )
        self.assertEqual(
            report["adaptive"]["by_profile"]["Q4_K"]["native_commands"],
            2,
        )
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

    def test_model_graph_identity_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = Path(directory) / "baseline.log"
            adaptive = Path(directory) / "adaptive.log"
            self.write_log(baseline, "commands_m4=2")
            self.write_log(adaptive, "commands_m8=2")
            adaptive.write_text(
                adaptive.read_text(encoding="utf-8").replace(
                    "GGML_RISCV_MODEL_NODE op=MUL_MAT type=f32 name=test",
                    "GGML_RISCV_MODEL_NODE op=MUL_MAT type=f32 name=other",
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "same model graph nodes"):
                compare_logs(baseline, adaptive, self.abi)

    def test_profile_counter_misattribution_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = Path(directory) / "baseline.log"
            adaptive = Path(directory) / "adaptive.log"
            self.write_log(baseline, "commands_m4=2")
            self.write_log(adaptive, "commands_m8=2")
            adaptive.write_text(
                adaptive.read_text(encoding="utf-8").replace(
                    "GGML_RISCV_QBS_EXEC type=Q4_K",
                    "GGML_RISCV_QBS_EXEC type=Q6_K",
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "modeled profiles"):
                compare_logs(baseline, adaptive, self.abi)

    def test_combined_log_uses_only_qbs_akv_section(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = Path(directory) / "baseline.log"
            adaptive = Path(directory) / "adaptive.log"
            self.write_log(baseline, "commands_m4=2")
            self.write_log(adaptive, "commands_m8=2")
            baseline_payload = baseline.read_text(encoding="utf-8")
            adaptive_payload = adaptive.read_text(encoding="utf-8")
            baseline.write_text(
                "AKV_TOKEN_RUN_BEGIN=RVV\n"
                "GGML_RISCV_MODEL_NODE op=ADD type=f32 name=ignored\n"
                "AKV_TOKEN_RUN_EXIT=RVV:0\n"
                "AKV_TOKEN_RUN_BEGIN=QBS_ONLY\n"
                "GGML_RISCV_MODEL_NODE op=ADD type=f32 name=ignored\n"
                + "AKV_TOKEN_RUN_EXIT=QBS_ONLY:0\n"
                "AKV_TOKEN_RUN_BEGIN=QBS_AKV_V2\n"
                + baseline_payload
                + "AKV_TOKEN_RUN_EXIT=QBS_AKV_V2:0\n",
                encoding="utf-8",
            )
            adaptive.write_text(
                "AKV_TOKEN_RUN_BEGIN=RVV\n"
                "GGML_RISCV_MODEL_NODE op=ADD type=f32 name=ignored\n"
                "AKV_TOKEN_RUN_EXIT=RVV:0\n"
                "AKV_TOKEN_RUN_BEGIN=QBS_ONLY\n"
                "GGML_RISCV_MODEL_NODE op=ADD type=f32 name=ignored\n"
                + "AKV_TOKEN_RUN_EXIT=QBS_ONLY:0\n"
                "AKV_TOKEN_RUN_BEGIN=QBS_AKV_V2\n"
                + adaptive_payload
                + "AKV_TOKEN_RUN_EXIT=QBS_AKV_V2:0\n",
                encoding="utf-8",
            )
            report = compare_logs(baseline, adaptive, self.abi)

        self.assertEqual(report["baseline"]["commands_by_m"], {4: 2})
        self.assertEqual(report["adaptive"]["commands_by_m"], {8: 2})
        self.assertEqual(report["baseline"]["model_nodes"]["total"], 1)

    def test_wide_m33_uses_n32_for_the_single_row_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline = Path(directory) / "baseline.log"
            adaptive = Path(directory) / "adaptive.log"
            common = (
                "GGML_RISCV_MODEL_NODE op=MUL_MAT type=f32 name=test\n"
                "GGML_RISCV_QBS_CALL type=q4_K mode=gemm k=256 "
                "input_rows=33 output_rows=32 split_k=0\n"
            )
            baseline.write_text(
                common
                + "GGML_RISCV_QBS_EXEC type=Q4_K commands_m1=1 "
                "commands_m4=8 native_qbexec=9 emulated_commands=0 "
                "command_dot_elements=270336\n",
                encoding="utf-8",
            )
            adaptive.write_text(
                common
                + "GGML_RISCV_QBS_EXEC type=Q4_K commands_m1=1 "
                "commands_m8=8 native_qbexec=9 emulated_commands=0 "
                "command_dot_elements=270336\n",
                encoding="utf-8",
            )
            report = compare_logs(baseline, adaptive, self.abi)

        self.assertEqual(report["baseline"]["commands_by_m"], {1: 1, 4: 8})
        self.assertEqual(report["adaptive"]["commands_by_m"], {1: 1, 8: 8})


if __name__ == "__main__":
    unittest.main()
