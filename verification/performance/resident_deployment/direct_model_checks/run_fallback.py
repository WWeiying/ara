#!/usr/bin/env python3
"""Full-model RVV fallback check; this does not execute Direct-U hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT.parent / "ara_dsa_signoff_integration/verification/out"
PLATFORM = Path("/home/wangwy/llama/platforms/cva6-qemu")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for data in iter(lambda: f.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.parent != OUT or not out.name.startswith("resident_direct_model_fallback_"):
        parser.error("use a fresh resident_direct_model_fallback_* signoff output")
    if not 1 <= args.timeout <= 1800:
        parser.error("timeout must be 1..1800 seconds")
    out.mkdir()
    inputs = {
        "runner": Path(__file__).resolve(),
        "elf": args.elf.resolve(),
        "init": Path(__file__).with_name("fallback_init.c").resolve(),
        "model": Path("/home/wangwy/llama/models/SmolLM2-135M-Instruct-Q4_K_M.gguf"),
        # Buildroot selects its real compiler from argv[0]; retain the alias.
        "cc": PLATFORM / "tools/bin/riscv64-linux-gcc",
        "qemu": (PLATFORM / "tools/bin/qemu-system-riscv64").resolve(),
        "kernel": (PLATFORM / "images/Image").resolve(),
        "bios": (PLATFORM / "images/fw_dynamic.bin").resolve(),
        "cpio": (PLATFORM / "sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio").resolve(),
    }
    pins = {str(p): digest(p) for p in inputs.values()}
    (out / "source-pins.json").write_text(json.dumps(pins, indent=2) + "\n")
    commands = []
    result = dict(state="FAIL", rtl_executed=False, direct_hardware_executed=False,
                  scope="Full-model no-device fallback, ordinary RVV, four generated tokens")

    def run(name, argv, timeout, binary=False):
        argv = list(map(str, argv))
        commands.append(argv)
        with (out / name).open("wb" if binary else "w") as log:
            subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=True)

    try:
        run("compile.log", [inputs["cc"], "-static", "-O2", "-march=rv64gc", "-mabi=lp64d",
                            inputs["init"], "-o", out / "init"], 60)
        entries = ["dir /dev 0755 0 0", "dir /proc 0755 0 0", "dir /sys 0755 0 0",
                   "nod /dev/console 0600 0 0 c 5 1", f"file /init {out / 'init'} 0755 0 0",
                   f"file /llama-simple {inputs['elf']} 0755 0 0",
                   f"file /model.gguf {inputs['model']} 0444 0 0"]
        (out / "initramfs.list").write_text("\n".join(entries) + "\n")
        run("initramfs.cpio", [inputs["cpio"], out / "initramfs.list"], 120, binary=True)
        start = time.monotonic()
        run("qemu.log", [inputs["qemu"], "-M", "virt", "-cpu",
                         "rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true", "-smp", "1", "-m", "4G",
                         "-display", "none", "-monitor", "none", "-serial", "stdio",
                         "-bios", inputs["bios"], "-kernel", inputs["kernel"],
                         "-initrd", out / "initramfs.cpio", "-append", "console=ttyS0 rdinit=/init"], args.timeout)
        log = (out / "qemu.log").read_text(errors="replace")
        match = re.search(r"DIRECT_MODEL_FALLBACK_RESULT exit=0 identical_logit_bytes=(\d+)", log)
        denied = re.search(r"GGML_AKV_DIRECT_COVERAGE lease_denied=([1-9]\d*) resident_calls=0 native_calls=0 resident_groups=0 native_groups=0 legacy_completed=0 failed=0", log)
        assert match and int(match[1]) > 0 and denied, "Missing checked fallback/path evidence"
        assert "DIRECT_MODEL_FALLBACK_CASE name=rvv exit=0" in log
        assert "DIRECT_MODEL_FALLBACK_CASE name=direct-unavailable exit=0" in log
        assert all(digest(Path(p)) == h for p, h in pins.items()), "input drift"
        result.update(state="FULL_MODEL_RVV_FALLBACK_PASS", identical_logit_bytes=int(match[1]),
                      lease_denied=int(denied[1]), elapsed_seconds=time.monotonic() - start)
    except Exception as exc:
        result["error"] = str(exc)
    (out / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return result["state"] != "FULL_MODEL_RVV_FALLBACK_PASS"


if __name__ == "__main__":
    raise SystemExit(main())
