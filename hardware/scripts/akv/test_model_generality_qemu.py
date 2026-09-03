#!/usr/bin/env python3

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("run-model-generality-qemu.py")
SPEC = importlib.util.spec_from_file_location("run_model_generality_qemu", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def summary(
    executed: int,
    fallback_shape: int,
    *,
    executed_prefill: int = 0,
) -> dict[str, object]:
    executed_decode = executed - executed_prefill
    assert executed_decode >= 0
    return {
        "provenance": {
            "tool": {"sha256": MODULE.sha256(MODULE.MODEL_SUMMARIZER)},
            "qbs_abi": {"sha256": "3" * 64, "architecture_version": 2},
            "run_manifest": {
                "LLAMA_REVISION": "llama-revision",
                "LLAMA_BINARY_SHA256": "1" * 64,
                "QEMU_BINARY_SHA256": "2" * 64,
                "QEMU_CPU": "rv64,v=true,vlen=1024,elen=64,xaraqbs=true",
                "MODEL_PROMPT": "test prompt",
                "MODEL_TOKENS": "2",
                "LOGITS_MAX_ABS_TOLERANCE": "0.001",
                "MODEL_NUMERICAL_CONTRACT": "decision-preserving-v1",
                "MODEL_LOGITS_MAX_KL_TOLERANCE": "0.02",
                "MODEL_LOGITS_MIN_COSINE_TOLERANCE": "0.98",
                "MODEL_LOGITS_MIN_TOP5_OVERLAP_TOLERANCE": "0.8",
                "REQUIRE_PREFILL": "1" if executed_prefill else "0",
            }
        },
        "functional": {
            "guest_exit": 0,
            "output_equal": True,
            "logits_top1_equal": "1",
            "logits_max_abs": "0",
            "akv_qbs": {
                "AKV_LOGITS_RECORDS": "1",
                "AKV_LOGITS_COMPARABLE_RECORDS": "1",
                "AKV_LOGITS_MAX_ABS": "0",
                "AKV_LOGITS_MAX_REL": "0",
                "AKV_LOGITS_MEAN_ABS": "0",
                "AKV_LOGITS_MEAN_RMSE": "0",
                "AKV_LOGITS_MEAN_KL": "0",
                "AKV_LOGITS_MEAN_COSINE": "1",
                "AKV_LOGITS_TOP5_OVERLAP": "1",
                "AKV_LOGITS_MAX_KL": "0",
                "AKV_LOGITS_MIN_COSINE": "1",
                "AKV_LOGITS_MIN_TOP5_OVERLAP": "1",
                "AKV_LOGITS_TOP1_EQUAL": "1",
            },
            "qbs_rvv": {
                "QBS_RVV_LOGITS_RECORDS": "1",
                "QBS_RVV_LOGITS_COMPARABLE_RECORDS": "1",
                "QBS_RVV_LOGITS_TOP1_EQUAL": "1",
                "QBS_RVV_TOKEN_OUTPUT_EQUAL": "1",
                "QBS_RVV_LOGITS_MAX_ABS": "0.25",
                "QBS_RVV_LOGITS_MAX_REL": "0.5",
                "QBS_RVV_LOGITS_MEAN_ABS": "0.1",
                "QBS_RVV_LOGITS_MEAN_RMSE": "0.12",
                "QBS_RVV_LOGITS_MEAN_KL": "0.01",
                "QBS_RVV_LOGITS_MEAN_COSINE": "0.9995",
                "QBS_RVV_LOGITS_TOP5_OVERLAP": "1",
                "QBS_RVV_LOGITS_MAX_KL": "0.01",
                "QBS_RVV_LOGITS_MIN_COSINE": "0.9995",
                "QBS_RVV_LOGITS_MIN_TOP5_OVERLAP": "1",
            },
        },
        "qbs": {
            "nodes": 4,
            "operations": {"MUL_MAT": 4},
            "coverage": {
                "Q4_K": {
                    "candidate_tensors": "2",
                    "selected_tensors": "2",
                    "candidate_elements": "1024",
                    "selected_elements": "1024",
                    "fallback_runtime": "0",
                    "fallback_format_filter": "0",
                    "fallback_capability": "0",
                    "fallback_dimensions": "0",
                    "fallback_shape": "0",
                    "fallback_layout": "0",
                    "fallback_profile": "0",
                    "fallback_dispatch": "0",
                }
            },
            "execution": {
                "Q4_K": {
                    "gemv_calls": "2", "gemm_calls": "1",
                    "native_qbexec": "8", "emulated_commands": "0",
                    "dot_elements": "1024", "command_dot_elements": "1024",
                }
            },
        },
        "akv_v2": {
            "calls_by_mode": {
                "decode": executed_decode,
                "prefill": executed_prefill,
            },
            "coverage": {
                "candidate_ops": str(executed + fallback_shape),
                "executed_ops": str(executed),
                "executed_decode": str(executed_decode),
                "executed_prefill": str(executed_prefill),
                "prefill_query_tokens": str(15 * executed_prefill),
                "prefill_attention_pairs": str(720 * executed_prefill),
                "fallback_runtime": "0",
                "fallback_capability": "0",
                "fallback_threading": "0",
                "fallback_feature": "0",
                "fallback_shape": str(fallback_shape),
                "fallback_layout": "0",
                "fallback_mask": "0",
                "fallback_size": "0",
            }
        },
        "graphs": {"prefill": 1, "decode": 1},
    }


class ModelGeneralityQemuTest(unittest.TestCase):
    def test_execute_metrics_require_native_qbs_and_akv(self):
        metrics = MODULE.qemu_metrics(summary(2, 0), "execute")
        self.assertEqual(metrics["qbs_profiles"], "Q4_K")
        self.assertEqual(metrics["qbs_operations"], "MUL_MAT:4")
        self.assertEqual(metrics["qbs_gemv_calls"], 2)
        self.assertEqual(metrics["qbs_gemm_calls"], 1)
        self.assertEqual(metrics["qbs_dot_elements"], 1024)
        self.assertEqual(metrics["qbs_native_commands"], 8)
        self.assertEqual(metrics["akv_executed_ops"], 2)

    def test_shape_fallback_is_explicitly_accepted(self):
        metrics = MODULE.qemu_metrics(summary(0, 2), "fallback_shape")
        self.assertEqual(metrics["akv_executed_ops"], 0)
        self.assertEqual(metrics["akv_fallback_shape"], 2)
        self.assertEqual(metrics["akv_fastpath_status"], "shape-fallback")

    def test_prefill_census_requires_decode_and_prefill_without_fallback(self):
        metrics = MODULE.qemu_metrics(
            summary(2, 0, executed_prefill=1), "execute", require_prefill=True
        )
        self.assertEqual(metrics["akv_executed_decode"], 1)
        self.assertEqual(metrics["akv_executed_prefill"], 1)
        self.assertEqual(metrics["akv_prefill_query_tokens"], 15)
        self.assertEqual(metrics["akv_prefill_attention_pairs"], 720)
        self.assertEqual(metrics["akv_fastpath_status"], "decode+prefill")
        self.assertEqual(metrics["akv_performance_evidence"], "functional-qemu-only")

    def test_prefill_census_rejects_decode_only_execute(self):
        value = summary(2, 0)
        value["provenance"]["run_manifest"]["REQUIRE_PREFILL"] = "1"
        with self.assertRaisesRegex(ValueError, "both Decode and Prefill"):
            MODULE.qemu_metrics(value, "execute", require_prefill=True)

    def test_prefill_census_accepts_explicit_shape_fallback(self):
        metrics = MODULE.qemu_metrics(
            summary(0, 2), "fallback_shape", require_prefill=True
        )
        self.assertEqual(metrics["akv_fallback_ops"], 2)

    def test_prefill_census_does_not_default_missing_size_fallback(self):
        value = summary(2, 0, executed_prefill=1)
        del value["akv_v2"]["coverage"]["fallback_size"]
        with self.assertRaisesRegex(ValueError, "fallback fields"):
            MODULE.qemu_metrics(value, "execute", require_prefill=True)

    def test_partial_or_wrong_disposition_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "exclusively by shape"):
            MODULE.qemu_metrics(summary(1, 1), "fallback_shape")
        with self.assertRaisesRegex(ValueError, "no executed operation"):
            MODULE.qemu_metrics(summary(0, 2), "execute")

    def test_qbs_fallback_is_rejected(self):
        value = summary(2, 0)
        value["qbs"]["coverage"]["Q4_K"]["fallback_shape"] = "1"
        with self.assertRaisesRegex(ValueError, "coverage is incomplete"):
            MODULE.qemu_metrics(value, "execute")

    def test_akv_model_quality_contract_is_enforced(self):
        value = summary(2, 0)
        value["functional"]["akv_qbs"]["AKV_LOGITS_MAX_KL"] = "0.021"
        with self.assertRaisesRegex(ValueError, "AKV/QBS model-quality"):
            MODULE.qemu_metrics(value, "execute")

    def test_stale_model_summary_is_rejected(self):
        value = summary(2, 0)
        value["provenance"]["tool"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "different model-closure summarizer"):
            MODULE.qemu_metrics(value, "execute")

    def test_partial_native_command_work_is_rejected(self):
        value = summary(2, 0)
        value["qbs"]["execution"]["Q4_K"]["command_dot_elements"] = "1023"
        with self.assertRaisesRegex(ValueError, "command work differs"):
            MODULE.qemu_metrics(value, "execute")

    def test_legacy_mul_mat_id_activation_gap_is_explicit(self):
        value = summary(2, 0)
        value["qbs"]["operations"] = {"MUL_MAT_ID": 4}
        value["qbs"]["activation_accounting"] = {
            "complete": False,
            "unresolved_nodes": 4,
            "unresolved_operations": {"MUL_MAT_ID": 4},
        }
        metrics = MODULE.qemu_metrics(value, "execute")
        self.assertEqual(
            metrics["qbs_activation_accounting"],
            "unavailable_legacy_source_shape",
        )
        self.assertEqual(metrics["qbs_activation_unresolved_nodes"], 4)


if __name__ == "__main__":
    unittest.main()
