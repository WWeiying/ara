"""Audit a paired standard-RVV and QBS real-model VCS measurement."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

from check_real_dut_evidence import (QBS_M1_INSTRUCTION, archived_legacy_runner,
                                     fields, verify_manifest)


INPUT_FILES = ("source_weight.bin", "activation_f32.bin", "golden_f32.bin")
CASE_FIELDS = ("capture_root", "phase", "operator", "weight_type", "k",
               "rows", "inputs", "capture_rows", "capture_inputs")


def case_summary(case: dict[str, object]) -> dict[str, object]:
    return {key: case[key] for key in CASE_FIELDS if key in case}


def digest(path: Path) -> str:
    hash_value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hash_value.update(chunk)
    return hash_value.hexdigest()


def marker(path: Path, prefix: str) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", errors="replace") as stream:
        return [fields(line) for line in stream if line.startswith(prefix)]


def phase_gap(record: dict[str, str], name: str,
              issues: list[str]) -> int | None:
    try:
        total = int(record["compute_cycles"])
        stages = [int(record[key]) for key in
                  ("quantize_cycles", "pack_cycles", "matmul_cycles")]
    except (KeyError, ValueError):
        issues.append(f"{name} timed stage fields are invalid")
        return None
    if total <= 0 or any(stage < 0 for stage in stages) or sum(stages) > total:
        issues.append(f"{name} timed stages exceed or invalidate compute cycles")
        return None
    return total - sum(stages)


def image_components(manifest: Path) -> dict[str, str]:
    components: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            continue
        digest, name = match.groups()
        path = Path(name)
        if path.name in ("simv", "simulator.conf"):
            key = path.name
        elif ".daidir/" in name and path.suffix == ".so":
            key = f"simv.daidir/{path.name}"
        else:
            continue
        if key in components and components[key] != digest:
            raise ValueError(f"conflicting VCS image component: {key}")
        components[key] = digest
    return components


def custom_allocations(trace: Path) -> tuple[int, int]:
    qbs_m1 = custom2 = 0
    with trace.open(encoding="utf-8", errors="replace", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"event", "insn"}.issubset(reader.fieldnames or []):
            raise ValueError("vector trace has no event/insn columns")
        for row in reader:
            if row["event"] != "alloc":
                continue
            try:
                instruction = int(row["insn"], 16)
            except (TypeError, ValueError) as error:
                raise ValueError("vector allocation has an invalid instruction") from error
            qbs_m1 += instruction == int(QBS_M1_INSTRUCTION, 16)
            custom2 += (instruction & 0x7f) == 0x5b
    return qbs_m1, custom2


def audit_pair(qbs_run: Path, rvv_run: Path, qbs_app: Path,
               rvv_app: Path, archived_runner: Path | None = None) -> dict[str, object]:
    issues: list[str] = []
    qbs_case = json.loads((qbs_app / "case.json").read_text(encoding="utf-8"))
    rvv_case = json.loads((rvv_app / "case.json").read_text(encoding="utf-8"))
    for key in CASE_FIELDS:
        if qbs_case.get(key) != rvv_case.get(key):
            issues.append(f"case {key} differs")
    input_hashes: dict[str, str] = {}
    for name in INPUT_FILES:
        qbs_hash = digest(qbs_app / "generated" / name)
        rvv_hash = digest(rvv_app / "generated" / name)
        if qbs_hash != rvv_hash:
            issues.append(f"captured input {name} differs")
        input_hashes[name] = qbs_hash

    qbs_audit = json.loads((qbs_run / "qbs_evidence.json").read_text(
        encoding="utf-8"))
    qbs_uvm = json.loads((qbs_run / "uvm_result.json").read_text(
        encoding="utf-8"))
    rvv_uvm = json.loads((rvv_run / "uvm_result.json").read_text(
        encoding="utf-8"))
    if qbs_audit.get("status") != "PASS" or qbs_uvm.get("status") != "PASS":
        issues.append("QBS real-DUT evidence did not pass")
    for key, path in (
        ("case_sha256", qbs_app / "case.json"),
        ("elf_sha256", qbs_run / "work/input.elf"),
        ("log_sha256", qbs_run / "work/run.vcs.log"),
        ("trace_sha256", qbs_run / "work/vector_trace.csv"),
    ):
        if qbs_audit.get(key) != digest(path):
            issues.append(f"QBS evidence {key} does not match current file")
    for manifest, required in (
        ("INPUT_SHA256SUMS", {"work/input.elf"}),
        ("RUN_SHA256SUMS", {"work/run.vcs.log", "work/vector_trace.csv",
                            "uvm_result.json", "INPUT_SHA256SUMS"}),
    ):
        issues.extend(verify_manifest(qbs_run / manifest, qbs_run, required,
                                      archived_legacy_runner(archived_runner)))
    if rvv_uvm.get("status") != "PASS" or rvv_uvm.get("issues"):
        issues.append("standard-RVV real-DUT UVM audit did not pass")
    if qbs_uvm.get("simv_sha256") != rvv_uvm.get("simv_sha256"):
        issues.append("RVV and QBS used different VCS images")
    try:
        qbs_image = image_components(qbs_run / "INPUT_SHA256SUMS")
        rvv_image = image_components(rvv_run / "INPUT_SHA256SUMS")
        if ("simv" not in qbs_image or "simulator.conf" not in qbs_image or
                not any(key.startswith("simv.daidir/") for key in qbs_image) or
                qbs_image != rvv_image or
                qbs_image["simv"] != qbs_uvm.get("simv_sha256")):
            issues.append("RVV/QBS VCS executable, configuration, or libraries differ")
    except (OSError, ValueError) as error:
        qbs_image = rvv_image = {}
        issues.append(f"cannot verify paired VCS image: {error}")

    rvv_log = rvv_run / "work/run.vcs.log"
    rvv_trace = rvv_run / "work/vector_trace.csv"
    rvv_records = marker(rvv_log, "REAL_BENCH ")
    if len(rvv_records) != 1:
        issues.append(f"expected one RVV benchmark record, found {len(rvv_records)}")
    rvv = rvv_records[0] if len(rvv_records) == 1 else {}
    qbs = qbs_audit.get("benchmark", {})
    phase_gaps: dict[str, int | None] = {}
    for name, record, case in (("RVV", rvv, rvv_case),
                               ("QBS", qbs, qbs_case)):
        for key, expected in (("case", case["case_id"]),
                              ("result", "PASS"), ("mismatches", "0"),
                              ("k", str(case["k"])),
                              ("rows", str(case["rows"])),
                              ("inputs", str(case["inputs"])),
                              ("outputs", str(case["rows"] * case["inputs"]))):
            if record.get(key) != expected:
                issues.append(f"{name} {key}: expected {expected}, got {record.get(key)}")
        phase_gaps[name.lower()] = phase_gap(record, name, issues)
        if not re.fullmatch(r"0x[0-9a-f]+", record.get("checksum", "")):
            issues.append(f"{name} output checksum is missing or malformed")
    for key, expected in (("timing_scope", "production_command"),
                          ("setup_included", "1"), ("operations", "1"),
                          ("quantizations", "1"), ("cross_op_reuse", "0"),
                          ("activation_context", "0")):
        if qbs.get(key) != expected:
            issues.append(f"QBS {key}: expected {expected}, got {qbs.get(key)}")
    if qbs.get("timed_cycles") != qbs.get("compute_cycles"):
        issues.append("QBS timed and compute cycles disagree")
    if rvv.get("setup_cycles") != "0":
        issues.append("RVV setup was not excluded as expected")

    try:
        qbs_instruction_events, custom2_events = custom_allocations(rvv_trace)
    except (OSError, ValueError) as error:
        qbs_instruction_events = custom2_events = 0
        issues.append(f"cannot audit standard-RVV custom allocations: {error}")
    if custom2_events:
        issues.append("standard-RVV trace contains QBS/AKV custom-2 allocations")

    for manifest, required in (
        ("INPUT_SHA256SUMS", {"work/input.elf"}),
        ("RUN_SHA256SUMS", {"work/run.vcs.log", "work/vector_trace.csv",
                            "uvm_result.json", "INPUT_SHA256SUMS"}),
    ):
        issues.extend(verify_manifest(rvv_run / manifest, rvv_run, required,
                                      archived_legacy_runner(archived_runner)))
    for name, path in (("elf_sha256", rvv_run / "work/input.elf"),
                       ("log_sha256", rvv_log),
                       ("vector_trace_sha256", rvv_trace)):
        if rvv_uvm.get(name) != digest(path):
            issues.append(f"RVV UVM {name} does not match current file")

    try:
        rvv_cycles = int(rvv["compute_cycles"])
        qbs_cycles = int(qbs["compute_cycles"])
        if rvv_cycles <= 0 or qbs_cycles <= 0:
            raise ValueError("nonpositive cycle count")
    except (KeyError, ValueError):
        rvv_cycles = qbs_cycles = 0
        issues.append("paired compute cycle count is invalid")

    return {
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "scope": "same captured Qwen2.5 slice and VCS image; each app checks llama.cpp golden",
        "case": case_summary(qbs_case),
        "input_sha256": input_hashes,
        "simv_sha256": qbs_uvm.get("simv_sha256"),
        "vcs_image_components": qbs_image,
        "qbs_audit_sha256": digest(qbs_run / "qbs_evidence.json"),
        "rvv_elf_sha256": digest(rvv_run / "work/input.elf"),
        "qbs_elf_sha256": digest(qbs_run / "work/input.elf"),
        "rvv_compute_cycles": rvv_cycles,
        "qbs_compute_cycles": qbs_cycles,
        "rvv_output_checksum": rvv.get("checksum"),
        "qbs_output_checksum": qbs.get("checksum"),
        "bitwise_equal_output_checksum": rvv.get("checksum") == qbs.get("checksum"),
        "rvv_phase_gap_cycles": phase_gaps["rvv"],
        "qbs_phase_gap_cycles": phase_gaps["qbs"],
        "rvv_over_qbs_speedup": (rvv_cycles / qbs_cycles
                                 if rvv_cycles and qbs_cycles else None),
        "rvv_qbs_command_allocations": qbs_instruction_events,
        "rvv_custom2_command_allocations": custom2_events,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qbs-run", type=Path, required=True)
    parser.add_argument("--rvv-run", type=Path, required=True)
    parser.add_argument("--qbs-app", type=Path, required=True)
    parser.add_argument("--rvv-app", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit_pair(args.qbs_run.resolve(), args.rvv_run.resolve(),
                        args.qbs_app.resolve(), args.rvv_app.resolve())
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"RVV/QBS paired real-DUT evidence: {result['status']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
