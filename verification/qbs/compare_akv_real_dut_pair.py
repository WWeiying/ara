"""Audit one captured Attention core on standard RVV and AKV-v2 real DUT."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

from check_real_dut_evidence import archived_legacy_runner, verify_manifest
from compare_real_dut_pair import image_components


OPERATOR = re.compile(
    r"LLAMA_OPERATOR (\S+) (PASS|FAIL) cycles=(\d+) mismatches=(\d+)\s*$")
INCBIN = re.compile(r'\.incbin "([^"]+)"')


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def assembly_inputs(path: Path) -> tuple[list[int], list[Path]]:
    config: list[int] = []
    sources: list[Path] = []
    in_config = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "llama_case_config:":
            in_config = True
        elif in_config and stripped.startswith(".balign"):
            in_config = False
        elif in_config and stripped.startswith(".long "):
            config.append(int(stripped.split()[1], 0))
        match = INCBIN.fullmatch(stripped)
        if match:
            sources.append(Path(match.group(1)))
    return config, sources


def operator_record(log: Path, implementation: str,
                    issues: list[str]) -> int | None:
    records = []
    dispatch = []
    with log.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            match = OPERATOR.fullmatch(line.strip())
            if match:
                records.append(match.groups())
            if line.startswith("ATTENTION_DISPATCH "):
                dispatch.append(line.strip())
    expected_name = f"operator/decode/attention_core/{implementation}"
    if len(records) != 1 or records[0][:2] != (expected_name, "PASS") or \
            records[0][3] != "0":
        issues.append(f"{implementation}: operator golden self-check missing or failed")
        return None
    if implementation == "akv_v2":
        if dispatch != ["ATTENTION_DISPATCH native_v2=1 portable=0"]:
            issues.append("AKV-v2 native dispatch was not observed exactly once")
    elif dispatch:
        issues.append("standard RVV unexpectedly reported AKV dispatch")
    cycles = int(records[0][2])
    if cycles <= 0:
        issues.append(f"{implementation}: invalid Attention cycle count")
        return None
    return cycles


def custom_allocations(trace: Path) -> dict[str, int]:
    counts = {"fill_v2": 0, "column_v2": 0, "value_load": 0,
              "release": 0, "other_custom2": 0}
    with trace.open(encoding="utf-8", errors="replace") as stream:
        for row in csv.reader(stream):
            if len(row) < 7 or row[1] != "alloc":
                continue
            instruction = int(row[6], 16)
            if instruction & 0x7f != 0x5b:
                continue
            funct3 = (instruction >> 12) & 0x7
            key = {3: "value_load", 5: "release", 6: "fill_v2",
                   7: "column_v2"}.get(funct3, "other_custom2")
            counts[key] += 1
    return counts


def audit_pair(rvv_run: Path, akv_run: Path, rvv_elf: Path, akv_elf: Path,
               rvv_asm: Path, akv_asm: Path,
               archived_runner: Path | None = None) -> dict[str, object]:
    issues: list[str] = []
    rvv_cfg, rvv_sources = assembly_inputs(rvv_asm)
    akv_cfg, akv_sources = assembly_inputs(akv_asm)
    if (len(rvv_cfg) < 5 or len(akv_cfg) < 5 or
            rvv_cfg[2:4] != [7, 1] or akv_cfg[2:4] != [7, 8] or
            rvv_cfg[:3] != akv_cfg[:3] or rvv_cfg[4:] != akv_cfg[4:]):
        issues.append("Attention configurations differ beyond RVV/AKV mode")
    if len(rvv_sources) != 5 or rvv_sources != akv_sources:
        issues.append("captured Attention input paths differ")
    source_hashes: dict[str, str] = {}
    rvv_image = rvv_elf.read_bytes()
    akv_image = akv_elf.read_bytes()
    for source in rvv_sources:
        data = source.read_bytes()
        source_hashes[str(source)] = hashlib.sha256(data).hexdigest()
        if not data or data not in rvv_image or data not in akv_image:
            issues.append(f"captured tensor is missing from an ELF: {source}")

    runs = {"rvv": rvv_run, "akv_v2": akv_run}
    audits = {}
    components = {}
    cycles = {}
    allocations = {}
    for mode, root in runs.items():
        audits[mode] = json.loads((root / "uvm_result.json").read_text())
        uvm = audits[mode]
        if uvm.get("status") != "PASS" or uvm.get("issues"):
            issues.append(f"{mode}: real-DUT UVM audit failed")
        work = root / "work"
        log = work / "run.vcs.log"
        trace = work / "vector_trace.csv"
        expected_elf = rvv_elf if mode == "rvv" else akv_elf
        if digest(work / "input.elf") != digest(expected_elf):
            issues.append(f"{mode}: VCS input ELF differs from frozen input")
        for key, path in (("elf_sha256", work / "input.elf"),
                          ("log_sha256", log),
                          ("vector_trace_sha256", trace)):
            if uvm.get(key) != digest(path):
                issues.append(f"{mode}: UVM {key} does not match current file")
        for manifest, required in (
            ("INPUT_SHA256SUMS", {"work/input.elf"}),
            ("RUN_SHA256SUMS", {"work/run.vcs.log", "work/vector_trace.csv",
                                "uvm_result.json", "INPUT_SHA256SUMS"}),
        ):
            issues.extend(verify_manifest(root / manifest, root, required,
                                          archived_legacy_runner(archived_runner)))
        components[mode] = image_components(root / "INPUT_SHA256SUMS")
        cycles[mode] = operator_record(log, mode, issues)
        allocations[mode] = custom_allocations(trace)
    if (not components["rvv"] or components["rvv"] != components["akv_v2"] or
            components["rvv"].get("simv") != audits["rvv"].get("simv_sha256") or
            components["akv_v2"].get("simv") != audits["akv_v2"].get("simv_sha256") or
            audits["rvv"].get("sim_image_sha256") !=
            audits["akv_v2"].get("sim_image_sha256")):
        issues.append("paired VCS images differ")
    if any(allocations["rvv"].values()):
        issues.append("standard RVV trace contains custom2 instructions")
    if (allocations["akv_v2"]["fill_v2"] == 0 or
            allocations["akv_v2"]["column_v2"] == 0 or
            allocations["akv_v2"]["value_load"] == 0 or
            allocations["akv_v2"]["release"] == 0 or
            allocations["akv_v2"]["other_custom2"] != 0):
        issues.append("AKV-v2 trace lacks expected fill/column/value/release activity")
    rvv_cycles, akv_cycles = cycles["rvv"], cycles["akv_v2"]
    return {
        "status": "PASS" if not issues else "FAIL",
        "issues": issues,
        "scope": "single real Qwen2.5 decode Attention core; kernel timing excludes device init",
        "rvv_cycles": rvv_cycles,
        "akv_v2_cycles": akv_cycles,
        "rvv_over_akv_v2_speedup": (rvv_cycles / akv_cycles
                                      if rvv_cycles and akv_cycles else None),
        "captured_input_sha256": source_hashes,
        "rvv_elf_sha256": digest(rvv_elf),
        "akv_v2_elf_sha256": digest(akv_elf),
        "rvv_assembly_sha256": digest(rvv_asm),
        "akv_v2_assembly_sha256": digest(akv_asm),
        "vcs_image_components": components["rvv"],
        "custom_allocations": allocations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rvv-run", "akv-run", "rvv-elf", "akv-elf",
                 "rvv-asm", "akv-asm", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit_pair(args.rvv_run.resolve(), args.akv_run.resolve(),
                            args.rvv_elf.resolve(), args.akv_elf.resolve(),
                            args.rvv_asm.resolve(), args.akv_asm.resolve())
    except (OSError, ValueError, KeyError) as error:
        result = {"status": "FAIL", "issues": [str(error)]}
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"RVV/AKV real-DUT paired evidence: {result['status']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
