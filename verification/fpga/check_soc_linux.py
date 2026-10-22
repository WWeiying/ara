#!/usr/bin/env python3
"""Independently audit one completed Cheshire/Ara VCS Linux run."""

import argparse
import hashlib
import json
from pathlib import Path
import re


UART_PREFIX = "[CANDIDATE_UART] "
REQUIRED_UART = (
    "OpenSBI v",
    "Linux version",
    "Ara verification Linux init reached",
    "[LINUX_RVV] PASS arithmetic_load_store",
    "[LINUX_RVV] PASS vfredmax_boundary",
    "[LINUX_RVV] PASS preempt_parent",
    "[LINUX_RVV] PASS preempt_child",
    "[LINUX_RVV] PASS signal_return",
    "[LINUX_RVV] PASS scalar_fault_return",
    "[LINUX_RVV] PASS illegal_instruction_return",
    "RVV fallback userspace PASS",
    "RVV context switch and fault return PASS",
    "ARA_LINUX_USERSPACE PASS",
)
FAILURE_MARKERS = (
    "SOC_LINUX_FAIL", "SOC_LINUX_INCOMPLETE", "[LINUX_RVV] FAIL",
    "ARA_LINUX_USERSPACE FAIL", "Kernel panic", "Oops:", "Fatal:",
    "a_invalid_write_data", "[CACHE_SELECTED_X]", "[CACHE_UNMATCHED_RESPONSE]",
)
READ_WARNING = "a_invalid_read_data"
CACHE_PROBE_ACTIVE = "[CACHE_PROBE_ACTIVE] selected-byte and response-ID checks enabled"
PASS_LINE = "SOC_LINUX_PASS mode=LINUX reason=UART_USERSPACE_MARKERS_AND_RTL_ACTIVITY"


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def console_evidence(log, quiet_opensbi=False, cache_probe=False):
    errors = []
    events = [line[len(UART_PREFIX):] for line in log.splitlines()
              if line.startswith(UART_PREFIX)]
    positions = {}
    required = (("Linux version", "SBI specification v", "SBI implementation ID=",
                 *REQUIRED_UART[2:]) if quiet_opensbi else REQUIRED_UART)
    if quiet_opensbi and "OpenSBI v" in log:
        errors.append("quiet OpenSBI unexpectedly printed a boot banner")
    for marker in required:
        hits = [i for i, event in enumerate(events) if marker in event]
        if len(hits) != 1:
            errors.append(f"UART marker {marker!r} seen {len(hits)} times")
        else:
            positions[marker] = hits[0]
    ordered = [marker for marker in required
               if marker not in ("[LINUX_RVV] PASS preempt_parent",
                                 "[LINUX_RVV] PASS preempt_child")]
    if all(marker in positions for marker in ordered):
        if any(positions[left] >= positions[right]
               for left, right in zip(ordered, ordered[1:])):
            errors.append("Linux UART milestones are out of order")
    for marker in ("[LINUX_RVV] PASS preempt_parent", "[LINUX_RVV] PASS preempt_child"):
        if (marker in positions and "[LINUX_RVV] PASS vfredmax_boundary" in positions and
                "[LINUX_RVV] PASS signal_return" in positions and
                not positions["[LINUX_RVV] PASS vfredmax_boundary"] < positions[marker] <
                positions["[LINUX_RVV] PASS signal_return"]):
            errors.append(f"{marker} is outside the context-switch phase")
    if cache_probe and log.count(CACHE_PROBE_ACTIVE) != 1:
        errors.append("cache selected-byte probe was not confirmed active exactly once")
    for marker in FAILURE_MARKERS + (() if cache_probe else (READ_WARNING,)):
        if marker in log:
            errors.append(f"failure marker present: {marker}")
    pass_lines = [line for line in log.splitlines() if line == PASS_LINE]
    if len(pass_lines) != 1 or log.find(PASS_LINE) < log.find(
            UART_PREFIX + "ARA_LINUX_USERSPACE PASS"):
        errors.append("missing, duplicate or premature SoC Linux PASS")

    counts = {}
    for name, pattern in {
        "retirement": r"^\[CANDIDATE_COUNTS\] cycles=(\d+) commits=(\d+) rom=(\d+) payload=(\d+) traps=(\d+)\b",
        "rtc": r"^\[CANDIDATE_COUNTS\] mmio_read=(\d+) mmio_write=(\d+) mailbox_write=(\d+) rtc_ticks=(\d+)\b",
        "ddr": r"^\[CANDIDATE_COUNTS\] ddr_ar=(\d+) ddr_r=(\d+) ddr_aw=(\d+) ddr_w=(\d+) ddr_b=(\d+)\b",
    }.items():
        hits = re.findall(pattern, log, re.M)
        if len(hits) != 1:
            errors.append(f"expected one final {name} counter record, saw {len(hits)}")
        else:
            counts[name] = tuple(map(int, hits[0]))
            if any(value <= 0 for value in counts[name][1:] if name == "retirement"):
                errors.append("ROM, payload or traps had zero activity")
            if name == "rtc" and counts[name][3] <= 0:
                errors.append("RTC had zero activity")
            if name == "ddr" and any(value <= 0 for value in counts[name]):
                errors.append("DDR read/write channels had zero activity")
    if "entry_retired=1" not in log or "exec_ack=1" not in log:
        errors.append("entry retirement or ROM EXEC acknowledgement is missing")
    return {"passed": not errors, "errors": errors, "uart_markers": positions,
            "counters": counts}


