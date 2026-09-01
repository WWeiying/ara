#!/usr/bin/env python3

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from census_prefill_shapes import analyze_case


def node_line(m: int, capacity: int = 256) -> str:
    return (
        "GGML_RISCV_MODEL_NODE op=FLASH_ATTN_EXT type=f32 "
        f"ne0=64 ne1=8 ne2={m} ne3=1 src0=f32 src1=f16 "
        f"src0_ne0=64 src0_ne1={m} src0_ne2=8 src0_ne3=1 "
        f"src1_ne0=64 src1_ne1={capacity} src1_ne2=2 src1_ne3=1 "
        f"src2=f16 src2_ne0=64 src2_ne1={capacity} src2_ne2=2 src2_ne3=1 "
        f"src3=f16 src3_ne0={capacity} src3_ne1={m} src3_ne2=1 src3_ne3=1 "
        "name=attn"
    )


def graph(graph_id: int, m: int, capacity: int = 256) -> list[str]:
    return [
        f"GGML_RISCV_MODEL_GRAPH_BEGIN id={graph_id} nodes=1",
        node_line(m, capacity),
        f"GGML_RISCV_MODEL_GRAPH_END id={graph_id}",
    ]


MODEL = {
    "id": "test",
    "name": "Test",
    "architecture": "test",
    "topology": "dense",
    "quantization": "Q4_K_M",
}


class CensusPrefillShapesTest(unittest.TestCase):
    def write_log(self, root: Path, prompt_tokens: int, chunks: list[int]) -> Path:
        lines = [f"prompt eval time = 1.0 ms / {prompt_tokens} tokens"]
        for index, tokens in enumerate(chunks):
            lines.extend(graph(index, tokens, 1024 if prompt_tokens > 256 else 256))
        lines.extend(graph(len(chunks), 1, 1024 if prompt_tokens > 256 else 256))
        path = root / "host.log"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_single_prefill_chunk(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = analyze_case(self.write_log(Path(directory), 15, [15]), MODEL, 16)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["M_query_tokens"], 15)
        self.assertEqual(row["P_past_tokens"], 0)
        self.assertEqual(row["gqa_rows"], 4)
        self.assertEqual(row["visible_pairs_per_q_head"], 120)
        self.assertEqual(row["attention_macs"], 122880)
        self.assertEqual(row["fast_path_disposition"], "candidate")

    def test_chunked_prefill_tracks_past_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = analyze_case(
                self.write_log(Path(directory), 1023, [512, 511]), MODEL, 1024
            )
        self.assertEqual([row["M_query_tokens"] for row in rows], [512, 511])
        self.assertEqual([row["P_past_tokens"] for row in rows], [0, 512])
        self.assertEqual([row["visible_kv_end"] for row in rows], [512, 1023])

    def test_rejects_prompt_not_covered_by_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            log = self.write_log(Path(directory), 15, [14])
            with self.assertRaisesRegex(ValueError, "cover 14 tokens"):
                analyze_case(log, MODEL, 16)


if __name__ == "__main__":
    unittest.main()
