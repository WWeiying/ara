#!/usr/bin/env python3
"""Audit a stopped-on-UART Cheshire Linux milestone, not a full boot."""

import argparse
import json
from pathlib import Path

try:
    from .check_soc_linux import (CACHE_PROBE_ACTIVE, FAILURE_MARKERS,
                                  UART_PREFIX, digest)
except ImportError:
    from check_soc_linux import (CACHE_PROBE_ACTIVE, FAILURE_MARKERS,
                                 UART_PREFIX, digest)


def audit(output: Path, marker: str) -> dict:
    output = output.resolve()
    errors = []

    def load(path: Path) -> dict:
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            errors.append(f"cannot read {path}: {exc}")
            return {}

    inputs_path = output / "inputs.json"
    inputs = load(inputs_path)
    summary = load(output / "summary.json")
    command = load(output / "sim/command.json")
    if not marker or "\n" in marker:
        errors.append("invalid milestone marker")
    if inputs.get("mode") != "linux":
        errors.append("frozen SoC mode is not Linux")
    if summary.get("status") != "LINUX_UART_MILESTONE_REACHED":
        errors.append("run did not stop at a Linux UART milestone")
    if inputs_path.is_file() and summary.get("inputs_manifest_sha256") != digest(inputs_path):
        errors.append("frozen input manifest hash differs")
    if summary.get("technology", {}).get("passed") is not True:
        errors.append("technology model checks did not pass")

    records = inputs.get("inputs", {})
    if not isinstance(records, dict) or not records:
        errors.append("frozen input records are missing")
        records = {}
    input_root = (output / "inputs").resolve()
    for name, record in records.items():
        path = (input_root / name).resolve()
        if (not path.is_relative_to(input_root) or not path.is_file() or
                digest(path) != record.get("sha256") or
                path.stat().st_size != record.get("size_bytes")):
            errors.append(f"frozen input differs: {name}")
    for name in ("fw_jump.elf", "ara_vcu118.dtb", "Image", "initramfs.cpio"):
        if "package/linux/artifacts/" + name not in records:
            errors.append(f"Linux artifact was not frozen: {name}")

    simv = output / "compile/simv"
    image = summary.get("simv_image_sha256") or {}
    actual_image = {"simv", *(str(path.relative_to(simv.parent))
                               for path in (simv.parent / "simv.daidir").rglob("*.so"))}
    if not image or "simv" not in image or set(image) != actual_image:
        errors.append("VCS launcher/library image hashes are missing")
    for name, expected in image.items():
        path = output / "compile" / name
        if not path.is_file() or digest(path) != expected:
            errors.append(f"VCS image differs: {name}")
    if not simv.is_file() or digest(simv) != summary.get("simv_sha256"):
        errors.append("VCS launcher hash differs")
    driver = output / "run_driver.py"
    if (not driver.is_file() or
            digest(driver) != summary.get("run_driver_sha256")):
        errors.append("run driver hash differs")

    argv = command.get("argv") or []
    entry = inputs.get("entry")
    if (argv != summary.get("simulation", {}).get("argv") or
            "+LINUX_MODE" not in argv or
            "+MEM_HEX=" + str(output / "inputs/generated/memory.hex") not in argv or
            not isinstance(entry, int) or f"+BOOT_ENTRY={entry:x}" not in argv or
            str(simv) not in argv or
            ("+QUIET_OPENSBI" in argv) != inputs.get("quiet_opensbi")):
        errors.append("simulation command differs from frozen Linux run")
    simulation = summary.get("simulation", {})
    if (command.get("cwd") != str(output / "sim") or
            command.get("returncode") != -1 or
            command.get("returncode") != simulation.get("returncode") or
            command.get("uart_milestone_reached") != marker or
            simulation.get("uart_milestone_reached") != marker or
            command.get("timeout") or simulation.get("timeout") or
            not isinstance(simulation.get("last_progress_cycle"), int) or
            simulation["last_progress_cycle"] <= 0):
        errors.append("milestone termination evidence is inconsistent")
    console = output / "sim/console.log"
    if console.is_file():
        log = console.read_text(errors="replace")
        events = [line[len(UART_PREFIX):] for line in log.splitlines()
                  if line.startswith(UART_PREFIX)]
        marker_count = sum(marker in event for event in events)
        if marker_count != 1:
            errors.append(f"UART marker {marker!r} seen {marker_count} times")
        for failure in FAILURE_MARKERS:
            if failure in log:
                errors.append(f"failure marker present: {failure}")
        if "+CACHE_TAG_PROBE" in argv and log.count(CACHE_PROBE_ACTIVE) != 1:
            errors.append("cache selected-byte probe was not confirmed active once")
    else:
        errors.append("simulation console is missing")
        marker_count = 0
    return {"status": "PASS" if not errors else "FAIL", "scope": "UART milestone only; not Linux boot or userspace signoff",
            "output": str(output), "marker": marker, "marker_count": marker_count,
            "last_progress_cycle": simulation.get("last_progress_cycle"),
            "inputs_manifest_sha256": summary.get("inputs_manifest_sha256"),
            "simv_sha256": summary.get("simv_sha256"), "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--marker", default="Linux version")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = audit(args.output, args.marker)
    if args.report:
        args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
