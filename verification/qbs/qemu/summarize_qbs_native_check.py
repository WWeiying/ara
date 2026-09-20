#!/usr/bin/env python3
"""Convert a QBS llama.cpp QEMU log into machine-readable reports."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


KEY_VALUE = re.compile(r"([A-Za-z0-9_]+)=([^\s]+)")


def value(token: str):
    lowered = token.lower()
    if lowered in {"nan", "+nan", "-nan", "inf", "+inf", "-inf"}:
        return None
    try:
        if re.fullmatch(r"[-+]?\d+", token):
            return int(token, 10)
        return float(token)
    except ValueError:
        return token


def fields(text: str) -> dict[str, object]:
    return {key: value(raw) for key, raw in KEY_VALUE.findall(text)}


def parse_log(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8", errors="replace")
    exits = {
        label: int(code)
        for label, code in re.findall(r"^QBS_TOKEN_RUN_EXIT=([^:]+):(-?\d+)$", text, re.M)
    }
    executions = [
        fields(payload)
        for payload in re.findall(r"^GGML_RISCV_QBS_EXEC (.+)$", text, re.M)
    ]
    metrics_match = re.search(r"^QBS_MODEL_METRICS (.+)$", text, re.M)
    metrics = fields(metrics_match.group(1)) if metrics_match else {}
    records_match = re.search(
        r"^QBS_LOGITS_RECORDS=(\d+) status=([^\s]+)$", text, re.M
    )
    equal_match = re.search(r"^QBS_TOKEN_OUTPUT_EQUAL=([^\s]+)$", text, re.M)
    guest_match = re.search(r"^LLAMA_GUEST_EXIT=(-?\d+)$", text, re.M)

    native_qbexec = sum(int(row.get("native_qbexec", 0)) for row in executions)
    native_gemv = sum(int(row.get("gemv_calls", 0)) for row in executions)
    native_gemm = sum(int(row.get("gemm_calls", 0)) for row in executions)
    qbs_exit = exits.get("QBS_NATIVE")
    rvv_exit = exits.get("RVV")
    guest_exit = int(guest_match.group(1)) if guest_match else None
    output_equal = equal_match.group(1) if equal_match else None
    logits_records = int(records_match.group(1)) if records_match else None
    logits_status = records_match.group(2) if records_match else None
    passed = (
        rvv_exit == 0
        and qbs_exit == 0
        and guest_exit == 0
        and output_equal == "1"
        and native_qbexec > 0
        and (logits_status in {None, "OK"})
    )

    summary = {
        "log": str(path),
        "rvv_exit": rvv_exit,
        "qbs_native_exit": qbs_exit,
        "guest_exit": guest_exit,
        "output_equal": output_equal,
        "logits_records": logits_records,
        "logits_status": logits_status,
        "metrics_records": metrics.get("records"),
        "mean_kl": metrics.get("mean_kl"),
        "top1_agreement": metrics.get("top1_agreement"),
        "top5_overlap": metrics.get("top5_overlap"),
        "mean_rmse": metrics.get("mean_rmse"),
        "max_abs": metrics.get("max_abs"),
        "native_types": ",".join(
            str(row.get("type", "")) for row in executions
        ),
        "native_qbexec_total": native_qbexec,
        "native_gemv_calls": native_gemv,
        "native_gemm_calls": native_gemm,
        "pass": passed,
    }
    return {"summary": summary, "metrics": metrics, "executions": executions}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--require-pass", action="store_true")
    args = parser.parse_args()

    report = parse_log(args.log)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=report["summary"].keys())
        writer.writeheader()
        writer.writerow(report["summary"])
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"parsed QBS QEMU report -> {args.output}")
    if args.require_pass and not report["summary"]["pass"]:
        raise SystemExit("QBS QEMU acceptance markers are incomplete")


if __name__ == "__main__":
    main()
