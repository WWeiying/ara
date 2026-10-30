#!/usr/bin/env python3
"""Exercise the public production packing API with independent byte checks.

Linux QEMU is a functional gate, not a performance measurement. RTL timing
remains a separate acceptance using the same runtime implementation.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from run_half_scale_soc import ROOT, atomic_json, digest, hashes
from run_tile_context_engine import run_command


def check_log(text):
    matches = re.findall(
        r"^RUNTIME_PACK_PASS cases=(\d+) invalid=8 bytes=exact guards=exact fcsr_vcsr=exact\s*$",
        text, re.M)
    if (matches != ["10752"] or text.count("RUNTIME_PACK_GUEST_EXIT=0") != 1
            or re.search(r"RUNTIME_PACK_FAIL|Kernel panic|Illegal instruction|Assertion .*failed", text)):
        raise ValueError("Incomplete or failed runtime packing test")
    return {"cases": 10752, "invalid_cases": 8}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--qemu", type=Path, required=True)
    p.add_argument("--platform", type=Path, default=Path("/home/wangwy/llama/platforms/cva6-qemu"))
    p.add_argument("--timeout", type=int, default=600)
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    qemu, platform = args.qemu.resolve(strict=True), args.platform.resolve(strict=True)
    source, runtime = ROOT / "verification/qbs", ROOT / "software/qbs"
    cc = platform / "tools/bin/riscv64-linux-gcc"
    objdump = platform / "tools/bin/riscv64-linux-objdump"
    cpio = platform / "sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio"
    libraries = [Path(subprocess.check_output([cc, "-print-file-name=" + name], text=True).strip())
                 for name in ("libc.a", "libgcc.a")]
    sources = [Path(__file__), source / "runtime_activation_pack_init.c",
               source / "test_runtime_activation_pack.c", source / "run_half_scale_soc.py",
               source / "run_tile_context_engine.py", runtime / "src/qbs_runtime.c",
               *runtime.glob("include/qbs/*.h"), *runtime.glob("src/*.h"),
               cc, objdump, cpio, qemu, *libraries,
               platform / "images/Image", platform / "images/fw_dynamic.bin"]
    pins = hashes(sources)
    atomic_json(out / "manifest.json", pins)
    state = dict(state="preparing", pid=os.getpid(), child_pid=None, cases=[])

    def save():
        atomic_json(out / "status.json", state)

    def run(command, log, timeout):
        def started(pid):
            state.update(child_pid=pid, command=list(map(str, command)), log=str(log))
            save()
        try:
            rc = run_command(list(map(str, command)), log, timeout, os.environ.copy(), started)
            if rc:
                raise RuntimeError(f"Command returned {rc}: {log}")
        finally:
            state["child_pid"] = None
            save()

    save()
    try:
        for mode, avl in (("scalar", 0), ("vector", 0), ("vector", 7)):
            label = f"{mode}-avl{avl}"
            binary = out / f"init-{label}"
            state["state"] = "building"
            flags = ["-DQBS_PACK_FORCE_SCALAR=1"] if mode == "scalar" else []
            flags += [f"-DQBS_PACK_AVL_LIMIT={avl}"]
            run([cc, "-march=rv64gcv", "-mabi=lp64d", "-O2", "-static",
                 "-fno-tree-vectorize", "-fno-tree-slp-vectorize", "-ffunction-sections",
                 "-fdata-sections", "-Wl,--gc-sections", "-Wall", "-Wextra", "-Werror",
                 *flags, "-I" + str(runtime / "include"),
                 source / "runtime_activation_pack_init.c", runtime / "src/qbs_runtime.c",
                 "-o", binary], out / f"build-{label}.log", 120)
            disasm = subprocess.check_output([objdump, "-d", binary], text=True)
            (out / f"disassembly-{label}.txt").write_text(disasm)
            # Require the targeted strided stores in vector builds; libc may
            # itself contain RVV, so absence in a scalar binary is not required.
            if mode == "vector" and ("vsse8.v" not in disasm or "vsse16.v" not in disasm):
                raise ValueError("Missing RVV byte/halfword packing implementation")
            listing = out / f"init-{label}.list"
            listing.write_text("dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n"
                               f"file /init {binary} 755 0 0\n")
            archive = out / f"init-{label}.cpio"
            with archive.open("wb") as target, (out / f"cpio-{label}.log").open("wb") as log:
                subprocess.run([cpio, listing], stdout=target, stderr=log, check=True, timeout=60)
            for vlen in ((128, 1024) if avl == 0 and mode == "vector" else (1024,)):
                if hashes(sources) != pins:
                    raise ValueError("Pinned source drift before guest execution")
                state["state"] = "running"
                log = out / f"vlen{vlen}-{label}.log"
                run([qemu, "-M", "virt", "-cpu", f"rv64,v=true,vlen={vlen},elen=64",
                     "-smp", "1", "-m", "512M", "-display", "none", "-monitor", "none",
                     "-serial", "stdio", "-bios", platform / "images/fw_dynamic.bin",
                     "-kernel", platform / "images/Image", "-initrd", archive,
                     "-append", "console=ttyS0 rdinit=/init"], log, args.timeout)
                counts = check_log(log.read_text())
                if hashes(sources) != pins:
                    raise ValueError("Pinned source drift during execution")
                state["cases"].append(dict(mode=mode, vlen=vlen, avl_limit=avl,
                    **counts, log_sha256=digest(log), elf_sha256=digest(binary)))
                save()
        state["state"] = "PASS"
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc))
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
