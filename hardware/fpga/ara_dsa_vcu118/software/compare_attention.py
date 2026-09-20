#!/usr/bin/env python3
"""Compare measured FPGA attention cycles from mode result CSV files."""

import argparse
import csv
import json
from pathlib import Path


def read_row(path):
    with path.open(newline="") as stream:
        row = next(csv.DictReader(stream))
    if row.get("pass") != "True":
        raise SystemExit(f"benchmark is not PASS: {path}")
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rvv", required=True, type=Path)
    parser.add_argument("--akv", required=True, type=Path)
    parser.add_argument("--akv-v2", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    rows = {name: read_row(path) for name, path in
            (("rvv", args.rvv), ("akv", args.akv), ("akv_v2", args.akv_v2))}
    rvv_cycles = int(rows["rvv"]["cycles"])
    result = []
    for mode, row in rows.items():
        cycles = int(row["cycles"])
        result.append({
            "mode": mode,
            "case": row.get("case", ""),
            "result": row.get("result", ""),
            "cycles": cycles,
            "seconds_at_50mhz": cycles / 50_000_000,
            "relative_to_rvv": cycles / rvv_cycles,
            "speedup_over_rvv": rvv_cycles / cycles,
            "mismatches": int(row["mismatches"]),
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=result[0].keys())
        writer.writeheader()
        writer.writerows(result)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2) + "\n")
    print(f"wrote attention comparison -> {args.output}")


if __name__ == "__main__":
    main()
