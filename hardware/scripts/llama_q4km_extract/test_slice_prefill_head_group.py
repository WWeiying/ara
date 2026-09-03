#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("slice-prefill-head-group.py")
SPEC = importlib.util.spec_from_file_location("slice_prefill_head_group", MODULE_PATH)
slice_prefill = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(slice_prefill)


class SlicePrefillHeadGroupTest(unittest.TestCase):
    case_id = "operator/prefill/p0_m2/attention_core"

    def emit_tensor(self, case_dir: Path, name: str, tensor_type: str,
                    shape: list[int], values: list[int]) -> str:
        if tensor_type == "f32":
            payload = struct.pack(f"<{len(values)}f", *values)
        else:
            payload = struct.pack(f"<{len(values)}H", *values)
        metadata = {
            "type": tensor_type,
            "shape": shape,
            "strides": slice_prefill.contiguous_strides(
                shape, slice_prefill.TYPE_BYTES[tensor_type]
            ),
            "nbytes": len(payload),
        }
        (case_dir / f"{name}.json").write_text(
            json.dumps(metadata) + "\n", encoding="utf-8"
        )
        (case_dir / f"{name}.bin").write_bytes(payload)
        return f"{name}.json"

    def make_source(self, root: Path) -> None:
        case_dir = root / "replay/cases" / self.case_id
        case_dir.mkdir(parents=True)
        # D=2, M=2, Hq=6, Hkv=2: three Query rows per KV head.
        case = {"kind": "attention_core", "scale": 0.5,
                "max_bias": 0.0, "logit_softcap": 0.0,
                "v_transposed": False, "atol": 0.01, "rtol": 0.0}
        case["input_a"] = self.emit_tensor(
            case_dir, "input_a", "f32", [2, 2, 6, 1], list(range(24))
        )
        case["key"] = self.emit_tensor(
            case_dir, "key", "f16", [2, 2, 2, 1], list(range(8))
        )
        case["value"] = self.emit_tensor(
            case_dir, "value", "f16", [2, 2, 2, 1], list(range(100, 108))
        )
        case["mask"] = self.emit_tensor(
            case_dir, "mask", "f16", [2, 2, 1, 1],
            [0x0000, 0xFC00, 0x0000, 0x0000],
        )
        # Golden layout is [D * Hq, M], so each token contains all heads.
        case["golden"] = self.emit_tensor(
            case_dir, "golden", "f32", [12, 2, 1, 1],
            list(range(200, 224)),
        )
        (case_dir / "case.json").write_text(
            json.dumps(case) + "\n", encoding="utf-8"
        )
        (root / "replay/manifest.json").write_text(
            json.dumps({
                "schema_version": 1,
                "model": "unit-test",
                "cases": [{
                    "id": self.case_id,
                    "level": "operator-leaf",
                    "kind": "attention_core",
                    "path": str(case_dir.relative_to(root)),
                }],
            }) + "\n",
            encoding="utf-8",
        )

    def test_selects_two_query_rows_and_matching_kv_head(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "output"
            self.make_source(source)
            manifest = slice_prefill.slice_capture(
                source, output, self.case_id,
                kv_head=1, query_row_start=1, query_rows=2,
            )
            case_dir = output / "replay/cases" / self.case_id
            query = struct.unpack("<8f", (case_dir / "input_a.bin").read_bytes())
            key = struct.unpack("<4H", (case_dir / "key.bin").read_bytes())
            value = struct.unpack("<4H", (case_dir / "value.bin").read_bytes())
            golden = struct.unpack("<8f", (case_dir / "golden.bin").read_bytes())

        self.assertEqual(manifest["topology"]["gqa_rows"], 2)
        self.assertEqual(manifest["topology"]["active_kv"], 2)
        self.assertEqual(query, tuple(float(value) for value in range(16, 24)))
        self.assertEqual(key, tuple(range(4, 8)))
        self.assertEqual(value, tuple(range(104, 108)))
        # Source heads 4 and 5 occupy elements 8..11 in each token row.
        self.assertEqual(golden, (208.0, 209.0, 210.0, 211.0,
                                  220.0, 221.0, 222.0, 223.0))

    def test_rejects_query_rows_crossing_source_gqa_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            self.make_source(source)
            with self.assertRaisesRegex(ValueError, "exceeds source GQA"):
                slice_prefill.slice_capture(
                    source, root / "output", self.case_id,
                    kv_head=0, query_row_start=2, query_rows=2,
                )


if __name__ == "__main__":
    unittest.main()
