#!/usr/bin/env python3
"""Run the sealed Q8_K candidate against its production generic oracle."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal

from run_half_scale_soc import atomic_json, digest, hashes
from run_tile_context_engine import run_command
from run_ggml_segmented import verify_native_build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "configuration", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    build = args.build.resolve(strict=True)
    config_path = args.configuration.resolve(strict=True)
    config = json.loads(config_path.read_text())
    qemu, platform = Path(config["qemu"]), Path(config["platform"])
    report = json.loads((build / "build.json").read_text())
    pins = json.loads((build / "manifest.json").read_text())
    if report.get("state") != "READY" or digest(build / "manifest.json") != report["manifest_sha256"]:
        raise ValueError("Unsealed build")
    if hashes(map(Path, pins)) != pins:
        raise ValueError("Build input/artifact drift")
    checker = Path(__file__).parent / "ggml_q8k_m4_prepare_native/check.py"
    if pins.get(str(checker)) != digest(checker):
        raise ValueError("Acceptance checker drift")
    spec = importlib.util.spec_from_file_location("q8k_checker", checker)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    model_files = verify_native_build(qemu)
    pins.update(hashes([Path(__file__), config_path, qemu, *map(Path, model_files),
                       platform / "images/fw_dynamic.bin", platform / "images/Image",
                       build / "manifest.json", build / "build.json",
                       Path(__file__).with_name("run_tile_context_engine.py"),
                       Path(__file__).with_name("run_half_scale_soc.py"),
                       Path(__file__).with_name("run_ggml_segmented.py")]))
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    atomic_json(out / "manifest.json", pins)
    state = dict(state="PREPARING", pid=os.getpid(), child_pid=None, cases=[],
                 manifest_sha256=digest(out / "manifest.json"),
                 scope="Q8_K candidate versus production generic: bytes/FCSR/VCSR, not RTL performance")

    def save():
        atomic_json(out / "status.json", state)

    def interrupted(signum, _frame):
        raise InterruptedError(f"signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    save()
    try:
        for vlen in (128, 1024):
            if hashes(map(Path, pins)) != pins:
                raise ValueError("Input drift before execution")
            command = list(map(str, [qemu, "-M", "virt", "-cpu",
                f"rv64,v=true,vlen={vlen},elen=64,xaraqbs=true", "-smp", "1", "-m", "512M",
                "-display", "none", "-monitor", "none", "-serial", "stdio",
                "-bios", platform / "images/fw_dynamic.bin", "-kernel", platform / "images/Image",
                "-initrd", build / "initramfs.cpio", "-append", "console=ttyS0 rdinit=/init"]))
            log = out / f"qemu-{vlen}.log"

            def started(pid):
                state.update(state="RUNNING", child_pid=pid, vlen=vlen, command=command)
                save()

            try:
                rc = run_command(command, log, 900, os.environ.copy(), started)
            finally:
                state["child_pid"] = None
                save()
            if rc:
                raise RuntimeError(f"Guest failed or timed out: {rc}")
            checked = module.check_output(log.read_text(errors="replace"), vlen)
            if hashes(map(Path, pins)) != pins:
                raise ValueError("Input drift during execution")
            state["cases"].append(dict(vlen=vlen, log_sha256=digest(log), report=checked))
            save()
        if state["cases"][0]["report"]["digests"] != state["cases"][1]["report"]["digests"]:
            raise ValueError("VLEN-dependent result digest")
        state.update(state="PASS", checks=sum(c["report"]["checks"] for c in state["cases"]),
                     manifest_unchanged=True)
        atomic_json(out / "pins-after.json", hashes(map(Path, pins)))
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc))
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
