#!/usr/bin/env python3
"""Parse one combined real-Qwen QBS+AKV UART replay."""

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
    qbs = None
    attention = None
    dispatch = {}
    combined = None
    for raw in log.splitlines():
        line = raw.strip()
        if line.startswith("QBS_REAL_BENCH "):
            qbs = fields(line.split(None, 1)[1])
        elif line.startswith("ATTENTION_DISPATCH "):
            dispatch = fields(line.split(None, 1)[1])
        elif line.startswith("LLAMA_OPERATOR "):
            words = line.split()
            if len(words) < 4:
                raise ValueError(f"malformed LLAMA_OPERATOR line: {line}")
            attention = {"case": words[1], "result": words[2]}
            attention.update(fields(" ".join(words[3:])))
        elif line.startswith("QBS_AKV_COMBINED "):
            combined = fields(line.split(None, 1)[1])

    if qbs is None or attention is None or combined is None:
        raise ValueError("missing QBS, attention, or combined record")
    required = {
        "qbs": (qbs, ("case", "result", "compute_cycles", "mismatches",
                       "quantize_cycles", "pack_cycles", "matmul_cycles",
                       "logical_read_bytes")),
        "attention": (attention, ("case", "result", "cycles", "mismatches")),
        "combined": (combined, ("result", "qbs_cycles", "attention_cycles",
                                  "total_cycles", "qbs_status",
                                  "attention_status")),
    }
    for name, (record, keys) in required.items():
        missing = [key for key in keys if key not in record]
        if missing:
            raise ValueError(f"{name} record missing: {', '.join(missing)}")

    numeric_qbs = ("compute_cycles", "mismatches", "quantize_cycles",
                   "pack_cycles", "matmul_cycles", "logical_read_bytes")
    numeric_attention = ("cycles", "mismatches")
    numeric_combined = ("qbs_cycles", "attention_cycles", "total_cycles",
                        "qbs_status", "attention_status")
    for key in numeric_qbs:
        qbs[key] = int(qbs[key], 0)
    for key in numeric_attention:
        attention[key] = int(attention[key], 0)
    for key in numeric_combined:
        combined[key] = int(combined[key], 0)

    row = {
        "record": "QBS_AKV_COMBINED",
        "qbs_case": qbs["case"],
        "qbs_result": qbs["result"],
        "qbs_compute_cycles": qbs["compute_cycles"],
        "qbs_quantize_cycles": qbs["quantize_cycles"],
        "qbs_pack_cycles": qbs["pack_cycles"],
        "qbs_matmul_cycles": qbs["matmul_cycles"],
        "qbs_logical_read_bytes": qbs["logical_read_bytes"],
        "qbs_mismatches": qbs["mismatches"],
        "attention_case": attention["case"],
        "attention_result": attention["result"],
        "attention_cycles": attention["cycles"],
        "attention_mismatches": attention["mismatches"],
        "attention_native_v2": dispatch.get("native_v2", ""),
        "attention_portable": dispatch.get("portable", ""),
        "qbs_cycles": combined["qbs_cycles"],
        "combined_attention_cycles": combined["attention_cycles"],
        "total_cycles": combined["total_cycles"],
        "qbs_status": combined["qbs_status"],
        "attention_status": combined["attention_status"],
        "attention_mode": combined.get("attention_mode", ""),
    }
    row["total_seconds_at_50mhz"] = row["total_cycles"] / 50_000_000
    row["pass"] = (
        qbs["result"] == "PASS" and qbs["mismatches"] == 0 and
        attention["result"] == "PASS" and attention["mismatches"] == 0 and
        dispatch.get("native_v2") == "1" and
        combined.get("attention_mode") == "akv_v2" and
        combined["result"] == "PASS" and combined["qbs_status"] == 0 and
        combined["attention_status"] == 0 and
        combined["qbs_cycles"] == qbs["compute_cycles"] and
        combined["attention_cycles"] == attention["cycles"] and
        combined["total_cycles"] ==
        combined["qbs_cycles"] + combined["attention_cycles"]
    )
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    row = parse(args.log.read_text(errors="replace"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row),
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerow(row)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(row, indent=2) + "\n")
    print(f"parsed combined result -> {args.output}")
    if not row["pass"]:
        raise SystemExit("combined result is not a consistent PASS")


if __name__ == "__main__":
    main()
