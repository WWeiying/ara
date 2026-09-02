#!/usr/bin/env python3

import importlib.util
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("summarize-model-generality.py")
SPEC = importlib.util.spec_from_file_location("summarize_model_generality", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def host(eligible: int = 1, fallback: int = 0) -> dict[str, object]:
    return {
        "decode": {
            "qbs_candidate_compute_nodes": 2,
            "qbs_profiles": {"Q4_K": 2},
            "qbs_operations": {"MUL_MAT": 2},
            "akv_candidate_compute_nodes": 1,
            "akv_shape_eligible_compute_nodes": eligible,
            "akv_shape_fallback_compute_nodes": fallback,
        }
    }


def qemu(
    executed: int,
    fallback_shape: int,
    *,
    executed_prefill: int = 0,
) -> dict[str, object]:
    executed_decode = executed - executed_prefill
    assert executed_decode >= 0
    return {
        "graphs": {"prefill": 1, "decode": 1},
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
                "QBS_RVV_LOGITS_MEAN_COSINE": "0.99",
                "QBS_RVV_LOGITS_TOP5_OVERLAP": "1",
            },
        },
        "qbs": {
            "nodes": 4,
            "operations": {"MUL_MAT": 4},
            "coverage": {
                "Q4_K": {
                    "candidate_tensors": "2", "selected_tensors": "2",
                    "candidate_elements": "1024", "selected_elements": "1024",
                    "fallback_runtime": "0", "fallback_format_filter": "0",
                    "fallback_capability": "0", "fallback_dimensions": "0",
                    "fallback_shape": "0", "fallback_layout": "0",
                    "fallback_profile": "0", "fallback_dispatch": "0",
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
                "candidate_ops": "2", "executed_ops": str(executed),
                "executed_decode": str(executed_decode),
                "executed_prefill": str(executed_prefill),
                "prefill_query_tokens": str(15 * executed_prefill),
                "prefill_attention_pairs": str(720 * executed_prefill),
                "fallback_runtime": "0", "fallback_capability": "0",
                "fallback_threading": "0", "fallback_feature": "0",
                "fallback_shape": str(fallback_shape), "fallback_layout": "0",
                "fallback_mask": "0",
                "fallback_size": "0",
            }
        },
        "provenance": {
            "tool": {"sha256": MODULE.sha256(MODULE.QEMU_MODULE.MODEL_SUMMARIZER)},
            "qbs_abi": {"sha256": "3" * 64, "architecture_version": 2},
            "run_manifest": {
                "MODEL_GUEST_PATH": "/model/models/test.gguf",
                "MODEL_PROMPT": "test prompt",
                "MODEL_TOKENS": "2",
                "LOGITS_MAX_ABS_TOLERANCE": "0.001",
                "LLAMA_REVISION": "llama-revision",
                "LLAMA_BINARY_SHA256": "1" * 64,
                "QEMU_BINARY_SHA256": "2" * 64,
                "QEMU_CPU": "rv64,v=true,vlen=1024,xaraqbs=true",
                "QEMU_MEMORY": "4G",
                "MODEL_DISK_SHA256": "disk-sha",
                "REQUIRE_PREFILL": "1" if executed_prefill else "0",
            }
        },
    }


