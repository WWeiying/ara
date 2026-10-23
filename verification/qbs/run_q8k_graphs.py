#!/usr/bin/env python3
"""Run native QEMU GGML graph selection checks; never report RTL cycles."""
import argparse
import json
import os
from pathlib import Path
import signal

from check_q8k_graphs import check_output
from run_half_scale_soc import atomic_json, digest, hashes
from run_tile_context_engine import run_command
from run_ggml_segmented import verify_native_build


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "configuration", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args()
    build = args.build.resolve(strict=True)
    config_path = args.configuration.resolve(strict=True)
    config = json.loads(config_path.read_text())
    qemu, platform = Path(config["qemu"]), Path(config["platform"])
    report = json.loads((build / "build.json").read_text())
    pins = json.loads((build / "manifest.json").read_text())
    if (report["state"] != "READY" or digest(build / "manifest.json") != report["manifest_sha256"] or
            hashes(map(Path, pins)) != pins):
        raise ValueError("Build input/artifact drift")
    here = Path(__file__).parent
    model_files = verify_native_build(qemu)
    pins.update(hashes([Path(__file__), here / "check_q8k_graphs.py",
        here / "check_ggml_tile_context.py", here / "ggml_m4_prepare_production/check.py",
        here / "run_ggml_segmented.py", here / "run_tile_context_engine.py",
        here / "run_half_scale_soc.py", qemu, *map(Path, model_files),
        config_path, platform / "images/fw_dynamic.bin", platform / "images/Image",
        build / "build.json", build / "manifest.json"]))
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    atomic_json(out / "manifest.json", pins)
    state = dict(state="PREPARING", pid=os.getpid(), child_pid=None,
                 scope="Private GGML graph OFF/ON functional dispatch, VLEN1024; not RTL/model performance")
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
            "rv64,v=true,vlen=1024,elen=64,xaraqbs=true", "-smp", "1", "-m", "512M",
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
