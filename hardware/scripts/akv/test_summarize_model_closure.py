#!/usr/bin/env python3

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("summarize-model-closure.py")
SPEC = importlib.util.spec_from_file_location("summarize_model_closure", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ModelClosureTest(unittest.TestCase):
    def test_lifetime_summary_requires_matching_provenance(self):
        manifest = {
            key: f"value-{key}"
            for key in MODULE.LIFETIME_MANIFEST_KEYS
        }
        summary = {
            "semantic_command_stream_equal": True,
            "baseline": {
                "quantizations": 3,
                "activation_bytes": 300,
                "quantization_input_elements": 24,
                "quantization_input_bytes": 96,
            },
            "cross_operator": {
                "quantizations": 2,
                "activation_bytes": 200,
                "activation_bytes_eliminated": 100,
                "quantizations_eliminated": 1,
                "quantization_input_elements": 16,
                "quantization_input_bytes": 64,
                "quantization_input_elements_eliminated": 8,
                "quantization_input_bytes_eliminated": 32,
            },
            "eliminated_quantizations": [
                {
                    "op": "Kcur-0",
                    "weight_type": "Q4_K",
                    "m": 1,
                    "n": 8,
                    "k": 8,
                    "quantized_bytes": 100,
                    "input_elements": 8,
                }
            ],
            "provenance": {"manifest": {"values": manifest}},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lifetime.json"
            path.write_text(json.dumps(summary))
            loaded = MODULE.load_qbs_lifetime_summary(path, manifest)
            self.assertEqual(loaded["cross_operator"]["quantizations_eliminated"], 1)

            mismatched = dict(manifest)
            mismatched["MODEL_PROMPT"] = "different"
            with self.assertRaisesRegex(ValueError, "MODEL_PROMPT"):
                MODULE.load_qbs_lifetime_summary(path, mismatched)

    def test_cycle_projection_applies_exact_lifetime_elimination(self):
        node = {
            "phase": "decode",
            "node_name": "Kcur-0",
            "type": "Q4_K",
            "mode": "gemv",
            "k": 8,
            "input_rows": 1,
            "output_rows": 8,
            "activation_elements": 8,
            "dot_elements": 64,
        }
        qbs_points = [
            {
                "case": "q4",
                "profile": "Q4_K",
                "k": 8,
                "m": 1,
                "n": 8,
                "quant_cycles_per_element": 2.0,
                "matmul_cycles_per_dot": 1.0,
            }
        ]
        lifetime_summary = {
            "eliminated_quantizations": [
                {
                    "op": "Kcur-0",
                    "weight_type": "Q4_K",
                    "m": 1,
                    "n": 8,
                    "k": 8,
                }
            ]
        }
        rows = MODULE.cycle_projection(
            [node], [], [], qbs_points,
            [{"active_kv": 16, "cycles": 100}, {"active_kv": 128, "cycles": 500}],
            {}, lifetime_summary,
        )
        self.assertEqual(rows[0]["quantization_applied"], 0)
        self.assertEqual(rows[0]["quantize_projected_cycles"], 0)
        self.assertEqual(rows[0]["matmul_projected_cycles"], 64)
        self.assertEqual(rows[0]["projected_cycles"], 64)

    def test_combined_trace_is_partitioned_and_cross_checked(self):
        trace = """\
AKV_TOKEN_RUN_BEGIN=RVV
AKV_TOKEN_RUN_EXIT=RVV:0
AKV_TOKEN_RUN_BEGIN=QBS_ONLY
AKV_TOKEN_RUN_EXIT=QBS_ONLY:0
AKV_TOKEN_RUN_BEGIN=QBS_AKV_V2
GGML_RISCV_MODEL_GRAPH_BEGIN id=0 nodes=2
GGML_RISCV_MODEL_NODE op=MUL_MAT type=f32 ne0=8 ne1=4 ne2=1 ne3=1 src0=q4_K src1=f32 fused_followers=0 fused_next=NONE name=blk.0.attn_q
GGML_RISCV_QBS_CALL type=q4_K mode=gemm k=256 input_rows=4 output_rows=4 split_k=0
GGML_RISCV_QBS_CALL type=q4_K mode=gemm k=256 input_rows=4 output_rows=4 split_k=0
GGML_RISCV_MODEL_NODE op=FLASH_ATTN_EXT type=f32 ne0=8 ne1=4 ne2=1 ne3=1 src0=f32 src1=f16 fused_followers=0 fused_next=NONE name=blk.0.attn
GGML_RISCV_MODEL_GRAPH_END id=0
GGML_RISCV_MODEL_GRAPH_BEGIN id=1 nodes=2
GGML_RISCV_MODEL_NODE op=MUL_MAT type=f32 ne0=8 ne1=1 ne2=1 ne3=1 src0=q4_K src1=f32 fused_followers=0 fused_next=NONE name=blk.0.attn_q
GGML_RISCV_QBS_CALL type=q4_K mode=gemv k=256 input_rows=1 output_rows=8 split_k=0
GGML_RISCV_MODEL_NODE op=FLASH_ATTN_EXT type=f32 ne0=8 ne1=1 ne2=1 ne3=1 src0=f32 src1=f16 fused_followers=0 fused_next=NONE name=blk.0.attn
GGML_RISCV_AKV_EXEC kernel=v2 kv_heads=1 q_rows=6 gqa_rows=6 head_dim=8 active_kv=4 attention_macs=384
GGML_RISCV_MODEL_GRAPH_END id=1
GGML_RISCV_QBS_COVERAGE type=Q4_K candidate_tensors=1 selected_tensors=1 candidate_elements=64 selected_elements=64 fallback_runtime=0 fallback_format_filter=0 fallback_capability=0 fallback_dimensions=0 fallback_shape=0 fallback_layout=0 fallback_profile=0 fallback_dispatch=0
GGML_RISCV_QBS_EXEC type=Q4_K gemv_calls=1 gemm_calls=1 input_rows=5 output_rows=16 activation_elements=1280 output_elements=40 dot_elements=10240 split_calls=0 commands_m1=1 commands_m2=0 commands_m3=0 commands_m4=1 native_qbexec=3 emulated_commands=0 command_dot_elements=10240 segmented_commands=0 context_fill=2 context_reuse=0 context_release=2
GGML_RISCV_AKV_COVERAGE candidate_ops=2 executed_ops=1 groups=1 executed_v1=0 executed_v2=1 groups_v1=0 groups_v2=1 kv_group_tokens=4 attention_macs=384 fallback_runtime=0 fallback_capability=0 fallback_threading=0 fallback_feature=0 fallback_shape=1 fallback_layout=0 fallback_mask=0
AKV_TOKEN_RUN_EXIT=QBS_AKV_V2:0
QBS_RVV_LOGITS_RECORDS=1
QBS_RVV_LOGITS_COMPARABLE_RECORDS=1
QBS_RVV_LOGITS_MAX_ABS=0.25
QBS_RVV_LOGITS_MAX_REL=0.5
QBS_RVV_LOGITS_TOP1_EQUAL=1
QBS_RVV_TOKEN_OUTPUT_EQUAL=1
AKV_LOGITS_TOP1_EQUAL=1
AKV_LOGITS_MAX_ABS=0
AKV_TOKEN_OUTPUT_EQUAL=1
LLAMA_GUEST_EXIT=0
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qemu.log"
            path.write_text(trace)
            run = MODULE.parse_log(path)
        MODULE.validate_dynamic(run)
        qbs_call_rows, qbs_node_rows, akv_rows, node_rows = MODULE.dynamic_rows(run)
        self.assertEqual([graph.phase for graph in run.graphs], ["prefill", "decode"])
        self.assertEqual(sum(row["calls"] for row in qbs_call_rows), 3)
        self.assertEqual(sum(row["dot_elements"] for row in qbs_call_rows), 10240)
        self.assertEqual(sum(row["weight_payload_bytes"] for row in qbs_call_rows), 2304)
        self.assertEqual(len(qbs_node_rows), 2)
        self.assertEqual(sum(row["activation_elements"] for row in qbs_node_rows), 1280)
        self.assertEqual(sum(row["dot_elements"] for row in qbs_node_rows), 10240)
        self.assertEqual(sum(row["attention_macs"] for row in akv_rows), 384)
        self.assertEqual(sum(row["query_payload_bytes"] for row in akv_rows), 96)
        self.assertEqual(sum(row["kv_payload_bytes"] for row in akv_rows), 128)
        self.assertEqual(akv_rows[0]["gqa_rows"], 6)
        self.assertEqual(akv_rows[0]["head_dim"], 8)
        self.assertEqual(sum(row["count"] for row in node_rows), 4)

        saved_akv_calls = run.graphs[1].akv_calls
        run.graphs[1].akv_calls = []
        with self.assertRaisesRegex(ValueError, "AKV call/coverage MAC count mismatch"):
            MODULE.validate_dynamic(run)
        run.graphs[1].akv_calls = saved_akv_calls

        run.graphs[1].akv_calls = saved_akv_calls * 2
        with self.assertRaisesRegex(ValueError, "AKV graph coverage mismatch"):
            MODULE.validate_dynamic(run)
        run.graphs[1].akv_calls = saved_akv_calls

        saved_coverage = run.akv_coverage.copy()
        run.graphs[1].akv_calls = []
        run.akv_coverage.update(
            executed_ops="0",
            groups="0",
            executed_v2="0",
            groups_v2="0",
            kv_group_tokens="0",
            attention_macs="0",
            fallback_shape="2",
        )
        MODULE.validate_dynamic(run)
        run.graphs[1].akv_calls = saved_akv_calls
        run.akv_coverage = saved_coverage

        run.graphs[1].nodes.append(
            {
                "op": "MUL_MAT",
                "type": "f32",
                "ne0": "8",
                "ne1": "1",
                "ne2": "1",
                "ne3": "1",
                "src0": "q4_K",
                "src1": "f32",
                "name": "blk.0.uncalled",
            }
        )
        with self.assertRaisesRegex(ValueError, "QBS graph coverage mismatch"):
            MODULE.validate_dynamic(run)

    def test_node_semantics_follow_graph_order(self):
        nodes = [
            {"op": "RMS_NORM", "name": "norm-0"},
            {"op": "MUL_MAT", "name": "Qcur-0"},
            {"op": "ADD", "name": "ffn_inp-0"},
            {"op": "RMS_NORM", "name": "norm-0"},
            {"op": "MUL_MAT", "name": "ffn_gate-0"},
            {"op": "GLU", "name": "ffn_swiglu-0"},
            {"op": "ADD", "name": "l_out-0"},
            {"op": "RMS_NORM", "name": "norm"},
            {"op": "MUL_MAT", "name": "result_output"},
        ]
        self.assertEqual(MODULE.node_semantic(nodes, 0), "attention_norm")
        self.assertEqual(MODULE.node_semantic(nodes, 2), "attention_residual")
        self.assertEqual(MODULE.node_semantic(nodes, 3), "ffn_norm")
        self.assertEqual(MODULE.node_semantic(nodes, 5), "ffn_activation")
        self.assertEqual(MODULE.node_semantic(nodes, 6), "ffn_residual")
        self.assertEqual(MODULE.node_semantic(nodes, 7), "final_norm")

    def test_prefill_tail_is_one_high_level_qbs_node(self):
        graph = MODULE.Graph(
            graph_id=0,
            declared_nodes=1,
            nodes=[
                {
                    "op": "MUL_MAT",
                    "type": "f32",
                    "ne0": "8",
                    "ne1": "5",
                    "ne2": "1",
                    "ne3": "1",
                    "src0": "q4_K",
                    "src1": "f32",
                    "name": "blk.0.attn_q",
                }
            ],
            qbs_calls=[
                {"_node_index": "0", "type": "q4_K", "mode": "gemm", "k": "256", "input_rows": "4", "output_rows": "4", "split_k": "0"},
                {"_node_index": "0", "type": "q4_K", "mode": "gemm", "k": "256", "input_rows": "4", "output_rows": "4", "split_k": "0"},
                {"_node_index": "0", "type": "q4_K", "mode": "gemv", "k": "256", "input_rows": "1", "output_rows": "4", "split_k": "0"},
                {"_node_index": "0", "type": "q4_K", "mode": "gemv", "k": "256", "input_rows": "1", "output_rows": "4", "split_k": "0"},
            ],
            closed=True,
        )
        run = MODULE.ParsedRun([graph], {}, {}, {}, {}, {}, False, 0, 0)
        qbs_call_rows, qbs_node_rows, _, _ = MODULE.dynamic_rows(run)
        self.assertEqual(sum(row["calls"] for row in qbs_call_rows), 4)
        self.assertEqual(len(qbs_node_rows), 1)
        self.assertEqual(qbs_node_rows[0]["mode"], "gemm+gemv_tail")
        self.assertEqual(qbs_node_rows[0]["activation_elements"], 1280)
        self.assertEqual(qbs_node_rows[0]["dot_elements"], 10240)
        self.assertEqual(qbs_node_rows[0]["weight_payload_bytes"], 2304)

    def test_mul_mat_id_counts_routed_work_but_one_source_activation(self):
        graph = MODULE.Graph(
            graph_id=0,
            declared_nodes=1,
            nodes=[
                {
                    "op": "MUL_MAT_ID",
                    "type": "f32",
                    "ne0": "64",
                    "ne1": "2",
                    "ne2": "1",
                    "ne3": "1",
                    "src0": "q4_K",
                    "src1": "f32",
                    "src1_ne1": "1",
                    "src1_ne2": "1",
                    "src1_ne3": "1",
                    "name": "blk.0.ffn_gate_exps",
                }
            ],
            qbs_calls=[
                {"_node_index": "0", "type": "q4_K", "mode": "gemv", "k": "256", "input_rows": "1", "output_rows": "64", "split_k": "0"},
                {"_node_index": "0", "type": "q4_K", "mode": "gemv", "k": "256", "input_rows": "1", "output_rows": "64", "split_k": "0"},
            ],
            closed=True,
        )
        run = MODULE.ParsedRun([graph], {}, {}, {}, {}, {}, False, 0, 0)
        qbs_call_rows, qbs_node_rows, _, _ = MODULE.dynamic_rows(run)
        self.assertEqual(qbs_node_rows[0]["operation"], "MUL_MAT_ID")
        self.assertEqual(qbs_node_rows[0]["input_rows"], 2)
        self.assertEqual(qbs_node_rows[0]["activation_rows"], 1)
        self.assertEqual(qbs_node_rows[0]["activation_accounting"], "exact_source_shape")
        self.assertEqual(qbs_node_rows[0]["activation_elements"], 256)
        self.assertEqual(qbs_node_rows[0]["dot_elements"], 32768)
        self.assertEqual(sum(row["weight_payload_bytes"] for row in qbs_call_rows), 18432)

    def test_mul_mat_id_legacy_trace_does_not_guess_activation_rows(self):
        graph = MODULE.Graph(
            graph_id=0,
            declared_nodes=1,
            nodes=[{
                "op": "MUL_MAT_ID", "type": "f32", "ne0": "64", "ne1": "2",
                "ne2": "1", "ne3": "1", "src0": "q4_K", "src1": "f32",
                "name": "blk.0.ffn_gate_exps",
            }],
            qbs_calls=[
                {"_node_index": "0", "type": "q4_K", "mode": "gemv", "k": "256", "input_rows": "1", "output_rows": "64", "split_k": "0"},
                {"_node_index": "0", "type": "q4_K", "mode": "gemv", "k": "256", "input_rows": "1", "output_rows": "64", "split_k": "0"},
            ],
            closed=True,
        )
        run = MODULE.ParsedRun([graph], {}, {}, {}, {}, {}, False, 0, 0)
        _, qbs_node_rows, _, _ = MODULE.dynamic_rows(run)
        row = qbs_node_rows[0]
        self.assertIsNone(row["activation_rows"])
        self.assertIsNone(row["activation_elements"])
        self.assertIsNone(row["quantized_activation_bytes"])
        self.assertEqual(row["activation_accounting"], "unavailable_legacy_source_shape")

    def test_qbs_payload_accounting_rejects_partial_blocks(self):
        with self.assertRaisesRegex(ValueError, "not divisible"):
            MODULE.blocked_payload_bytes(255, 1, 1, 144, 256, "Q4_K weight")

    def test_decode_remainder_uses_type_and_shape_specific_calibrations(self):
        common = {
            "phase": "decode",
            "semantic": "",
            "type": "f32",
            "ne1": "1",
            "ne2": "1",
            "ne3": "1",
            "src1": "i32",
        }
        cases = [
            (
                {**common, "op": "ADD", "ne0": "1536", "src0": "f32", "src1": "f32"},
                ("rvv_bias", "calibration/decode/qkv_bias_1536"),
            ),
            (
                {**common, "op": "ADD", "ne0": "256", "src0": "f32", "src1": "f32"},
                ("rvv_bias", "calibration/decode/qkv_bias_256"),
            ),
            (
                {
                    **common,
                    "op": "SET_ROWS",
                    "type": "f16",
                    "ne0": "256",
                    "ne1": "256",
                    "src0": "f32",
                    "src1": "i64",
                },
                ("rvv_cache_update", "calibration/decode/cache_set_rows_f32_f16"),
            ),
            (
                {**common, "op": "GET_ROWS", "ne0": "1536", "src0": "f32"},
                ("rvv_row_gather", "calibration/decode/get_rows_f32"),
            ),
            (
                {**common, "op": "GET_ROWS", "ne0": "1536", "src0": "q4_K"},
                ("rvv_row_gather", "calibration/decode/get_rows_q4_k"),
            ),
        ]
        for row, expected in cases:
            with self.subTest(row=row):
                self.assertEqual(MODULE.classify_rvv_node(row), expected)

        wrong_shape = {**common, "op": "GET_ROWS", "ne0": "1536", "ne1": "2", "src0": "f32"}
        self.assertIsNone(MODULE.classify_rvv_node(wrong_shape))

    def test_akv_calibration_description_uses_loaded_points(self):
        points = [
            {"active_kv": 16, "cycles": 100},
            {"active_kv": 128, "cycles": 500},
        ]
        self.assertEqual(
            MODULE.describe_akv_calibration(points),
            "piecewise AKV-v2 KV16/KV128 RTL",
        )

    def test_component_shares_exclude_an_incomplete_phase(self):
        rows = [
            {
                "phase": "decode",
                "category": "qbs",
                "instances": 2,
                "projected_cycles": 75,
            },
            {
                "phase": "decode",
                "category": "rvv_norm",
                "instances": 1,
                "projected_cycles": 25,
            },
            {
                "phase": "prefill",
                "category": "qbs",
                "instances": 2,
                "projected_cycles": 200,
            },
            {
                "phase": "prefill",
                "category": "uncalibrated",
                "instances": 1,
                "projected_cycles": "",
            },
        ]
        summary = MODULE.aggregate_components(rows)
        self.assertEqual(
            [(row["phase"], row["component"]) for row in summary],
            [("decode", "qbs"), ("decode", "rvv_remaining")],
        )
        self.assertEqual(
            [row["share_of_phase_cycles"] for row in summary],
            [0.75, 0.25],
        )


if __name__ == "__main__":
    unittest.main()
