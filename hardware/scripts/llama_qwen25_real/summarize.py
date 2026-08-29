#!/usr/bin/env python3
"""Merge one REAL_BENCH line with Ara's RTL performance report."""

from __future__ import annotations

import argparse
import csv
import re
import struct
from pathlib import Path


BENCH_RE = re.compile(r"\bREAL_BENCH\s+(.*)$")
PERF_RE = re.compile(r"^\[PERF\]\s+([^:]+?)\s*:\s*(\S+)")


def parse_key_values(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        match = BENCH_RE.search(line)
        if not match:
            continue
        for item in match.group(1).split():
            if "=" in item:
                key, value = item.split("=", 1)
                result[key] = value
    if not result:
        raise RuntimeError("run log contains no REAL_BENCH result")
    return result


def parse_perf(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        match = PERF_RE.match(line)
        if match:
            result[match.group(1).strip()] = match.group(2)
    return result


def float_from_bits(value: str) -> str:
    number = int(value, 16)
    decoded = struct.unpack("<f", struct.pack("<I", number))[0]
    return f"{decoded:.9g}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-log", type=Path, required=True)
    parser.add_argument("--perf-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    bench = parse_key_values(args.run_log.read_text(errors="replace"))
    perf = parse_perf(args.perf_log.read_text(errors="replace"))
    row = dict(bench)
    row["max_abs"] = float_from_bits(bench["max_abs_bits"])
    row["max_rel"] = float_from_bits(bench["max_rel_bits"])
    for key in (
        "total_cycles",
        "total_insns",
        "total_vector_insns",
        "ara_req_fire_count",
        "rvv_axi_ar_count",
        "rvv_axi_r_count",
        "rvv_op_load",
        "rvv_op_store",
        "lane utilization",
    ):
        row[key.replace(" ", "_")] = perf.get(key, "NA")

    fields = [
        "case", "result", "k", "rows", "inputs", "outputs",
        "tiles", "timing_scope", "setup_included", "timed_cycles",
        "timed_cycles_per_output_x1000", "descriptor_setup_cycles",
        "descriptor_setup_cycles_valid", "setup_cycles", "compute_cycles",
        "cycles_per_output_x1000",
        "quantize_cycles", "pack_cycles", "matmul_cycles",
        "logical_read_bytes", "total_cycles", "total_insns",
        "total_vector_insns", "ara_req_fire_count", "rvv_axi_ar_count",
        "rvv_axi_r_count", "rvv_op_load", "rvv_op_store",
        "lane_utilization", "checksum", "mismatches", "max_abs", "max_rel",
        "max_abs_bits", "max_rel_bits",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerow(row)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
