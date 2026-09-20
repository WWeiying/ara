#!/usr/bin/env python3
"""Convert one FPGA UART benchmark log into machine-readable CSV and JSON."""

import argparse
import csv
import json
from pathlib import Path


def parse_record(line):
    parts = line.strip().split(None, 1)
    if len(parts) != 2 or parts[0] not in {"REAL_BENCH", "QBS_REAL_BENCH"}:
        return None
    row = {"record": parts[0]}
    for item in parts[1].split():
        if "=" in item:
            key, value = item.split("=", 1)
            row[key] = value
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=("rvv", "qbs"))
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    rows = []
    for line in args.log.read_text(errors="replace").splitlines():
        row = parse_record(line)
        if row is not None:
            row["mode"] = args.mode
            rows.append(row)
    if not rows:
        raise SystemExit(f"no REAL_BENCH record found in {args.log}")

    fields = ["mode", "record"]
    fields += sorted({key for row in rows for key in row if key not in fields})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(rows, indent=2) + "\n")

    print(f"parsed {len(rows)} benchmark record(s) -> {args.output}")


if __name__ == "__main__":
    main()
