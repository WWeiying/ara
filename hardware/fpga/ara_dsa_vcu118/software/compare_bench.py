#!/usr/bin/env python3
"""Compare the RVV and QBS CSV records produced by run_qwen_small.ps1."""

import argparse
import csv
import json
from pathlib import Path


MEASURES = (
    ("compute_cycles", "cycles"),
    ("quantize_cycles", "cycles"),
    ("pack_cycles", "cycles"),
    ("matmul_cycles", "cycles"),
    ("logical_read_bytes", "bytes"),
)


def read_one(path):
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 1:
        raise SystemExit(f"expected one benchmark row in {path}, got {len(rows)}")
    row = rows[0]
    if row.get("result") != "PASS" or row.get("mismatches") != "0":
        raise SystemExit(f"benchmark did not pass: {path}")
    return row


def number(row, key):
    value = row.get(key, "")
    if not value:
        raise SystemExit(f"missing {key} in benchmark CSV")
    return int(value, 0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rvv", required=True, type=Path)
    parser.add_argument("--qbs", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--clock-mhz", type=float, default=50.0)
    args = parser.parse_args()

    rvv = read_one(args.rvv)
    qbs = read_one(args.qbs)
    clock_hz = args.clock_mhz * 1_000_000.0
    rows = []
    for key, unit in MEASURES:
        rvv_value = number(rvv, key)
        qbs_value = number(qbs, key)
        rows.append({
            "metric": key,
            "unit": unit,
            "rvv": rvv_value,
            "qbs": qbs_value,
            "qbs_over_rvv": qbs_value / rvv_value if rvv_value else "",
            "speedup_rvv_over_qbs": rvv_value / qbs_value if qbs_value else "",
            "rvv_time_us": rvv_value * 1_000_000.0 / clock_hz,
            "qbs_time_us": qbs_value * 1_000_000.0 / clock_hz,
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "metric", "unit", "rvv", "qbs", "qbs_over_rvv",
        "speedup_rvv_over_qbs", "rvv_time_us", "qbs_time_us",
    ]
    with args.output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    report = {
        "clock_mhz": args.clock_mhz,
        "rvv": rvv,
        "qbs": qbs,
        "metrics": rows,
    }
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote comparison -> {args.output}")


if __name__ == "__main__":
    main()
