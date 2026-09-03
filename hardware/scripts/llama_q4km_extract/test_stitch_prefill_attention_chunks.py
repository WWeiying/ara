#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("stitch_prefill_attention_chunks.py")
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("stitch_prefill", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


def strides(shape: list[int], element_bytes: int) -> list[int]:
    result = [element_bytes]
    for dimension in shape[:3]:
        result.append(result[-1] * dimension)
    return result


class StitchPrefillTest(unittest.TestCase):
    def write_tensor(
        self, directory: Path, name: str, tensor_type: str, shape: list[int], payload: bytes
    ) -> str:
        path = directory / f"{name}.json"
        element_bytes = 2 if tensor_type == "f16" else 4
        path.write_text(json.dumps({
            "type": tensor_type,
            "shape": shape,
            "strides": strides(shape, element_bytes),
            "nbytes": len(payload),
        }) + "\n", encoding="utf-8")
        path.with_suffix(".bin").write_bytes(payload)
        return path.name

    def make_source(self, root: Path, corrupt_prefix: bool = False) -> Path:
        (root / "model.json").parent.mkdir(parents=True, exist_ok=True)
        (root / "model.json").write_text('{"model":"test"}\n', encoding="utf-8")
        entries = []
        all_k = [10, 11, 20, 21, 30, 31, 40, 41]
        if corrupt_prefix:
            all_k[0] = 99
        all_v = [110, 111, 120, 121, 130, 131, 140, 141]
        for index, (past, capacity, key, value) in enumerate((
            (0, 2, [10, 11, 20, 21], [110, 111, 120, 121]),
            (2, 4, all_k, all_v),
        )):
            case_id = f"operator/prefill/chunk_{index}/attention_core"
            case_dir = root / "replay" / "cases" / str(index)
            case_dir.mkdir(parents=True)
            query = struct.pack("<8f", *[float(index * 10 + item) for item in range(8)])
            golden = struct.pack("<8f", *[float(index * 20 + item) for item in range(8)])
            mask_rows = []
            for token in range(2):
                prefix = past + token + 1
                mask_rows.extend([0] * prefix + [0xFC00] * (capacity - prefix))
            case = {
                "kind": "attention_core",
                "input_a": self.write_tensor(case_dir, "input_a", "f32", [2, 2, 2, 1], query),
                "key": self.write_tensor(
                    case_dir, "key", "f16", [2, capacity, 1, 1], struct.pack(f"<{len(key)}H", *key)
                ),
                "value": self.write_tensor(
                    case_dir, "value", "f16", [2, capacity, 1, 1], struct.pack(f"<{len(value)}H", *value)
                ),
                "mask": self.write_tensor(
                    case_dir, "mask", "f16", [capacity, 2, 1, 1],
                    struct.pack(f"<{len(mask_rows)}H", *mask_rows),
                ),
                "golden": self.write_tensor(case_dir, "golden", "f32", [4, 2, 1, 1], golden),
                "scale": 0.5,
                "max_bias": 0.0,
                "logit_softcap": 0.0,
                "v_transposed": False,
                "atol": 0.004,
                "rtol": 0.002,
            }
            (case_dir / "case.json").write_text(json.dumps(case) + "\n", encoding="utf-8")
            entries.append({"id": case_id, "path": f"replay/cases/{index}"})
        manifest = root / "replay" / "manifest.json"
        manifest.write_text(json.dumps({"cases": entries}) + "\n", encoding="utf-8")
        return root

    def test_stitches_consecutive_real_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = self.make_source(base / "source")
            output = base / "output"
            result = module.stitch(source, output, [
                "operator/prefill/chunk_0/attention_core",
                "operator/prefill/chunk_1/attention_core",
            ])
            case_dir = output / "replay" / "cases" / result["case_id"]
            case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
            query = json.loads((case_dir / case["input_a"]).read_text(encoding="utf-8"))
            mask = json.loads((case_dir / case["mask"]).read_text(encoding="utf-8"))
            key = json.loads((case_dir / case["key"]).read_text(encoding="utf-8"))
            self.assertEqual(result["case_id"], "operator/prefill/p0_m4/attention_core")
            self.assertEqual(query["shape"], [2, 4, 2, 1])
            self.assertEqual(mask["shape"], [4, 4, 1, 1])
            self.assertEqual(key["shape"], [2, 4, 1, 1])
            mask_values = struct.unpack("<16H", (case_dir / case["mask"]).with_suffix(".bin").read_bytes())
            self.assertEqual(
                mask_values,
                (0, 0xFC00, 0xFC00, 0xFC00,
                 0, 0, 0xFC00, 0xFC00,
                 0, 0, 0, 0xFC00,
                 0, 0, 0, 0),
            )

    def test_rejects_changed_kv_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = self.make_source(base / "source", corrupt_prefix=True)
            with self.assertRaisesRegex(ValueError, "key cache prefix differs"):
                module.stitch(source, base / "output", [
                    "operator/prefill/chunk_0/attention_core",
                    "operator/prefill/chunk_1/attention_core",
                ])


if __name__ == "__main__":
    unittest.main()
