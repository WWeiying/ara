#!/usr/bin/env python3

"""Compare diagnostic F32 node dumps from two model variants.

The model runner emits raw IEEE-754 words for one selected graph node between
AKV_TOKEN_RUN_BEGIN/EXIT markers.  Parsing words rather than decimal text keeps
bit differences, signed zero, infinities, and NaNs distinguishable.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path


RUN_BEGIN_RE = re.compile(r"^AKV_TOKEN_RUN_BEGIN=([^\s]+)$")
RUN_EXIT_RE = re.compile(r"^AKV_TOKEN_RUN_EXIT=([^:]+):(-?\d+)$")
DUMP_BEGIN_RE = re.compile(
    r"^GGML_RISCV_MODEL_F32_BEGIN graph=(\d+) node=(\d+) "
    r"ne0=(\d+) ne1=(\d+) ne2=(\d+) ne3=(\d+)$"
)
DUMP_ROW_RE = re.compile(
    r"^GGML_RISCV_MODEL_F32 graph=(\d+) node=(\d+) row=(\d+) data=(.*)$"
)
DUMP_END_RE = re.compile(
    r"^GGML_RISCV_MODEL_F32_END graph=(\d+) node=(\d+) rows=(\d+)$"
)


@dataclass
class TensorDump:
    graph: int
    node: int
    shape: tuple[int, int, int, int]
    rows: dict[int, list[int]] = field(default_factory=dict)

    @property
    def row_count(self) -> int:
        return self.shape[1] * self.shape[2] * self.shape[3]

    def validate(self) -> None:
        if set(self.rows) != set(range(self.row_count)):
            missing = sorted(set(range(self.row_count)) - set(self.rows))
            extra = sorted(set(self.rows) - set(range(self.row_count)))
            raise ValueError(
                f"graph {self.graph} node {self.node} has incomplete rows: "
                f"missing={missing[:8]} extra={extra[:8]}"
            )
        bad = [index for index, row in self.rows.items() if len(row) != self.shape[0]]
        if bad:
            raise ValueError(
                f"graph {self.graph} node {self.node} rows have wrong width: {bad[:8]}"
            )


def bits_to_float(bits: int) -> float:
    return struct.unpack("<f", struct.pack("<I", bits))[0]


def json_float(value: float) -> float | str:
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "-inf" if value < 0.0 else "inf"
    return value


def ordered_float_bits(bits: int) -> int:
    # Map IEEE sign-magnitude ordering onto monotonically increasing integers.
    return (~bits & 0xFFFFFFFF) if bits & 0x80000000 else (bits | 0x80000000)


def parse_dumps(path: Path) -> dict[str, TensorDump]:
    dumps: dict[str, TensorDump] = {}
    current_run: str | None = None
    current_dump: TensorDump | None = None

    for line_number, raw_line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        line = raw_line.strip().replace("\r", "")
        match = RUN_BEGIN_RE.match(line)
        if match:
            if current_run is not None:
                raise ValueError(f"nested run marker at line {line_number}")
            current_run = match.group(1)
            current_dump = None
            continue

        match = RUN_EXIT_RE.match(line)
        if match:
            if current_run != match.group(1):
                raise ValueError(f"unmatched run exit at line {line_number}")
            if current_dump is not None:
                raise ValueError(f"unterminated F32 dump at line {line_number}")
            current_run = None
            continue

        if current_run is None:
            continue

        match = DUMP_BEGIN_RE.match(line)
        if match:
            if current_dump is not None:
                raise ValueError(f"nested F32 dump at line {line_number}")
            if current_run in dumps:
                raise ValueError(f"run {current_run} contains multiple selected F32 dumps")
            graph, node, *shape = (int(value) for value in match.groups())
            current_dump = TensorDump(graph, node, tuple(shape))
            continue

        match = DUMP_ROW_RE.match(line)
        if match:
            if current_dump is None:
                raise ValueError(f"F32 row outside dump at line {line_number}")
            graph, node, row_index = (int(value) for value in match.groups()[:3])
            if (graph, node) != (current_dump.graph, current_dump.node):
                raise ValueError(f"F32 row identity changed at line {line_number}")
            if row_index in current_dump.rows:
                raise ValueError(f"duplicate F32 row {row_index} at line {line_number}")
            words = match.group(4).split(",") if match.group(4) else []
            try:
                current_dump.rows[row_index] = [int(word, 16) for word in words]
            except ValueError as error:
                raise ValueError(f"invalid F32 word at line {line_number}") from error
            if any(word < 0 or word > 0xFFFFFFFF for word in current_dump.rows[row_index]):
                raise ValueError(f"out-of-range F32 word at line {line_number}")
            continue

        match = DUMP_END_RE.match(line)
        if match:
            if current_dump is None:
                raise ValueError(f"F32 end outside dump at line {line_number}")
            graph, node, rows = (int(value) for value in match.groups())
            if (graph, node) != (current_dump.graph, current_dump.node):
                raise ValueError(f"F32 end identity changed at line {line_number}")
            if rows != current_dump.row_count:
                raise ValueError(
                    f"F32 end row count {rows} differs from shape count "
                    f"{current_dump.row_count} at line {line_number}"
                )
            current_dump.validate()
            dumps[current_run] = current_dump
            current_dump = None

    if current_run is not None or current_dump is not None:
        raise ValueError("log ends inside a run or F32 dump")
    return dumps


def row_coordinates(row: int, shape: tuple[int, int, int, int]) -> dict[str, int]:
    _, ne1, ne2, _ = shape
    i1 = row % ne1
    quotient = row // ne1
    i2 = quotient % ne2
    i3 = quotient // ne2
    return {"i1": i1, "i2": i2, "i3": i3}


def compare(lhs: TensorDump, rhs: TensorDump, lhs_label: str, rhs_label: str) -> dict[str, object]:
    if (lhs.graph, lhs.node, lhs.shape) != (rhs.graph, rhs.node, rhs.shape):
        raise ValueError(
            "selected dumps differ in identity or shape: "
            f"{lhs_label}={(lhs.graph, lhs.node, lhs.shape)} "
            f"{rhs_label}={(rhs.graph, rhs.node, rhs.shape)}"
        )

    total = math.prod(lhs.shape)
    bit_mismatches = 0
    finite_mismatches = 0
    nonfinite_mismatches = 0
    signed_zero_mismatches = 0
    abs_sum = 0.0
    squared_sum = 0.0
    max_abs = 0.0
    max_abs_location: dict[str, object] | None = None
    max_ulp = 0
    first: dict[str, object] | None = None

    for row in range(lhs.row_count):
        for i0, (lhs_bits, rhs_bits) in enumerate(zip(lhs.rows[row], rhs.rows[row])):
            if lhs_bits == rhs_bits:
                continue
            bit_mismatches += 1
            lhs_value = bits_to_float(lhs_bits)
            rhs_value = bits_to_float(rhs_bits)
            location = {"row": row, "i0": i0, **row_coordinates(row, lhs.shape)}
            record = {
                **location,
                f"{lhs_label}_bits": f"{lhs_bits:08x}",
                f"{rhs_label}_bits": f"{rhs_bits:08x}",
                f"{lhs_label}_value": json_float(lhs_value),
                f"{rhs_label}_value": json_float(rhs_value),
            }
            if first is None:
                first = record

            if math.isfinite(lhs_value) and math.isfinite(rhs_value):
                finite_mismatches += 1
                difference = abs(lhs_value - rhs_value)
                abs_sum += difference
                squared_sum += difference * difference
                ulp = abs(ordered_float_bits(lhs_bits) - ordered_float_bits(rhs_bits))
                if difference > max_abs:
                    max_abs = difference
                    max_abs_location = {**record, "abs_error": difference, "ulp_error": ulp}
                max_ulp = max(max_ulp, ulp)
                if lhs_value == rhs_value:
                    signed_zero_mismatches += 1
            else:
                nonfinite_mismatches += 1

    return {
        "lhs": lhs_label,
        "rhs": rhs_label,
        "graph": lhs.graph,
        "node": lhs.node,
        "shape": list(lhs.shape),
        "elements": total,
        "bit_equal": bit_mismatches == 0,
        "bit_mismatches": bit_mismatches,
        "finite_mismatches": finite_mismatches,
        "nonfinite_mismatches": nonfinite_mismatches,
        "signed_zero_mismatches": signed_zero_mismatches,
        "mismatch_fraction": bit_mismatches / total if total else 0.0,
        "mean_abs_over_mismatches": abs_sum / finite_mismatches if finite_mismatches else 0.0,
        "rmse_over_mismatches": math.sqrt(squared_sum / finite_mismatches) if finite_mismatches else 0.0,
        "max_abs": max_abs,
        "max_ulp": max_ulp,
        "first_mismatch": first,
        "max_abs_location": max_abs_location,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--lhs", default="QBS_ONLY")
    parser.add_argument("--rhs", default="QBS_AKV_V2")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    dumps = parse_dumps(args.log)
    missing = [label for label in (args.lhs, args.rhs) if label not in dumps]
    if missing:
        raise ValueError(f"missing F32 dumps for variants: {', '.join(missing)}")
    result = compare(dumps[args.lhs], dumps[args.rhs], args.lhs, args.rhs)
    encoded = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output is not None:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
