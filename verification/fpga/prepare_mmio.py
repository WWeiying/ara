#!/usr/bin/env python3
"""Prepare two isolated AXI/MMIO source overrides; never edit the FPGA export."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
import subprocess

if __package__:
    from .prepare_linux_bundle import file_record, plain_path, save_json
else:
    from prepare_linux_bundle import file_record, plain_path, save_json

ROOT = Path(__file__).resolve().parents[2]
EXPORT = ROOT / "hardware/fpga/ara_dsa_vcu118/rtl"
PATCH = Path(__file__).with_name("patches") / "mmio-read-range.patch"
INPUTS = {
    "axi/src/axi_to_detailed_mem.sv": "dfa78d1f75a355a4552f53d2fc030490c49e767ada5dae2c525c4d554800c506",
    "register_interface/src/axi_to_reg_v2.sv": "df090ca44a38464c16cb88fb859e23e8dc192609a059e0c12f7325e7c87170cb",
}


def validate_patch(text: str) -> None:
    old = re.findall(r"(?m)^--- a/(\S+)$", text)
    new = re.findall(r"(?m)^\+\+\+ b/(\S+)$", text)
    headers = re.findall(r"(?m)^diff --git a/(\S+) b/(\S+)$", text)
    if old != list(INPUTS) or new != old or headers != list(zip(old, old)):
        raise ValueError("patch must target exactly the two approved MMIO files")
    if (re.findall(r"(?m)^--- (.*)$", text) != ["a/" + name for name in old] or
            re.findall(r"(?m)^\+\+\+ (.*)$", text) != ["b/" + name for name in new]):
        raise ValueError("unapproved patch file header")
    if re.search(r"(?m)^(?:rename|copy|new file|deleted file|old mode|new mode|GIT binary)", text):
        raise ValueError("unsupported patch operation")


def prepare(output: Path, export: Path = EXPORT, patch: Path = PATCH) -> dict:
    output, export, patch = map(plain_path, (output, export, patch))
    output.relative_to(ROOT / "verification/out")
    if output == ROOT / "verification/out" or output.exists():
        raise ValueError("output must be a new directory below verification/out")
    patch_text = patch.read_text()
    validate_patch(patch_text)
    sources = {name: file_record(plain_path(export / name)) for name in INPUTS}
    for name, expected in INPUTS.items():
        if sources[name]["sha256"] != expected:
            raise ValueError(f"unreviewed MMIO baseline: {name}")
    patch_record = file_record(patch)
    output.mkdir(parents=True)
    report = dict(schema_version=1, status="PREPARING", applied_to_export=False,
                  sources=sources, patch=patch_record, commands=[], board_boot="NOT_RUN")
    try:
        for name, record in sources.items():
            for root in ("inputs/export", "rtl"):
                destination = output / root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(Path(record["path"]).read_bytes())
                if file_record(destination)["sha256"] != record["sha256"]:
                    raise ValueError(f"copy drift: {name}")
        frozen_patch = output / "inputs/mmio-read-range.patch"
        frozen_patch.write_text(patch_text)
        if file_record(frozen_patch)["sha256"] != patch_record["sha256"]:
            raise ValueError("patch changed during snapshot")
        preparer = output / "inputs/prepare_mmio.py"
        preparer.write_bytes(Path(__file__).read_bytes())
        helper = output / "inputs/prepare_linux_bundle.py"
        helper.write_bytes(Path(__file__).with_name(helper.name).read_bytes())
        report["preparer"] = file_record(preparer)
        report["helper"] = file_record(helper)
        for dry in (True, False):
            command = ["patch", "--batch", "--forward", "--fuzz=0", "-p1",
                       "--input", str(frozen_patch)]
            if dry:
                command.append("--dry-run")
            process = subprocess.run(command, cwd=output / "rtl", capture_output=True,
                                     text=True, timeout=15)
            report["commands"].append(dict(argv=command, cwd=str(output / "rtl"),
                                           returncode=process.returncode,
                                           stdout=process.stdout, stderr=process.stderr))
            if process.returncode or any(term in process.stdout.lower() for term in ("fuzz", "offset")):
                raise ValueError(f"MMIO patch failed: {process.stdout}\n{process.stderr}")
        for name, record in sources.items():
            if file_record(Path(record["path"])) != record:
                raise ValueError(f"live source changed: {name}")
            if file_record(output / "inputs/export" / name)["sha256"] != record["sha256"]:
                raise ValueError(f"pristine input changed: {name}")
        if file_record(patch) != patch_record:
            raise ValueError("live patch changed")
        report["files"] = {name: file_record(output / "rtl" / name) for name in INPUTS}
        report.update(status="PREPARED_NOT_VALIDATED", inputs_unchanged=True)
        save_json(output / "manifest.json", report)
    except BaseException as error:
        report.update(status="FAIL", error=str(error))
        save_json(output / "failure.json", report)
        raise
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = prepare(args.output)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"MMIO preparation failed: {error}\n")
    print(f"{report['status']}: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
