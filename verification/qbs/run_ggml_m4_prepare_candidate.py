#!/usr/bin/env python3
"""Native QEMU byte/FP-environment gate against the compiled GGML M4 oracle.

Reuse the existing private static GGML build; do not rebuild or edit llama.cpp.
This gate measures functional equivalence, never QEMU performance.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from run_half_scale_soc import atomic_json, digest, hashes
from run_tile_context_engine import run_command

ROOT = Path(__file__).resolve().parents[2]


def check_log(text):
    matches = re.findall(
        r"^M4_PREPARE_PASS checks=(\d+) vector=(\d+) fallback=(\d+) bytes=exact fcsr=exact\s*$",
        text, re.M)
    if len(matches) != 1:
        raise ValueError("Missing or duplicate M4 preparation result")
    checks, vector, fallback = map(int, matches[0])
    if (checks != 3375 or vector != 585 or fallback != 2790
            or checks != vector + fallback
            or len(re.findall(r"^M4_CAPTURE_PASS elements=3584 checks=45 vector=9 fallback=36\s*$",
                              text, re.M)) != 1
            or text.count("M4_PREPARE_GUEST_EXIT=0") != 1
            or re.search(r"M4_PREPARE_FAIL|Kernel panic|Illegal instruction|Assertion .*failed", text)):
        raise ValueError("Incomplete or failed M4 preparation test")
    return dict(checks=checks, vector_checks=vector, fallback_checks=fallback)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--qemu", type=Path, required=True)
    p.add_argument("--ggml-build", type=Path, required=True)
    p.add_argument("--llama", type=Path, default=Path("/home/wangwy/llama/llama.cpp"))
    p.add_argument("--platform", type=Path,
                   default=Path("/home/wangwy/llama/platforms/cva6-qemu"))
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--capture", type=Path, default=ROOT /
                   "apps/llama_qwen25_q8_0_prefill_m4_direct_qbs/generated/activation_f32.bin")
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    qemu = args.qemu.resolve(strict=True)
    platform = args.platform.resolve(strict=True)
    build = args.ggml_build.resolve(strict=True)
    capture = args.capture.resolve(strict=True)
    if capture.stat().st_size != 4 * 896 * 4:
        raise ValueError("Expected four real FP32 activation rows of K896")
    ggml = args.llama.resolve(strict=True) / "ggml"
    source = ROOT / "verification/qbs"
    cxx = platform / "tools/bin/riscv64-linux-g++"
    cpio = platform / "sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio"
    libs = [build / "ggml/src" / name for name in
            ("libggml.a", "libggml-cpu.a", "libggml-base.a")]
    oracle_manifest = build.parent / "manifest.json"
    sources = [Path(__file__), source / "ggml_m4_prepare_init.cpp",
               source / "ggml_m4_prepare_candidate.h",
               source / "test_ggml_m4_prepare_candidate.cpp",
               source / "run_half_scale_soc.py", source / "run_tile_context_engine.py",
               *libs, capture, oracle_manifest, build / "compile_commands.json",
               ggml / "src/ggml-cpu/repack.cpp", cxx.resolve(strict=True),
               cpio, qemu, platform / "images/Image", platform / "images/fw_dynamic.bin"]
    # Pin headers too: the candidate shares layout definitions with its oracle.
    sources += list(ggml.rglob("*.h"))
    for name in ("libm.a", "libc.a", "libstdc++.a"):
        library = subprocess.check_output([cxx, "-print-file-name=" + name], text=True).strip()
        sources.append(Path(library).resolve(strict=True))
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
        prior = json.loads(oracle_manifest.read_text())
        prior_ggml = {path: value for path, value in prior.items()
                      if Path(path).is_relative_to(ggml)}
        if str(ggml / "src/ggml-cpu/repack.cpp") not in prior_ggml:
            raise ValueError("Original build did not pin the production oracle")
        if any(digest(Path(path)) != value for path, value in prior_ggml.items()):
            raise ValueError("GGML differs from the reused build's source manifest")
        # Verify the reused build really contains the production oracle source.
        commands = json.loads((build / "compile_commands.json").read_text())
        oracle = [entry for entry in commands
                  if Path(entry["file"]).resolve() == (ggml / "src/ggml-cpu/repack.cpp").resolve()]
        if len(oracle) != 1 or "-ffast-math" in oracle[0].get("command", ""):
            raise ValueError("Expected one non-fast-math production repack oracle")
        atomic_json(out / "oracle_compile.json", oracle[0])
        binary = out / "init"
        state["state"] = "building"
        run([cxx, "-std=gnu++17", "-march=rv64gcv", "-mabi=lp64d", "-O3", "-static",
             "-fno-fast-math", "-Wall", "-Wextra", "-Werror",
             "-isystem", ggml / "include", "-isystem", ggml / "src",
             "-isystem", ggml / "src/ggml-cpu",
             source / "ggml_m4_prepare_init.cpp", "-Wl,--start-group", *libs,
             "-Wl,--end-group", "-lm", "-ldl", "-pthread", "-o", binary],
            out / "build.log", 120)
        elf_hash = digest(binary)
        listing = out / "init.list"
        listing.write_text("dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n"
                           f"file /init {binary} 755 0 0\n"
                           f"file /capture.bin {capture} 444 0 0\n")
        archive = out / "init.cpio"
        with archive.open("wb") as target, (out / "cpio.log").open("wb") as log:
            subprocess.run([cpio, listing], stdout=target, stderr=log, check=True, timeout=60)
        for vlen in (128, 1024):
            state["state"] = "running"
            log = out / f"vlen{vlen}.log"
            run([qemu, "-M", "virt", "-cpu", f"rv64,v=true,vlen={vlen},elen=64",
                 "-smp", "1", "-m", "512M", "-display", "none", "-monitor", "none",
                 "-serial", "stdio", "-bios", platform / "images/fw_dynamic.bin",
                 "-kernel", platform / "images/Image", "-initrd", archive,
                 "-append", "console=ttyS0 rdinit=/init"], log, args.timeout)
            result = check_log(log.read_text())
            if hashes(sources) != pins or digest(binary) != elf_hash:
                raise ValueError("Pinned sources, libraries or ELF changed")
            state["cases"].append(dict(vlen=vlen, **result,
                                       log_sha256=digest(log), elf_sha256=elf_hash))
            save()
        state["state"] = "PASS"
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc))
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
