#!/usr/bin/env python3
"""Reject non-equivalent real-model RVV/QBS inputs before a long DUT run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from elftools.elf.elffile import ELFFile


CASE_FIELDS = ("capture_root", "phase", "operator", "weight_type", "k",
               "rows", "inputs", "capture_rows", "capture_inputs")
INPUTS = ("source_weight.bin", "activation_f32.bin", "golden_f32.bin")
Q8_0_ACTIVATION_WEIGHTS = {"q4_0", "q5_0", "iq4_nl", "q8_0"}


def expected_activation_profile(weight_type: str) -> str:
    return "Q8_0" if weight_type in Q8_0_ACTIVATION_WEIGHTS else "Q8_K"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def elf_identity(path: Path) -> dict:
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        if elf.elfclass != 64 or elf["e_machine"] != "EM_RISCV" or elf["e_type"] != "ET_EXEC":
            raise ValueError(f"not an executable RISC-V ELF64: {path}")
        entry = elf["e_entry"]
    return {"path": str(path.resolve()), "sha256": digest(path), "entry": entry}


def check_r4(source: bytes, packed: bytes, rows: int, block_bytes: int,
             blocks: int) -> bool:
    padded_rows = (rows + 3) & ~3
    if (len(source) != rows * blocks * block_bytes or
            len(packed) != padded_rows * blocks * block_bytes):
        return False
    zero_block = bytes(block_bytes)
    cursor = 0
    for group in range(0, padded_rows, 4):
        for block in range(blocks):
            for offset in range(4):
                row = group + offset
                expected = (source[(row * blocks + block) * block_bytes:
                                   (row * blocks + block + 1) * block_bytes]
                            if row < rows else zero_block)
                if packed[cursor:cursor + block_bytes] != expected:
                    return False
                cursor += block_bytes
    return True


def audit(rvv_app: Path, qbs_app: Path, rvv_elf: Path, qbs_elf: Path,
          simv: Path) -> dict:
    issues = []
    cases = [json.loads((app / "case.json").read_text(encoding="utf-8"))
             for app in (rvv_app, qbs_app)]
    provenance = [json.loads((app / "generated/provenance.json").read_text(
        encoding="utf-8")) for app in (rvv_app, qbs_app)]
    for case, record in zip(cases, provenance):
        if "capture_root" not in case:
            case["capture_root"] = record.get("capture_root")
    for key in CASE_FIELDS:
        if cases[0].get(key) != cases[1].get(key):
            issues.append(f"case {key} differs")
    for name, record in zip(("RVV", "QBS"), provenance):
        if record.get("model_metadata_sha256") != provenance[0].get("model_metadata_sha256"):
            issues.append(f"{name} model metadata differs")
        for key in CASE_FIELDS:
            if record.get(key) != cases[0].get(key):
                issues.append(f"{name} provenance {key} differs from case")
    capture_root = cases[0].get("capture_root")
    if not isinstance(capture_root, str) or not capture_root:
        issues.append("captured model directory is missing")
    else:
        capture_metadata = Path(capture_root) / "model.json"
        if (not capture_metadata.is_file() or
                digest(capture_metadata) != provenance[0].get("model_metadata_sha256")):
            issues.append("captured model metadata differs from provenance")
    files = {}
    for name in (*INPUTS, "embedded_weight.bin"):
        files[name] = []
        for app, record in zip((rvv_app, qbs_app), provenance):
            path = app / "generated" / name
            actual = digest(path)
            described = record.get("tensors", {}).get(name, {}).get("sha256")
            if actual != described:
                issues.append(f"{app.name} {name} differs from provenance")
            files[name].append(actual)
        if name in INPUTS and files[name][0] != files[name][1]:
            issues.append(f"RVV/QBS {name} differs")
    for label, app, elf in (("RVV", rvv_app, rvv_elf),
                            ("QBS", qbs_app, qbs_elf)):
        image = elf.read_bytes()
        for name in ("embedded_weight.bin", "activation_f32.bin", "golden_f32.bin"):
            blob = (app / "generated" / name).read_bytes()
            if blob not in image:
                issues.append(f"{label} ELF does not embed {name}")
    descriptor = provenance[1].get("qbs", {})
    block_elements = descriptor.get("block_elements")
    if (not isinstance(block_elements, int) or block_elements <= 0 or
            cases[0]["k"] % block_elements):
        issues.append("K is not divisible by the declared quantization block size")
    if (descriptor.get("descriptor_version") != 2 or
            descriptor.get("weight_profile") != cases[0]["weight_type"].upper() or
            descriptor.get("weight_layout") != "W_R4_BLOCK_MAJOR" or
            descriptor.get("activation_profile") != expected_activation_profile(
                cases[0]["weight_type"]) or
            descriptor.get("activation_layout") not in (
                "A_ROW_MAJOR", "A_M4_INTERLEAVED", "A_M8_INTERLEAVED")):
        issues.append("QBS descriptor differs from the paired benchmark format")
    if not issues:
        rows = cases[0]["rows"]
        blocks = cases[0]["k"] // block_elements
        if descriptor.get("k_blocks") != blocks:
            issues.append("QBS descriptor block count differs from K")
        source = (qbs_app / "generated/source_weight.bin").read_bytes()
        packed = (qbs_app / "generated/embedded_weight.bin").read_bytes()
        block_bytes = len(source) // (rows * blocks)
        if not check_r4(source, packed, rows, block_bytes, blocks):
            issues.append("QBS embedded weight does not match R4 repack")
    configuration = {}
    for line in (simv.parent / "simulator.conf").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            configuration[key] = value
    for key, expected in (("vlen", "1024"), ("nr_lanes", "4"),
                          ("sim_l2_mb", "4"), ("qbs_enabled", "1")):
        if configuration.get(key) != expected:
            issues.append(f"simulator {key} is not {expected}")
    if not simv.is_file() or not simv.with_name(simv.name + ".daidir").is_dir():
        issues.append("VCS image or its daidir is missing")
    return {
        "status": "READY_NOT_RUN" if not issues else "NOT_READY",
        "scope": "real-model RVV/QBS input, layout and VCS-image preflight; no RTL execution claim",
        "issues": issues,
        "case": {key: cases[0][key] for key in CASE_FIELDS},
        "shared_input_sha256": {name: files[name][0] for name in INPUTS},
        "rvv_embedded_weight_sha256": files["embedded_weight.bin"][0],
        "qbs_embedded_weight_sha256": files["embedded_weight.bin"][1],
        "rvv_elf": elf_identity(rvv_elf),
        "qbs_elf": elf_identity(qbs_elf),
        "simv_sha256": digest(simv),
        "simulator_conf_sha256": digest(simv.parent / "simulator.conf"),
        "case_sha256": {"rvv": digest(rvv_app / "case.json"),
                        "qbs": digest(qbs_app / "case.json")},
        "provenance_sha256": {
            "rvv": digest(rvv_app / "generated/provenance.json"),
            "qbs": digest(qbs_app / "generated/provenance.json"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rvv-app", "qbs-app", "rvv-elf", "qbs-elf", "simv", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    result = audit(args.rvv_app, args.qbs_app, args.rvv_elf, args.qbs_elf, args.simv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"RVV/QBS paired preflight: {result['status']}")
    return 0 if result["status"] == "READY_NOT_RUN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
