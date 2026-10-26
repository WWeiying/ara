#!/usr/bin/env python3
"""Successor runner for the audited extended-context model; unchanged build/checker."""
import argparse
import json
import os
from pathlib import Path
import signal
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE.parents[1]))

from check import check_output
from run_half_scale_soc import atomic_json, digest, hashes
from run_tile_context_engine import run_command
from run_ggml_segmented import verify_native_build


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--approved-run", action="store_true", required=True)
    args = p.parse_args()
    build = args.build.resolve(strict=True)
    if not build.is_relative_to(HERE) or not args.output.resolve().is_relative_to(HERE):
        raise ValueError("Build and run outputs must remain under graphs/")
    qemu = ROOT / "verification/out/qemu-context-20261023-01/qemu-10.2.0-build/qemu-system-riscv64"
    platform = Path("/home/wangwy/llama/platforms/cva6-qemu")
    abi = qemu.parent.parent / "qemu-10.2.0/target/riscv/qbs_abi.h"
    if (digest(qemu) != "37e3b4c100c3e8fbb7a248f3a0ab328797285dfe59e285fcf8540a14bd5b8e4c" or
            digest(abi) != "4d7bf2d7f78c44bab494d86aee4163a02087b6ad10a43f1ed0752ff3a98fa117"):
        raise ValueError("Audited extended-context model identity changed")
    # The original graph preflight remains mandatory: M8/K32, Q8_K+Q8_0,
    # row-major/M4/M8 context layouts, 4672 bytes and storage version 1.
    report = json.loads((build / "build.json").read_text())
    pins = json.loads((build / "manifest.json").read_text())
    if (report["state"] != "READY" or digest(build / "manifest.json") != report["manifest_sha256"] or
            hashes(map(Path, pins)) != pins):
        raise ValueError("Build input/artifact drift")
    here = HERE.parents[1]
    model_files = verify_native_build(qemu)
    pins.update(hashes([Path(__file__), HERE / "check.py",
        here / "check_ggml_tile_context.py",
        here / "run_ggml_segmented.py", here / "run_tile_context_engine.py",
        here / "run_half_scale_soc.py", qemu, *map(Path, model_files),
        platform / "images/fw_dynamic.bin", platform / "images/Image",
        build / "build.json", build / "manifest.json"]))
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    atomic_json(out / "manifest.json", pins)
    state = dict(state="PREPARING", pid=os.getpid(), child_pid=None,
                 predecessor="graphs/run-01: legacy context capability preflight failure",
                 expected_info2="0x00000e08f0006ff1", expected_info3="0x0000000100001240",
                 scope="Combined-Zvfh GGML OFF/ON functional dispatch, VLEN1024; not RTL/model performance")
    def save():
        atomic_json(out / "status.json", state)
    def started(pid):
        state.update(state="RUNNING", child_pid=pid)
        save()
    def interrupted(signum, _frame):
        raise InterruptedError(f"signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    save()
    try:
        command = list(map(str, [qemu, "-M", "virt", "-cpu",
            "rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true", "-smp", "1", "-m", "512M",
            "-display", "none", "-monitor", "none", "-serial", "stdio",
            "-bios", platform / "images/fw_dynamic.bin", "-kernel", platform / "images/Image",
            "-initrd", build / "initramfs.cpio", "-append", "console=ttyS0 rdinit=/init"]))
        state["command"] = command
        atomic_json(out / "command.json", command)
        log = out / "qemu.log"
        if run_command(command, log, 900, os.environ.copy(), started):
            raise RuntimeError("QEMU guest failed or timed out")
        state.update(state="CHECKING", child_pid=None)
        save()
        checked = check_output(log.read_text())
        if hashes(map(Path, pins)) != pins:
            raise ValueError("Execution provenance drift")
        checked.update(log_sha256=digest(log), manifest_sha256=digest(out / "manifest.json"))
        atomic_json(out / "result.json", checked)
        atomic_json(out / "pins-after.json", hashes(map(Path, pins)))
        state.update(state="PASS", graphs=checked["graphs"],
                     q8k_calls_per_mode=checked["q8k_calls_per_mode"])
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc))
        raise
    finally:
        state["child_pid"] = None
        save()


if __name__ == "__main__":
    main()
