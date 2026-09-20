#!/usr/bin/env python3
"""Combine the small real-Qwen projection and attention FPGA records."""

import argparse
import csv
import json
from pathlib import Path


def one_row(path: Path):
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 1:
        raise ValueError(f"expected one record in {path}, found {len(rows)}")
    return rows[0]


def integer(row, key):
    try:
        return int(row[key], 0)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid integer {key!r} in record: {row}") from exc


def pass_projection(row):
    return row.get("result") == "PASS" and integer(row, "mismatches") == 0


def pass_attention(row):
    return row.get("result") == "PASS" and integer(row, "mismatches") == 0


def regular_row(mode, projection_mode, attention_mode, projection, attention):
    projection_cycles = integer(projection, "compute_cycles")
    attention_cycles = integer(attention, "cycles")
    return {
        "mode": mode,
        "projection_mode": projection_mode,
        "attention_mode": attention_mode,
        "projection_case": projection.get("case", ""),
        "attention_case": attention.get("case", ""),
        "projection_cycles": projection_cycles,
        "attention_cycles": attention_cycles,
        "total_cycles": projection_cycles + attention_cycles,
        "projection_quantize_cycles": integer(projection, "quantize_cycles"),
        "projection_pack_cycles": integer(projection, "pack_cycles"),
        "projection_matmul_cycles": integer(projection, "matmul_cycles"),
        "projection_logical_read_bytes": integer(
            projection, "logical_read_bytes"
        ),
        "attention_native_v2": attention.get("native_v2", ""),
        "projection_mismatches": integer(projection, "mismatches"),
        "attention_mismatches": integer(attention, "mismatches"),
        "qbs_status": "",
        "attention_status": "",
        "pass": pass_projection(projection) and pass_attention(attention),
    }


def combined_row(combined):
    return {
        "mode": "qbs_akv",
        "projection_mode": "qbs",
        "attention_mode": combined.get("attention_mode", "akv_v2"),
        "projection_case": combined.get("qbs_case", ""),
        "attention_case": combined.get("attention_case", ""),
        "projection_cycles": integer(combined, "qbs_cycles"),
        "attention_cycles": integer(combined, "combined_attention_cycles"),
        "total_cycles": integer(combined, "total_cycles"),
        "projection_quantize_cycles": integer(combined, "qbs_quantize_cycles"),
        "projection_pack_cycles": integer(combined, "qbs_pack_cycles"),
        "projection_matmul_cycles": integer(combined, "qbs_matmul_cycles"),
        "projection_logical_read_bytes": integer(
            combined, "qbs_logical_read_bytes"
        ),
        "attention_native_v2": combined.get("attention_native_v2", ""),
        "projection_mismatches": integer(combined, "qbs_mismatches"),
        "attention_mismatches": integer(combined, "attention_mismatches"),
        "qbs_status": combined.get("qbs_status", ""),
        "attention_status": combined.get("attention_status", ""),
        "pass": combined.get("pass", "False").lower() == "true",
    }


def finalize(rows):
    baseline = next(row for row in rows if row["mode"] == "rvv")
    baseline_cycles = baseline["total_cycles"]
    for row in rows:
        row["total_seconds_at_50mhz"] = row["total_cycles"] / 50_000_000
        row["speedup_vs_rvv"] = baseline_cycles / row["total_cycles"]
        row["pass"] = bool(row["pass"])
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--projection-rvv", required=True, type=Path)
    parser.add_argument("--projection-qbs", required=True, type=Path)
    parser.add_argument("--attention-rvv", required=True, type=Path)
    parser.add_argument("--attention-akv-v2", required=True, type=Path)
    parser.add_argument("--combined", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    args = parser.parse_args()

    projection_rvv = one_row(args.projection_rvv)
    projection_qbs = one_row(args.projection_qbs)
    attention_rvv = one_row(args.attention_rvv)
    attention_akv_v2 = one_row(args.attention_akv_v2)
    combined = one_row(args.combined)
    rows = finalize([
        regular_row("rvv", "rvv", "rvv", projection_rvv, attention_rvv),
        regular_row("qbs", "qbs", "rvv", projection_qbs, attention_rvv),
        regular_row("akv", "rvv", "akv_v2", projection_rvv, attention_akv_v2),
        combined_row(combined),
    ])

    fields = [
        "mode", "projection_mode", "attention_mode", "projection_case",
        "attention_case", "projection_cycles", "attention_cycles",
        "total_cycles", "total_seconds_at_50mhz", "speedup_vs_rvv",
        "projection_quantize_cycles", "projection_pack_cycles",
        "projection_matmul_cycles", "projection_logical_read_bytes",
        "attention_native_v2", "projection_mismatches",
        "attention_mismatches", "qbs_status", "attention_status", "pass",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(rows, indent=2) + "\n")

    if not all(row["pass"] for row in rows):
        raise SystemExit("one or more matrix records did not pass")
    print(f"parsed four-mode matrix -> {args.output}")


if __name__ == "__main__":
    main()
