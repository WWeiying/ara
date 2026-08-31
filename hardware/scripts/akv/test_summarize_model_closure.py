#!/usr/bin/env python3

import importlib.util
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
    def test_combined_trace_is_partitioned_and_cross_checked(self):
        trace = """\
AKV_TOKEN_RUN_BEGIN=RVV
AKV_TOKEN_RUN_EXIT=RVV:0
AKV_TOKEN_RUN_BEGIN=QBS_ONLY
AKV_TOKEN_RUN_EXIT=QBS_ONLY:0
AKV_TOKEN_RUN_BEGIN=QBS_AKV_V2
GGML_RISCV_MODEL_GRAPH_BEGIN id=0 nodes=2
GGML_RISCV_MODEL_NODE op=MUL_MAT type=f32 ne0=8 ne1=4 ne2=1 ne3=1 src0=q4_K src1=f32 fused_followers=0 fused_next=NONE name=blk.0.attn_q
GGML_RISCV_QBS_CALL type=q4_K mode=gemm k=8 input_rows=4 output_rows=8 split_k=0
GGML_RISCV_MODEL_GRAPH_END id=0
GGML_RISCV_MODEL_GRAPH_BEGIN id=1 nodes=2
GGML_RISCV_MODEL_NODE op=MUL_MAT type=f32 ne0=8 ne1=1 ne2=1 ne3=1 src0=q4_K src1=f32 fused_followers=0 fused_next=NONE name=blk.0.attn_q
GGML_RISCV_QBS_CALL type=q4_K mode=gemv k=8 input_rows=1 output_rows=8 split_k=0
GGML_RISCV_MODEL_NODE op=FLASH_ATTN_EXT type=f32 ne0=8 ne1=1 ne2=1 ne3=1 src0=f32 src1=f16 fused_followers=0 fused_next=NONE name=blk.0.attn
GGML_RISCV_AKV_EXEC kernel=v2 kv_heads=1 q_rows=6 active_kv=4 attention_macs=384
GGML_RISCV_MODEL_GRAPH_END id=1
GGML_RISCV_QBS_COVERAGE type=Q4_K candidate_tensors=1 selected_tensors=1 candidate_elements=64 selected_elements=64 fallback_runtime=0 fallback_format_filter=0 fallback_capability=0 fallback_dimensions=0 fallback_shape=0 fallback_layout=0 fallback_profile=0 fallback_dispatch=0
GGML_RISCV_QBS_EXEC type=Q4_K gemv_calls=1 gemm_calls=1 input_rows=5 output_rows=16 activation_elements=40 output_elements=40 dot_elements=320 split_calls=0 commands_m1=1 commands_m2=0 commands_m3=0 commands_m4=1 native_qbexec=2 emulated_commands=0 command_dot_elements=320 segmented_commands=0 context_fill=2 context_reuse=0 context_release=2
GGML_RISCV_AKV_COVERAGE candidate_ops=2 executed_ops=1 groups=1 executed_v1=0 executed_v2=1 groups_v1=0 groups_v2=1 kv_group_tokens=4 attention_macs=384 fallback_runtime=0 fallback_capability=0 fallback_threading=0 fallback_feature=0 fallback_shape=1 fallback_layout=0 fallback_mask=0
AKV_TOKEN_RUN_EXIT=QBS_AKV_V2:0
QBS_RVV_LOGITS_RECORDS=1
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
        qbs_rows, akv_rows, node_rows = MODULE.dynamic_rows(run)
        self.assertEqual([graph.phase for graph in run.graphs], ["prefill", "decode"])
        self.assertEqual(sum(row["dot_elements"] for row in qbs_rows), 320)
        self.assertEqual(sum(row["attention_macs"] for row in akv_rows), 384)
        self.assertEqual(sum(row["count"] for row in node_rows), 3)

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


if __name__ == "__main__":
    unittest.main()
