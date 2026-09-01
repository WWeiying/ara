#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).with_name(
    "validate_prefill_attention_reference.py"
)
SPEC = importlib.util.spec_from_file_location("validate_prefill", MODULE_PATH)
validate_prefill = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validate_prefill)


class ValidatePrefillAttentionReferenceTest(unittest.TestCase):
    def emit_tensor(self, case_dir: Path, role: str, tensor_type: str,
                    shape: list[int], values: np.ndarray) -> str:
        dtype = validate_prefill.TYPE_DTYPES[tensor_type]
        payload = np.asarray(values, dtype=dtype).tobytes()
        metadata = {
            "type": tensor_type,
            "shape": shape,
            "strides": validate_prefill.contiguous_strides(
                shape, dtype.itemsize
            ),
            "nbytes": len(payload),
        }
        (case_dir / f"{role}.json").write_text(
            json.dumps(metadata) + "\n", encoding="utf-8"
        )
        (case_dir / f"{role}.bin").write_bytes(payload)
        return f"{role}.json"

    def make_case(self, root: Path, golden_delta: float = 0.0) -> None:
        case_id = "operator/prefill/p0_m2/attention_core"
        case_dir = root / "replay/cases" / case_id
        case_dir.mkdir(parents=True)
        dim, tokens, query_heads, kv_heads, kv_capacity = 2, 2, 2, 1, 2
        query = np.asarray(
            [
                [[1, 0], [1, 0]],
                [[0, 1], [0, 1]],
            ],
            dtype=np.float32,
        )
        key = np.asarray([[[1, 0], [0, 1]]], dtype=np.float16)
        value = np.asarray([[[2, 4], [6, 8]]], dtype=np.float16)
        mask = np.asarray([[0, -np.inf], [0, 0]], dtype=np.float16)
        golden = np.asarray(
            [
                [[2, 4], [2, 4]],
                [[3.5101626, 5.5101626], [4.489837, 6.489837]],
            ],
            dtype=np.float32,
        )
        golden[1, 1, 0] += golden_delta
        case = {
            "kind": "attention_core",
            "scale": 0.5,
            "max_bias": 0.0,
            "logit_softcap": 0.0,
            "v_transposed": False,
            "atol": 0.01,
            "rtol": 0.0,
        }
        case["input_a"] = self.emit_tensor(
            case_dir, "input_a", "f32", [dim, tokens, query_heads, 1], query
        )
        case["key"] = self.emit_tensor(
            case_dir, "key", "f16", [dim, kv_capacity, kv_heads, 1], key
        )
        case["value"] = self.emit_tensor(
            case_dir, "value", "f16", [dim, kv_capacity, kv_heads, 1], value
        )
        case["mask"] = self.emit_tensor(
            case_dir, "mask", "f16", [kv_capacity, tokens, 1, 1], mask
        )
        case["golden"] = self.emit_tensor(
            case_dir, "golden", "f32", [dim * query_heads, tokens, 1, 1],
            golden,
        )
        (case_dir / "case.json").write_text(
            json.dumps(case) + "\n", encoding="utf-8"
        )
        (root / "replay/manifest.json").write_text(
            json.dumps({
                "cases": [{"id": case_id, "path": f"replay/cases/{case_id}"}]
            }) + "\n",
            encoding="utf-8",
        )

    def test_exact_causal_attention_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_case(root)
            result = validate_prefill.validate(root, query_block=2)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["cases"][0]["attention_macs"], 24)
        self.assertEqual(result["cases"][0]["mismatches"], 0)

    def test_reports_required_absolute_tolerance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_case(root, golden_delta=0.125)
            result = validate_prefill.validate(root, query_block=1)
        case = result["cases"][0]
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(case["mismatches"], 1)
        self.assertAlmostEqual(case["required_atol_at_rtol"], 0.125, places=6)
        self.assertEqual(case["first_mismatch"]["token"], 1)
        self.assertEqual(case["first_mismatch"]["head"], 1)
        self.assertEqual(case["first_mismatch"]["element"], 0)

    def test_tiled_online_schedule_crosses_kv_tiles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_case(root)
            result = validate_prefill.validate(
                root,
                query_block=2,
                kv_tile=1,
                quantize_query=True,
            )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["reference"],
                         "independent NumPy tiled online softmax")
        self.assertEqual(result["kv_tile"], 1)
        self.assertEqual(result["query_input"], "f16-converted")


if __name__ == "__main__":
    unittest.main()