def audit(output):
    output = output.resolve()
    errors = []

    def load(path):
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            errors.append(f"cannot read {path}: {exc}")
            return {}

    inputs_path = output / "inputs.json"
    manifest = load(inputs_path)
    summary = load(output / "summary.json")
    command = load(output / "sim/command.json")
    quiet_opensbi = manifest.get("quiet_opensbi", False)
    if type(quiet_opensbi) is not bool:
        errors.append("invalid quiet OpenSBI manifest setting")
        quiet_opensbi = False
    frozen_package = load(output / "inputs/package/manifest.json")
    frozen_quiet = frozen_package.get("simulation_only_linux_override", {}).get(
        "quiet_opensbi", False)
    if type(frozen_quiet) is not bool or frozen_quiet != quiet_opensbi:
        errors.append("quiet OpenSBI setting differs from frozen package")
    console = output / "sim/console.log"
    if manifest.get("mode") != "linux":
        errors.append("frozen SoC mode is not Linux")
    if summary.get("status") != "LINUX_BOOT_PASS":
        errors.append("SoC run did not report LINUX_BOOT_PASS")
    if inputs_path.is_file() and summary.get("inputs_manifest_sha256") != digest(inputs_path):
        errors.append("frozen input manifest hash differs")
    if summary.get("technology", {}).get("passed") is not True:
        errors.append("technology checks did not pass")
    for name in ("compile", "simulation"):
        record = summary.get(name) or {}
        if record.get("returncode") != 0 or record.get("timeout"):
            errors.append(f"{name} failed or timed out")
    records = manifest.get("inputs", {})
    for name, record in records.items():
        path = output / "inputs" / name
        if (not path.is_file() or digest(path) != record.get("sha256") or
                path.stat().st_size != record.get("size_bytes")):
            errors.append(f"frozen input differs: {name}")
    for name in ("fw_jump.elf", "ara_vcu118.dtb", "Image", "initramfs.cpio"):
        if "package/linux/artifacts/" + name not in records:
            errors.append(f"Linux artifact was not frozen: {name}")
    simv = output / "compile/simv"
    if not simv.is_file() or digest(simv) != summary.get("simv_sha256"):
        errors.append("VCS launcher hash differs")
    image = summary.get("simv_image_sha256") or {}
    actual_image = {"simv", *(str(path.relative_to(simv.parent))
                               for path in (simv.parent / "simv.daidir").rglob("*.so"))}
    if not image or "simv" not in image or set(image) != actual_image:
        errors.append("VCS launcher/library image hashes are missing")
    for name, expected in image.items():
        path = output / "compile" / name
        if not path.is_file() or digest(path) != expected:
            errors.append(f"VCS image differs: {name}")
    driver = output / "run_driver.py"
    if summary.get("run_driver_sha256") and (
            not driver.is_file() or digest(driver) != summary["run_driver_sha256"]):
        errors.append("run driver hash differs")
    argv = command.get("argv") or []
    entry = manifest.get("entry")
    if (argv != summary.get("simulation", {}).get("argv") or
            "+LINUX_MODE" not in argv or
            ("+QUIET_OPENSBI" in argv) != quiet_opensbi or
            "+MEM_HEX=" + str(output / "inputs/generated/memory.hex") not in argv or
            not isinstance(entry, int) or f"+BOOT_ENTRY={entry:x}" not in argv or
            str(simv) not in argv):
        errors.append("simulation command differs from frozen Linux run")
    if (command.get("returncode") != 0 or command.get("timeout") or
            command.get("cwd") != str(output / "sim")):
        errors.append("simulation command result or directory is invalid")
    if console.is_file():
        evidence = console_evidence(console.read_text(errors="replace"), quiet_opensbi,
                                    "+CACHE_TAG_PROBE" in argv)
        errors.extend(evidence["errors"])
    else:
        errors.append("simulation console is missing")
        evidence = {}
    return {"status": "PASS" if not errors else "FAIL", "output": str(output),
            "errors": errors, "console": evidence}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="completed run_soc_smoke.py --mode linux directory")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = audit(args.output)
    if args.report:
        args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
