"""Audit a real-model QBS plus AKV-v2 DUT run from its original VCS log."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def fields(line: str) -> dict[str, str]:
    return dict(re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)=([^\s]+)", line))


def audit(lines: list[str]) -> dict[str, object]:
    errors: list[str] = []

    def unique(prefix: str) -> str:
        matches = [line for line in lines if line.startswith(prefix)]
        if len(matches) != 1:
            errors.append(f"expected one {prefix} record, found {len(matches)}")
            return ""
        return matches[0]

    qbs = fields(unique("QBS_REAL_BENCH "))
    attention = unique("LLAMA_OPERATOR ")
    dispatch = fields(unique("ATTENTION_DISPATCH "))
    combined = fields(unique("QBS_AKV_COMBINED "))
    akv_perf = [fields(line) for line in lines if line.startswith("[AKV_PERF] ")]
    qbs_perf = [fields(line) for line in lines if line.startswith("[QBS_PERF] ")]

    for name, actual, expected in (
        ("QBS result", qbs.get("result"), "PASS"),
        ("QBS mismatches", qbs.get("mismatches"), "0"),
        ("QBS status", qbs.get("qbs_status"), "0"),
        ("AKV dispatch", dispatch.get("native_v2"), "1"),
        ("combined result", combined.get("result"), "PASS"),
        ("combined QBS status", combined.get("qbs_status"), "0"),
        ("combined attention status", combined.get("attention_status"), "0"),
        ("combined mode", combined.get("attention_mode"), "akv_v2"),
    ):
        if actual != expected:
            errors.append(f"{name}: expected {expected}, got {actual}")
    if not re.fullmatch(r"LLAMA_OPERATOR \S+ PASS cycles=[0-9]+ mismatches=0", attention):
        errors.append("attention golden comparison did not pass")
    if not qbs_perf or any(record.get("success") != "1" or record.get("fault") != "0"
                           for record in qbs_perf):
        errors.append("successful QBS RTL activity is missing")
    if not akv_perf or any(record.get("success") != "1" or record.get("fault") != "0"
                           for record in akv_perf):
        errors.append("successful AKV RTL activity is missing")
    sequences = [record.get("seq") for record in akv_perf]
    if sequences != [str(index) for index in range(1, len(akv_perf) + 1)]:
        errors.append("AKV command sequence is incomplete or duplicated")
    for name in ("v2_full", "v2_column_load"):
        values = [record.get(name) for record in akv_perf]
        if any(value is None or not value.isdigit() for value in values) or \
                sum(int(value) for value in values) < 1:
            errors.append(f"AKV RTL activity {name} is missing")
    return {"status": "PASS" if not errors else "FAIL", "issues": errors,
            "qbs": qbs, "qbs_command_count": len(qbs_perf),
            "attention": attention, "dispatch": dispatch,
            "akv_command_count": len(akv_perf), "akv_commands": akv_perf,
            "combined": combined}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.log.open(encoding="utf-8", errors="replace") as stream:
        result = audit([line.strip() for line in stream
                        if line.startswith(("QBS_REAL_BENCH ", "LLAMA_OPERATOR ",
                                            "ATTENTION_DISPATCH ", "QBS_AKV_COMBINED ",
                                            "[AKV_PERF] ", "[QBS_PERF] "))])
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"QBS+AKV real-DUT evidence: {result['status']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
