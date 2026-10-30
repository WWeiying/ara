#!/usr/bin/env python3
"""Check the isolated byte-packing candidate under Linux QEMU, not RTL timing."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from run_half_scale_soc import atomic_json, digest, hashes
from run_tile_context_engine import run_command

ROOT = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--qemu", type=Path, required=True)
    p.add_argument("--platform", type=Path,
                   default=Path("/home/wangwy/llama/platforms/cva6-qemu"))
    p.add_argument("--timeout", type=int, default=600)
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    qemu, platform = args.qemu.resolve(strict=True), args.platform.resolve(strict=True)
    source = ROOT / "verification/qbs"
    cc = platform / "tools/bin/riscv64-linux-gcc"
    cpio = platform / "sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio"
    sources = [Path(__file__), source / "activation_pack_init.c",
               source / "activation_pack_rvv_candidate.h",
               source / "test_activation_pack_candidate.c",
               source / "run_half_scale_soc.py", source / "run_tile_context_engine.py",
               ROOT / "software/qbs/include/qbs/qbs.h", ROOT / "apps/common/qbs_abi.h",
               cc, cpio, qemu, platform / "images/Image", platform / "images/fw_dynamic.bin"]
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
        for avl in (0, 7):
            binary = out / f"init-avl{avl}"
            state["state"] = "building"
            run([cc, "-march=rv64gcv", "-mabi=lp64d", "-O2", "-static",
                 "-fno-tree-vectorize", "-Wall", "-Wextra", "-Werror",
                 f"-DQBS_PACK_CANDIDATE_AVL_LIMIT={avl}",
                 "-I" + str(ROOT / "software/qbs/include"),
                 source / "activation_pack_init.c", "-o", binary],
                out / f"build-avl{avl}.log", 120)
            listing = out / f"init-avl{avl}.list"
            listing.write_text("dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n"
                               f"file /init {binary} 755 0 0\n")
            archive = out / f"init-avl{avl}.cpio"
            with archive.open("wb") as target, (out / f"cpio-avl{avl}.log").open("wb") as log:
                subprocess.run([cpio, listing], stdout=target, stderr=log,
                               check=True, timeout=60)
            for vlen in ((128, 1024) if avl == 0 else (1024,)):
                state["state"] = "running"
                log = out / f"vlen{vlen}-avl{avl}.log"
                run([qemu, "-M", "virt", "-cpu", f"rv64,v=true,vlen={vlen},elen=64",
                     "-smp", "1", "-m", "512M", "-display", "none", "-monitor", "none",
                     "-serial", "stdio", "-bios", platform / "images/fw_dynamic.bin",
                     "-kernel", platform / "images/Image", "-initrd", archive,
                     "-append", "console=ttyS0 rdinit=/init"], log, args.timeout)
                text = log.read_text()
                matches = re.findall(r"^PACK_CANDIDATE_PASS cases=(\d+) rvv=1 avl_limit=(\d+) invalid=14\s*$",
                                     text, re.M)
                if (matches != [("33264", str(avl))] or text.count("PACK_GUEST_EXIT=0") != 1
                        or re.search(r"PACK_CANDIDATE_FAIL|Kernel panic|Illegal instruction", text)):
                    raise ValueError(f"Incomplete or failed pack test: {log}")
                if hashes(sources) != pins:
                    raise ValueError("Pinned sources changed")
                state["cases"].append(dict(vlen=vlen, avl_limit=avl, cases=33264,
                                           log_sha256=digest(log), elf_sha256=digest(binary)))
                save()
        state["state"] = "PASS"
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc))
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
