#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import struct
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("compare-model-f32-dumps.py")
SPEC = importlib.util.spec_from_file_location("compare_model_f32_dumps", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def word(value: float) -> str:
    return f"{struct.unpack('<I', struct.pack('<f', value))[0]:08x}"


def run(label: str, rows: list[list[str]]) -> list[str]:
    lines = [
        f"AKV_TOKEN_RUN_BEGIN={label}",
        "GGML_RISCV_MODEL_F32_BEGIN graph=0 node=25 ne0=2 ne1=2 ne2=1 ne3=1",
    ]
    lines.extend(
        f"GGML_RISCV_MODEL_F32 graph=0 node=25 row={index} data={','.join(values)}"
        for index, values in enumerate(rows)
    )
    lines.extend(
        (
            "GGML_RISCV_MODEL_F32_END graph=0 node=25 rows=2",
            f"AKV_TOKEN_RUN_EXIT={label}:0",
        )
    )
    return lines


class CompareModelF32DumpsTest(unittest.TestCase):
    def test_reports_exact_location_and_error(self) -> None:
        lhs_rows = [[word(1.0), word(2.0)], [word(3.0), word(4.0)]]
        rhs_rows = [[word(1.0), word(2.0)], [word(3.5), word(4.0)]]
        lines = run("QBS_ONLY", lhs_rows) + run("QBS_AKV_V2", rhs_rows)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qemu.log"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            dumps = MODULE.parse_dumps(path)
        result = MODULE.compare(
            dumps["QBS_ONLY"], dumps["QBS_AKV_V2"], "QBS_ONLY", "QBS_AKV_V2"
        )
        self.assertEqual(result["bit_mismatches"], 1)
        self.assertEqual(result["finite_mismatches"], 1)
        self.assertEqual(result["first_mismatch"]["row"], 1)
        self.assertEqual(result["first_mismatch"]["i0"], 0)
        self.assertEqual(result["first_mismatch"]["i1"], 1)
        self.assertEqual(result["max_abs"], 0.5)

    def test_rejects_missing_rows(self) -> None:
        lines = run("QBS_ONLY", [[word(1.0), word(2.0)]])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qemu.log"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "row count|incomplete rows"):
                MODULE.parse_dumps(path)

    def test_nonfinite_values_remain_reportable(self) -> None:
        lhs = MODULE.TensorDump(0, 25, (1, 1, 1, 1), {0: [0x7FC00000]})
        rhs = MODULE.TensorDump(0, 25, (1, 1, 1, 1), {0: [0x3F800000]})
        result = MODULE.compare(lhs, rhs, "L", "R")
        self.assertEqual(result["nonfinite_mismatches"], 1)
        self.assertEqual(result["first_mismatch"]["L_value"], "nan")
        self.assertEqual(result["first_mismatch"]["R_value"], 1.0)
        # The command-line JSON path uses allow_nan=False.
        __import__("json").dumps(result, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
