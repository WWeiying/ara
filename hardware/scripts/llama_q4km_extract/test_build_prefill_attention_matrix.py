#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_prefill_attention_matrix.py")
SPEC = importlib.util.spec_from_file_location("build_prefill_matrix", MODULE_PATH)
matrix = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = matrix
SPEC.loader.exec_module(matrix)


class BuildPrefillAttentionMatrixTest(unittest.TestCase):
    def write_tensor(self, case_dir: Path, role: str, tensor_type: str,
                     shape: list[int], payload: bytes) -> str:
        metadata = {
            "type": tensor_type,
            "shape": shape,
            "strides": matrix.contiguous_strides(
                shape, matrix.TYPE_BYTES[tensor_type]
            ),
            "nbytes": len(payload),
        }
        (case_dir / f"{role}.json").write_text(
            json.dumps(metadata) + "\n", encoding="utf-8"
        )
        (case_dir / f"{role}.bin").write_bytes(payload)
        return f"{role}.json"

    def make_source(self, root: Path) -> str:
        case_id = "operator/prefill/chunk_0/attention_core"
        case_dir = root / "replay/cases" / case_id
        case_dir.mkdir(parents=True)
        dim, tokens, q_heads, kv_capacity, kv_heads = 4, 4, 2, 8, 1
        case = {
            "kind": "attention_core",
            "scale": 0.5,
            "max_bias": 0.0,
            "logit_softcap": 0.0,
            "v_transposed": False,
            "atol": 0.012,
            "rtol": 0.002,
        }
        shapes = {
            "input_a": ("f32", [dim, tokens, q_heads, 1]),
            "key": ("f16", [dim, kv_capacity, kv_heads, 1]),
            "value": ("f16", [dim, kv_capacity, kv_heads, 1]),
            "golden": ("f32", [dim * q_heads, tokens, 1, 1]),
        }
        for role, (tensor_type, shape) in shapes.items():
            elements = 1
            for dimension in shape:
                elements *= dimension
            case[role] = self.write_tensor(
                case_dir, role, tensor_type, shape,
                bytes(elements * matrix.TYPE_BYTES[tensor_type]),
            )
        mask_values = []
        for prefix in (4, 5, 6, 7):
            mask_values.extend([0x0000] * prefix)
            mask_values.extend([0xFC00] * (kv_capacity - prefix))
        case["mask"] = self.write_tensor(
            case_dir, "mask", "f16", [kv_capacity, tokens, 1, 1],
            struct.pack(f"<{len(mask_values)}H", *mask_values),
        )
        (case_dir / "case.json").write_text(
            json.dumps(case) + "\n", encoding="utf-8"
        )
        (root / "model.json").write_text(
            json.dumps({"description": "test model"}) + "\n",
            encoding="utf-8",
        )
        (root / "replay/manifest.json").write_text(
            json.dumps({
                "schema_version": 1,
                "cases": [{"id": case_id, "path": f"replay/cases/{case_id}"}],
            }) + "\n",
            encoding="utf-8",
        )
        return case_id

    def test_builds_deduplicated_real_prefix_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "matrix"
            case_id = self.make_source(source)
            spec = matrix.SourceSpec(source, case_id, (2, 4))
            result = matrix.build(output, [spec])
            short_case = output / (
                "replay/cases/operator/prefill/p3_m2/attention_core"
            )
            query = json.loads((short_case / "input_a.json").read_text())
            source_key = source / f"replay/cases/{case_id}/key.bin"
            matrix_key = short_case / "key.bin"
            self.assertEqual(result["case_count"], 2)
            self.assertEqual(result["cases"][0]["attention_macs"], 144)
            self.assertEqual(result["cases"][0]["atol"], 0.012)
            self.assertEqual(result["cases"][0]["rtol"], 0.002)
            self.assertEqual(query["shape"], [4, 2, 2, 1])
            self.assertEqual(source_key.read_bytes(), matrix_key.read_bytes())
            self.assertEqual(
                source_key.stat().st_ino, matrix_key.stat().st_ino
            )
            self.assertTrue((output / "replay/complete").is_file())

    def test_rejects_existing_output_without_removing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "matrix"
            output.mkdir()
            marker = output / "keep"
            marker.write_text("keep\n", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "already exists"):
                matrix.build(output, [])
            self.assertTrue(marker.is_file())

    def test_rejects_token_count_beyond_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "matrix"
            case_id = self.make_source(source)
            spec = matrix.SourceSpec(source, case_id, (5,))
            with self.assertRaisesRegex(ValueError, "source M=4"):
                matrix.build(output, [spec])
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
