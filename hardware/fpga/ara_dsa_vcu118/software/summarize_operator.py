#!/usr/bin/env python3
"""Convert one LLAMA_OPERATOR UART log into CSV and JSON."""

import argparse
import csv
import json
from pathlib import Path


def fields(text):
    result = {}
    for item in text.split():
        if "=" in item:
            key, value = item.split("=", 1)
            result[key] = value
    return result


def parse(log):
    row = {"record": "LLAMA_OPERATOR"}
    for line in log.splitlines():
        line = line.strip()
        if line.startswith("ATTENTION_DISPATCH "):
            row.update(fields(line.split(None, 1)[1]))
        elif line.startswith("LLAMA_OPERATOR "):
            words = line.split()
            if len(words) < 4:
                raise ValueError(f"malformed LLAMA_OPERATOR line: {line}")
            row.update({"case": words[1], "result": words[2]})
            row.update(fields(" ".join(words[3:])))
    if "case" not in row:
        raise ValueError("no LLAMA_OPERATOR record found")
    for key in ("cycles", "mismatches"):
        if key not in row:
            raise ValueError(f"LLAMA_OPERATOR record has no {key}")
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--mode", required=True,
                        choices=("rvv", "akv", "akv_v2"))
    args = parser.parse_args()

    row = parse(args.log.read_text(errors="replace"))
    row["mode"] = args.mode
    row["cycles"] = int(row["cycles"])
    row["mismatches"] = int(row["mismatches"])
    row["pass"] = row.get("result") == "PASS" and row["mismatches"] == 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["mode", "record", "case", "result", "pass", "cycles",
                  "mismatches", "native_v2", "portable"]
    with args.output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames,
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerow(row)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(row, indent=2) + "\n")
    print(f"parsed operator result -> {args.output}")
    if not row["pass"]:
        raise SystemExit("operator result is not PASS with zero mismatches")


if __name__ == "__main__":
    main()