class SummarizeModelGeneralityTest(unittest.TestCase):
    def test_attention_work_separates_candidate_and_eligible_shapes(self):
        decode = {
            "attention_shapes": [
                {
                    "shape_eligible": True,
                    "query_payload_logical_bytes": 64,
                    "kv_payload_logical_bytes": 128,
                    "attention_macs": 256,
                },
                {
                    "shape_eligible": False,
                    "query_payload_logical_bytes": 32,
                    "kv_payload_logical_bytes": 512,
                    "attention_macs": 1024,
                },
            ],
            "akv_query_payload_logical_bytes": 64,
            "akv_kv_payload_logical_bytes": 128,
            "akv_attention_macs": 256,
        }
        work = MODULE.attention_work(decode)
        self.assertEqual(work["candidate_kv_payload_logical_bytes"], 640)
        self.assertEqual(work["candidate_attention_macs"], 1280)
        self.assertEqual(work["eligible_kv_payload_logical_bytes"], 128)
        self.assertEqual(work["eligible_attention_macs"], 256)

    def test_attention_work_rejects_inconsistent_legacy_value(self):
        decode = {
            "attention_shapes": [{
                "shape_eligible": False,
                "query_payload_logical_bytes": 32,
                "kv_payload_logical_bytes": 512,
                "attention_macs": 1024,
            }],
            "akv_attention_macs": 1024,
        }
        with self.assertRaisesRegex(ValueError, "legacy host summary"):
            MODULE.attention_work(decode)

    def test_host_sweep_requires_exact_pass_matrix_and_model_hashes(self):
        models = {"test": {"expected_sha256": "model-sha"}}
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
                    {"model": "test", "effective_kv": 16, "status": "PASS"},
                    {"model": "test", "effective_kv": 128, "status": "PASS"},
                ])
            (root / "provenance.json").write_text(json.dumps({
                "baseline_commit": "base",
                "llama_revision": "llama",
                "llama_binary_sha256": "binary",
                "tokenizer_sha256": "tokenizer",
                "qbs_abi_sha256": "abi",
                "models": {"test": {"sha256": "model-sha"}},
            }), encoding="utf-8")
            provenance = MODULE.verify_host_sweep(root, models, [16, 128], "base")
            self.assertEqual(provenance["llama_revision"], "llama")

    def test_decode_execution_matches_prefill_fallback(self):
        spec = {
            "id": "test", "akv_disposition": "execute",
            "qemu": {"guest_path": "/model/models/test.gguf", "memory": "4G",
                     "disk_sha256": "disk-sha"},
            "decode_expectation": {
                "qbs_candidate_compute_nodes": 2,
                "attention_candidate_compute_nodes": 1,
                "qbs_profiles": ["Q4_K"],
                "qbs_operations": {"MUL_MAT": 2},
            },
        }
        metrics = MODULE.verify_qemu_against_host(spec, host(), qemu(1, 1))
        self.assertEqual(metrics["akv_executed_ops"], 1)

    def test_all_shape_fallback_is_accepted(self):
        spec = {
            "id": "test", "akv_disposition": "fallback_shape",
            "qemu": {"guest_path": "/model/models/test.gguf", "memory": "4G",
                     "disk_sha256": "disk-sha"},
            "decode_expectation": {
                "qbs_candidate_compute_nodes": 2,
                "attention_candidate_compute_nodes": 1,
                "qbs_profiles": ["Q4_K"],
                "qbs_operations": {"MUL_MAT": 2},
            },
        }
        metrics = MODULE.verify_qemu_against_host(spec, host(0, 1), qemu(0, 2))
        self.assertEqual(metrics["akv_fallback_shape"], 2)

    def test_prefill_census_requires_both_attention_phases(self):
        spec = {
            "id": "test", "akv_disposition": "execute",
            "qemu": {"guest_path": "/model/models/test.gguf", "memory": "4G",
                     "disk_sha256": "disk-sha"},
            "decode_expectation": {
                "qbs_candidate_compute_nodes": 2,
                "attention_candidate_compute_nodes": 1,
                "qbs_profiles": ["Q4_K"],
                "qbs_operations": {"MUL_MAT": 2},
            },
        }
        metrics = MODULE.verify_qemu_against_host(
            spec, host(), qemu(2, 0, executed_prefill=1), True
        )
        self.assertEqual(metrics["akv_executed_decode"], 1)
        self.assertEqual(metrics["akv_executed_prefill"], 1)

    def test_prefill_census_rejects_old_decode_only_partition(self):
        spec = {
            "id": "test", "akv_disposition": "execute",
            "qemu": {"guest_path": "/model/models/test.gguf", "memory": "4G",
                     "disk_sha256": "disk-sha"},
            "decode_expectation": {
                "qbs_candidate_compute_nodes": 2,
                "attention_candidate_compute_nodes": 1,
                "qbs_profiles": ["Q4_K"],
                "qbs_operations": {"MUL_MAT": 2},
            },
        }
        value = qemu(1, 1)
        value["provenance"]["run_manifest"]["REQUIRE_PREFILL"] = "1"
        with self.assertRaisesRegex(ValueError, "both Decode and Prefill"):
            MODULE.verify_qemu_against_host(spec, host(), value, True)

    def test_qemu_operation_drift_is_rejected(self):
        spec = {
            "id": "test", "akv_disposition": "execute",
            "qemu": {"guest_path": "/model/models/test.gguf", "memory": "4G",
                     "disk_sha256": "disk-sha"},
            "decode_expectation": {
                "qbs_candidate_compute_nodes": 2,
                "attention_candidate_compute_nodes": 1,
                "qbs_profiles": ["Q4_K"],
                "qbs_operations": {"MUL_MAT": 2},
            },
        }
        value = qemu(1, 1)
        value["qbs"]["operations"] = {"MUL_MAT_ID": 4}
        value["qbs"]["activation_accounting"] = {
            "complete": True,
            "unresolved_nodes": 0,
            "unresolved_operations": {},
        }
        with self.assertRaisesRegex(ValueError, "operation mismatch"):
            MODULE.verify_qemu_against_host(spec, host(), value)


if __name__ == "__main__":
    unittest.main()
