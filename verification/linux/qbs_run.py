#!/usr/bin/env python3
"""Run three bounded QEMU controls and reject incomplete native evidence."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode = True
from qbs_build import (FIRMWARE, KERNEL, LINUX, QEMU, check, dump, experiment_root,
                       file_record, find_tool, validate_elf, verify_record)
from run_stage import run_stage


def check_console(mode: str, text: str, golden: bytes) -> dict:
    check(mode in ("native", "fallback", "unsupported"), "unknown mode")
    lines = text.splitlines()

    def count(line: str) -> int:
        return lines.count(line)

    check(count(f"[QBS_INIT] mode={mode} rc=0") == 1 and
          count("[QBS_INIT] HASHES PASS") == 1, "init/hash failure")
    check("[QBS] FAIL" not in text and "Kernel panic" not in text, "guest failure")
    invocations = 2 if mode == "unsupported" else 1
    for line in ("OS_CUSTOM_CONTEXT=NOT_VALIDATED", "AKV_NATIVE_COMPUTE=UNAVAILABLE"):
        check(count(line) == invocations, f"scope marker: {line}")
    check(count("[QBS] QUANTIZATION byte_exact=1752") == 1 and
          count("[QBS] GUARDS inputs_unchanged=1 guards=8/8") == 1,
          "quantization/guard evidence missing")
    comparisons = re.findall(r"^\[QBS\] COMPARE (\w+) mismatches=(\d+)/32 max_abs=(\S+) atol=0.002 rtol=0.002$",
                             text, re.M)
    expected_names = ["rvv_frozen", "native_frozen", "native_rvv"] if mode == "native" else ["rvv_frozen"]
    check([c[0] for c in comparisons] == expected_names and
          all(c[1] == "0" and math.isfinite(float(c[2])) and float(c[2]) >= 0
              for c in comparisons), "comparison failure/missing/duplicate")
    trace = re.findall(r"^\[QBS_HOST_TRACE\] info_entries=(\d+) exec_entries=(\d+)$", text, re.M)
    check(len(trace) == 1, "missing/duplicate dynamic trace")
    info, execute = map(int, trace[0])
    counts = [(int(q), int(n)) for q, n in re.findall(
        r"^\[QBS\] COUNTS query_calls=(\d+) native_calls=(\d+)$", text, re.M)]
    check(len(counts) == invocations, "missing/duplicate guest counts")
    output = re.findall(r"^\[QBS\] OUTPUT index=(\d+) bits=([0-9a-f]{8}) golden=\S+$", text, re.M)
    is_native = mode == "native"
    check(count("QBS_NATIVE_COMPUTE=PASS") == int(is_native), "native status contradiction")
    check(count("QBS_NATIVE_COMPUTE=NOT_RUN") == int(not is_native), "fallback status")
    check(count("RVV_FALLBACK=PASS") == int(not is_native), "fallback marker")
    check(count("QBS_NATIVE_COMPUTE=UNSUPPORTED") == int(mode == "unsupported"), "unsupported status")
    if is_native:
        check(info > 0 and execute == 1 and counts == [(info, 1)], "native dynamic counts")
        for marker in ("[QBS_HOST_TRACE] helper_qbs_exec entry=1",
                       "[QBS] CAPABILITY ok", "[QBS] ABI arch=3 desc=2 numerical=1 max_n=32",
                       "[QBS] PLAN emitted_commands=1 M=1 N=32 K_blocks=6 DIRECT",
                       "[QBS] PRECHECK capacity_alignment_rejected native_calls=0 unchanged=1",
                       "[QBS] NATIVE_RETURN status=ok"):
            check(count(marker) == 1, f"missing native evidence: {marker}")
        check([int(i) for i, _ in output] == list(range(32)), "output coverage/order")
        actual = [struct.unpack("<f", bytes.fromhex(bits)[::-1])[0] for _, bits in output]
        reference = struct.unpack("<32f", golden)
        errors = [abs(a - b) for a, b in zip(actual, reference)]
        check(all(math.isfinite(a) and math.isfinite(b) and e <= 0.002 + 0.002 * abs(b)
                  for a, b, e in zip(actual, reference, errors)), "host frozen oracle mismatch")
    else:
        check(info == 0 and execute == 0 and not output and
              "[QBS_HOST_TRACE] helper_qbs_exec entry=" not in text and
              "[QBS] NATIVE_RETURN" not in text and "[QBS] EXEC " not in text,
              "unexpected native execution")
        check(counts == ([(0, 0)] if mode == "fallback" else [(1, 0), (1, 0)]),
              "control query/callback counts")
        if mode == "fallback":
            check(count("[QBS] CAPABILITY disabled") == 1, "forced fallback not disabled")
        else:
            check(count("[QBS] CAPABILITY unavailable signal=SIGILL") == 2 and
                  count("[QBS_INIT] auto_rc=0 require_rc=77") == 1,
                  "unsupported path not rejected")
        errors = []
    return {"status": "PASS", "mode": mode, "info_helper_entries": info,
            "exec_helper_entries": execute, "guest_counts": counts,
            "comparisons": {name: {"mismatches": int(mismatches), "max_abs": float(error)}
                            for name, mismatches, error in comparisons},
            "host_frozen_max_abs": max(errors) if errors else None,
            "QBS_NATIVE_COMPUTE": "PASS" if is_native else "NOT_RUN",
            "OS_CUSTOM_CONTEXT": "NOT_VALIDATED", "AKV_NATIVE_COMPUTE": "UNAVAILABLE",
            "scope": "single-process QEMU functional prerequisite; not RTL/FPGA or performance proof"}


def validate_payload(payload: Path) -> dict:
    manifest = json.loads((payload / "manifest.json").read_text())
    check(manifest["status"] == "BUILT", "build incomplete")
    for record in [*manifest["inputs"], *manifest["outputs"].values()]:
        verify_record(record)
    capture = json.loads((payload / "capture.json").read_text())
    for record in [*capture["source"].values(), *capture["files"].values()]:
        verify_record(record)
    validate_elf(payload / "qbs_native", (payload / "elf.txt").read_text(),
                 (payload / "elf.objdump").read_text())
    return capture


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt")
    args = parser.parse_args()
    root = experiment_root(args.attempt)
    payload = root / "payload"
    capture = validate_payload(payload)
    cases = {}
    for mode in ("native", "fallback", "unsupported"):
        output = root / mode
        check(not output.exists() and not output.is_symlink(), f"refuse overwrite: {output}")
        enabled = mode != "unsupported"
        command = [str(find_tool("timeout")), "--signal=TERM", "--kill-after=5s", "150s",
                   str(find_tool("gdb")), "-nx", "-nh", "--batch", "--return-child-result",
                   "-iex", "set auto-load off", "-x", str(LINUX / "qbs_trace.gdb"), "--args",
                   str(QEMU), "-machine", "virt", "-cpu",
                   "rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=" + str(enabled).lower(),
                   "-smp", "1", "-m", "512M", "-no-reboot", "-display", "none",
                   "-monitor", "none", "-serial", "stdio", "-bios", str(FIRMWARE),
                   "-kernel", str(KERNEL), "-initrd", str(payload / "initramfs.cpio"),
                   "-append", f"console=ttyS0 earlycon=sbi rdinit=/init panic=1 qbs_mode={mode}"]
        artifacts = {"kernel": KERNEL, "firmware": FIRMWARE, "emulator": QEMU,
                     "elf": payload / "qbs_native", "initramfs": payload / "initramfs.cpio",
                     "payload_manifest": payload / "manifest.json", "capture": payload / "capture.json",
                     "gdb_trace": LINUX / "qbs_trace.gdb", "runner": LINUX / "qbs_run.py",
                     **{name: Path(record["path"]) for name, record in capture["files"].items()}}
        before = {name: file_record(path) for name, path in artifacts.items()}
        result = run_stage("qemu", output, command,
                           [f"[QBS_INIT] mode={mode} rc=0", "[QBS_INIT] HASHES PASS"], artifacts, 180)
        try:
            check(result["status"] == "PASS", f"stage failed: {result['errors']}")
            for record in before.values():
                verify_record(record)
            cases[mode] = check_console(mode, (output / "console.log").read_text(),
                                        (payload / "data/golden.bin").read_bytes())
        except ValueError as error:
            cases[mode] = {"status": "FAIL", "error": str(error),
                           "QBS_NATIVE_COMPUTE": "NOT_VALIDATED",
                           "OS_CUSTOM_CONTEXT": "NOT_VALIDATED", "AKV_NATIVE_COMPUTE": "UNAVAILABLE"}
        cases[mode]["evidence"] = {name: file_record(output / name)
                                   for name in ("console.log", "stage_result.json", "command.json")}
        dump(output / "check.json", cases[mode])
        print(json.dumps({"mode": mode, "status": cases[mode]["status"],
                          "elapsed_s": result["elapsed_s"]}), flush=True)
        if cases[mode]["status"] != "PASS":
            break
    validate_payload(payload)
    success = len(cases) == 3 and all(c["status"] == "PASS" for c in cases.values())
    dump(root / "summary.json", {"status": "PASS" if success else "FAIL", "cases": cases,
                               "OS_CUSTOM_CONTEXT": "NOT_VALIDATED", "AKV_NATIVE_COMPUTE": "UNAVAILABLE",
                               "RTL_FPGA": "NOT_VALIDATED", "full_model": "NOT_RUN"})
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
