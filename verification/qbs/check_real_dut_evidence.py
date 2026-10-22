"""Cross-check a captured QBS benchmark, vector trace, and real-DUT UVM audit."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path


QBS_M1_INSTRUCTION = "00b5045b"
QBS_INSTRUCTION_BY_INPUTS = {
    1: QBS_M1_INSTRUCTION,
    2: "02b5045b",
    3: "04b5045b",
    4: "06b5045b",
    8: "0eb5045b",
}


def fields(line: str) -> dict[str, str]:
    return dict(re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)=([^\s]+)", line))


def audit_records(case: dict[str, object], log_lines: list[str],
                  trace_lines: list[str], uvm: dict[str, object]) -> dict[str, object]:
    issues: list[str] = []
    records = [fields(line) for line in log_lines
               if line.startswith("QBS_REAL_BENCH ")]
    if len(records) != 1:
        issues.append(f"expected one QBS_REAL_BENCH record, found {len(records)}")
    bench = records[0] if len(records) == 1 else {}
    expected = {
        "case": str(case["case_id"]),
        "k": str(case["k"]),
        "rows": str(case["rows"]),
        "inputs": str(case["inputs"]),
        "result": "PASS",
        "mismatches": "0",
        "qbs_status": "0",
    }
    for key, value in expected.items():
        if bench.get(key) != value:
            issues.append(f"QBS {key}: expected {value}, got {bench.get(key)}")
    try:
        outputs = int(bench["outputs"])
        result_count = int(bench["result_count"])
        tiles = int(bench["tiles"])
        operations = int(bench["operations"])
    except (KeyError, ValueError):
        outputs = result_count = tiles = operations = 0
        issues.append("QBS output, tile, or operation count is missing")
    if outputs != int(case["rows"]) * int(case["inputs"]):
        issues.append("QBS output count does not match case dimensions")
    if result_count != outputs * operations or tiles < 1 or operations < 1:
        issues.append("QBS result or command count is inconsistent")
    if uvm.get("status") != "PASS" or uvm.get("issues"):
        issues.append("real-DUT UVM audit did not pass")

    instruction = QBS_INSTRUCTION_BY_INPUTS.get(int(case["inputs"]))
    if instruction is None:
        issues.append("unsupported QBS input count for instruction audit")
    allocated: list[str] = []
    completed: list[str] = []
    written: set[str] = set()
    for row in csv.reader(trace_lines):
        if len(row) < 7 or row[6].lower() != instruction:
            continue
        if row[1] == "alloc":
            allocated.append(row[2])
        elif row[1] == "done":
            completed.append(row[2])
        elif row[1] == "write":
            written.add(row[2])
    if (len(allocated) != tiles * operations or
            len(set(allocated)) != len(allocated) or
            sorted(allocated) != sorted(completed) or
            not set(allocated).issubset(written)):
        issues.append("QBS alloc/write/done events do not match benchmark tiles")

    return {
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "case": expected["case"],
        "benchmark": bench,
        "qbs_commands": len(allocated),
        "qbs_completed": len(completed),
        "uvm_status": uvm.get("status"),
    }


def verify_manifest(path: Path, root: Path,
                    required: set[str],
                    archived_sources: dict[str, Path | list[Path]] | None = None) -> list[str]:
    issues: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        return [f"cannot read {path}: {error}"]
    if not lines:
        return [f"empty manifest: {path}"]
    listed: set[str] = set()
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            issues.append(f"invalid SHA-256 manifest line in {path}")
            continue
        listed.add(match[2])
        target = Path(match[2])
        if not target.is_absolute():
            target = root / target
        candidates = [target]
        if archived_sources and match[2] in archived_sources:
            archived = archived_sources[match[2]]
            candidates.extend(archived if isinstance(archived, list) else [archived])
        errors: list[str] = []
        for candidate in candidates:
            try:
                digest = hashlib.sha256()
                with candidate.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() == match[1]:
                    break
                errors.append(f"SHA-256 mismatch: {candidate}")
            except OSError as error:
                errors.append(f"cannot hash {candidate}: {error}")
        else:
            issues.extend(errors)
    for name in sorted(required - listed):
        issues.append(f"missing SHA-256 manifest entry: {name}")
    return issues


def archived_legacy_runner(extra: Path | None = None) -> dict[str, Path | list[Path]]:
    uvm_dir = Path(__file__).resolve().parent.parent / "uvm"
    current = uvm_dir / "run_real_dut_case.sh"
    legacy = uvm_dir / "run_real_dut_case_legacy_20260923.sh"
    return {str(current): [legacy, extra] if extra is not None else legacy}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--case-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.run.resolve()
    case = json.loads(args.case_json.read_text(encoding="utf-8"))
    uvm = json.loads((root / "uvm_result.json").read_text(encoding="utf-8"))
    log_path = root / "work/run.vcs.log"
    trace_path = root / "work/vector_trace.csv"
    with log_path.open(encoding="utf-8", errors="replace") as stream:
        log_lines = [line.strip() for line in stream
                     if line.startswith("QBS_REAL_BENCH ")]
    with trace_path.open(encoding="utf-8", errors="replace") as stream:
        result = audit_records(case, log_lines, stream, uvm)
    result["case_sha256"] = hashlib.sha256(
        args.case_json.read_bytes()).hexdigest()
    result["case_spec"] = {
        key: case[key] for key in ("case_id", "weight_type", "k", "rows", "inputs")
    }
    result["log_sha256"] = hashlib.sha256(log_path.read_bytes()).hexdigest()
    result["trace_sha256"] = hashlib.sha256(trace_path.read_bytes()).hexdigest()
    result["elf_sha256"] = hashlib.sha256(
        (root / "work/input.elf").read_bytes()).hexdigest()
    for name, actual in (("elf_sha256", result["elf_sha256"]),
                         ("log_sha256", result["log_sha256"]),
                         ("vector_trace_sha256", result["trace_sha256"])):
        if uvm.get(name) != actual:
            result["issues"].append(f"UVM {name} does not match current file")
    result["issues"].extend(verify_manifest(
        root / "INPUT_SHA256SUMS", root, {"work/input.elf"},
        archived_legacy_runner()))
    result["issues"].extend(verify_manifest(
        root / "RUN_SHA256SUMS", root,
        {"work/run.vcs.log", "work/vector_trace.csv", "uvm_result.json",
         "INPUT_SHA256SUMS"}))
    if result["issues"]:
        result["status"] = "FAIL"
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"QBS real-DUT evidence: {result['status']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
