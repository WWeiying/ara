#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("package_prefill_attention_capture.py")
SPEC = importlib.util.spec_from_file_location("package_prefill", MODULE_PATH)
package_prefill = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(package_prefill)


class PackagePrefillAttentionTest(unittest.TestCase):
    def write_tensor(self, block: Path, stem: str, tensor_type: str,
                     shape: list[int], payload: bytes) -> None:
        element_bytes = package_prefill.TYPE_BYTES[tensor_type]
        strides = package_prefill.contiguous_strides(shape, element_bytes)
        (block / f"{stem}.bin").write_bytes(payload)
        (block / f"{stem}.json").write_text(
            json.dumps({
                "type": tensor_type,
                "shape": shape,
                "strides": strides,
                "nbytes": len(payload),
            }) + "\n",
            encoding="utf-8",
        )

    def write_chunk(self, root: Path, index: int, query_tokens: int,
                    past_tokens: int, malformed_mask: bool = False) -> None:
        block = root / "prefill" / f"chunk-{index}" / "block"
        block.mkdir(parents=True)
        dim, q_heads, kv_heads = 4, 2, 1
        capacity = past_tokens + query_tokens
        shapes = {
            "attn_q_input-0": ("f32", [dim, query_tokens, q_heads, 1]),
            "attn_k_input-0": ("f16", [dim, capacity, kv_heads, 1]),
            "attn_v_input-0": ("f16", [dim, capacity, kv_heads, 1]),
            "kqv_out-0": ("f32", [dim * q_heads, query_tokens, 1, 1]),
        }
        for stem, (tensor_type, shape) in shapes.items():
            count = 1
            for value in shape:
                count *= value
            self.write_tensor(
                block, stem, tensor_type, shape,
                bytes(count * package_prefill.TYPE_BYTES[tensor_type]),
            )
        mask = []
        for token in range(query_tokens):
            prefix = past_tokens + token + 1
            row = [0x0000] * prefix + [0xFC00] * (capacity - prefix)
            mask.extend(row)
        if malformed_mask:
            mask[capacity + past_tokens + 1] = 0xFC00
        self.write_tensor(
            block,
            "attn_mask_input-0",
            "f16",
            [capacity, query_tokens, 1, 1],
            struct.pack(f"<{len(mask)}H", *mask),
        )
        (block / "attention_params-0.json").write_text(
            json.dumps({
                "op": "GGML_OP_SOFT_MAX",
                "scale": 0.5,
                "max_bias": 0.0,
                "logit_softcap": 0.0,
            }) + "\n",
            encoding="utf-8",
        )

    def make_root(self, directory: str) -> Path:
        root = Path(directory)
        (root / "model.json").write_text(
            json.dumps({"description": "test model"}) + "\n",
            encoding="utf-8",
        )
        return root

    def test_packages_contiguous_chunks_and_derives_past_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            self.write_chunk(root, 0, 3, 0)
            self.write_chunk(root, 1, 2, 3)
            summary = package_prefill.package(root, 0.004, 0.002)
            manifest = json.loads((root / "replay/manifest.json").read_text())
        self.assertEqual(summary["chunk_count"], 2)
        self.assertEqual(
            [(row["atol"], row["rtol"]) for row in summary["chunks"]],
            [(0.004, 0.002), (0.004, 0.002)],
        )
        self.assertEqual(
            [(row["M_query_tokens"], row["P_past_tokens"])
             for row in summary["chunks"]],
            [(3, 0), (2, 3)],
        )
        self.assertEqual(
            [row["id"] for row in manifest["cases"]],
            [
                "operator/prefill/chunk_0/attention_core",
                "operator/prefill/chunk_1/attention_core",
            ],
        )

    def test_rejects_a_mask_hole(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            self.write_chunk(root, 0, 3, 0, malformed_mask=True)
            with self.assertRaisesRegex(ValueError, "causal prefix"):
                package_prefill.package(root, 0.004, 0.002)

    def test_rejects_missing_chunk_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_root(directory)
            self.write_chunk(root, 1, 2, 0)
            with self.assertRaisesRegex(ValueError, "not contiguous"):
                package_prefill.package(root, 0.004, 0.002)


if __name__ == "__main__":
    unittest.main()
