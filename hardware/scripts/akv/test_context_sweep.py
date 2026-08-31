#!/usr/bin/env python3

import json
import tempfile
import unittest
from pathlib import Path

from context_sweep import parse_graphs, summarize_graphs, validate_reference


ABI = {
    "weight_profiles": {
        "Q4_K": {
            "block_bytes": 144,
            "block_elements": 256,
            "activation_profiles": ["Q8_K"],
        }
    },
    "activation_profiles": {
        "Q8_K": {"block_bytes": 292, "block_elements": 256}
    },
}


def node(op, src0, ne0, ne1, src0_shape, name, extra=""):
    s0 = " ".join(f"src0_ne{i}={value}" for i, value in enumerate(src0_shape))
    empty = " ".join(
        [
            "src1_ne0=0 src1_ne1=0 src1_ne2=0 src1_ne3=0",
            "src2=NONE src2_ne0=0 src2_ne1=0 src2_ne2=0 src2_ne3=0",
            "src3=NONE src3_ne0=0 src3_ne1=0 src3_ne2=0 src3_ne3=0",
        ]
    )
    return (
        f"GGML_RISCV_MODEL_NODE op={op} type=f32 ne0={ne0} ne1={ne1} ne2=1 ne3=1 "
        f"src0={src0} src1=f32 {s0} {empty} {extra} fused_followers=0 fused_next=NONE name={name}"
    )


class ContextSweepTest(unittest.TestCase):
    def write_log(self, text):
        handle = tempfile.NamedTemporaryFile("w", delete=False)
        handle.write(text)
        handle.close()
        self.addCleanup(Path(handle.name).unlink)
        return Path(handle.name)

    def test_decode_accounting_and_reference(self):
        matmul = node("MUL_MAT", "q4_K", 64, 1, (256, 64, 1, 1), "ffn")
        attention = (
            "GGML_RISCV_MODEL_NODE op=FLASH_ATTN_EXT type=f32 ne0=128 ne1=12 ne2=1 ne3=1 "
            "src0=f32 src1=f16 src0_ne0=128 src0_ne1=1 src0_ne2=12 src0_ne3=1 "
            "src1_ne0=128 src1_ne1=256 src1_ne2=2 src1_ne3=1 "
            "src2=f16 src2_ne0=128 src2_ne1=256 src2_ne2=2 src2_ne3=1 "
            "src3=f16 src3_ne0=256 src3_ne1=1 src3_ne2=1 src3_ne3=1 "
            "fused_followers=0 fused_next=NONE name=attention"
        )
        log = self.write_log("\n".join([
            "GGML_RISCV_MODEL_GRAPH_BEGIN id=0 nodes=2", matmul, attention,
            "GGML_RISCV_MODEL_GRAPH_END id=0",
            "GGML_RISCV_MODEL_GRAPH_BEGIN id=1 nodes=2", matmul, attention,
            "GGML_RISCV_MODEL_GRAPH_END id=1",
        ]))
        summary = summarize_graphs(parse_graphs(log), 128, ABI)
        decode = summary["decode"]
        self.assertEqual(decode["qbs_candidate_compute_nodes"], 1)
        self.assertEqual(decode["qbs_dot_elements"], 16384)
        self.assertEqual(decode["qbs_weight_logical_bytes"], 9216)
        self.assertEqual(decode["qbs_activation_logical_bytes_without_cross_op_reuse"], 292)
        self.assertEqual(decode["akv_shape_eligible_compute_nodes"], 1)
        self.assertEqual(decode["akv_shape_eligible_groups"], 2)
        self.assertEqual(decode["akv_kv_payload_logical_bytes"], 131072)
        reference = {
            "qbs": {"nodes": 2, "coverage": {"Q4_K": {}}},
            "akv_v2": {
                "coverage": {"candidate_ops": "2"},
                "shapes": [{"head_dim": 128, "q_rows": 12, "kv_heads": 2, "gqa_rows": 6}],
            },
        }
        validate_reference(summary, reference)

    def test_unsupported_gqa_stays_on_rvv(self):
        matmul = node("MUL_MAT", "q4_K", 64, 1, (256, 64, 1, 1), "ffn")
        attention = (
            "GGML_RISCV_MODEL_NODE op=FLASH_ATTN_EXT type=f32 ne0=64 ne1=12 ne2=1 ne3=1 "
            "src0=f32 src1=f16 src0_ne0=64 src0_ne1=1 src0_ne2=12 src0_ne3=1 "
            "src1_ne0=64 src1_ne1=128 src1_ne2=4 src1_ne3=1 "
            "src2=f16 src2_ne0=64 src2_ne1=128 src2_ne2=4 src2_ne3=1 "
            "src3=f16 src3_ne0=128 src3_ne1=1 src3_ne2=1 src3_ne3=1 "
            "fused_followers=0 fused_next=NONE name=attention"
        )
        log = self.write_log("\n".join([
            "GGML_RISCV_MODEL_GRAPH_BEGIN id=0 nodes=2", matmul, attention,
            "GGML_RISCV_MODEL_GRAPH_END id=0",
            "GGML_RISCV_MODEL_GRAPH_BEGIN id=1 nodes=2", matmul, attention,
            "GGML_RISCV_MODEL_GRAPH_END id=1",
        ]))
        decode = summarize_graphs(parse_graphs(log), 16, ABI)["decode"]
        self.assertEqual(decode["akv_shape_eligible_compute_nodes"], 0)
        self.assertEqual(decode["akv_shape_fallback_compute_nodes"], 1)
        self.assertEqual(decode["ordinary_rvv_compute_nodes_if_akv_shape_selected"], 1)

    def test_rejects_incomplete_graph(self):
        log = self.write_log("GGML_RISCV_MODEL_GRAPH_BEGIN id=0 nodes=1\n")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            parse_graphs(log)

    def test_accepts_generated_text_before_trace_marker(self):
        graph = "\n".join([
            "generated tokenGGML_RISCV_MODEL_GRAPH_BEGIN id=1 nodes=1",
            node("MUL_MAT", "q4_K", 64, 1, (256, 64, 1, 1), "ffn"),
            "GGML_RISCV_MODEL_GRAPH_END id=1",
        ])
        parsed = parse_graphs(self.write_log(graph))
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].graph_id, 1)
        self.assertEqual(len(parsed[0].nodes), 1)


if __name__ == "__main__":
    unittest.main()
