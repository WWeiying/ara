#!/usr/bin/env python3
"""Build and run paired GGML tile-context graphs using native QBS QEMU.

This is a functional integration gate, not an RTL performance measurement.
Run the worker directly under systemd; the output directory must be new.
"""
import argparse
import os
from pathlib import Path
import signal
import subprocess

from run_ggml_segmented import verify_native_build
from run_half_scale_soc import atomic_json, digest, hashes
from run_tile_context_engine import run_command

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--llama", type=Path, default=Path("/home/wangwy/llama/llama.cpp"))
    parser.add_argument("--platform", type=Path,
                        default=Path("/home/wangwy/llama/platforms/cva6-qemu"))
    parser.add_argument("--toolchain", type=Path,
                        default=Path("/home/wangwy/llama/toolchains/riscv64-cva6-rvv.cmake"))
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    if args.jobs < 1 or args.timeout < 1:
        parser.error("jobs and timeout must be positive")
    from check_ggml_tile_context import check_output

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = ROOT / "verification/qbs/ggml_tile_context"
    llama = args.llama.resolve(strict=True)
    platform = args.platform.resolve(strict=True)
    toolchain = args.toolchain.resolve(strict=True)
    qemu = args.qemu.resolve(strict=True)
    runtime = ROOT / "software/qbs"
    tools = platform / "tools/bin"
    cpio_tool = platform / "sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio"
    build = out / "build"
    state = {"state": "preparing", "pid": os.getpid(), "scope": __doc__,
             "source_root": str(ROOT), "llama": str(llama), "qemu": str(qemu),
             "output": str(out), "child_pid": None}

    def save():
        atomic_json(out / "status.json", state)

    def run(argv, log, timeout=600):
        def started(pid):
            state.update(child_pid=pid, command=list(map(str, argv)), log=str(log))
            save()
        try:
            rc = run_command(list(map(str, argv)), log, timeout, os.environ.copy(), started)
            if rc:
                raise RuntimeError(f"Command failed rc={rc}: {log}")
        finally:
            state["child_pid"] = None
            save()

    def interrupted(signum, _frame):
        raise InterruptedError(f"worker received signal {signum}")

    handlers = {s: signal.signal(s, interrupted) for s in (signal.SIGTERM, signal.SIGINT)}
    save()
    try:
        verify_native_build(qemu)
        model = qemu.parent.parent / "qemu-10.2.0/target/riscv"
        for name, original in (("qbs_abi.h", ROOT / "apps/common/qbs_abi.h"),
                               ("qbs_ref.c", ROOT / "verification/qbs/qbs_ref.c")):
            if digest(model / name) != digest(original):
                raise RuntimeError(f"QEMU uses another worktree's {name}")
        header = (ROOT / "verification/qbs/qbs_ref.h").read_text().replace(
            "../../apps/common/qbs_abi.h", "qbs_abi.h")
        if (model / "qbs_ref.h").read_text() != header:
            raise RuntimeError("QEMU reference header mismatch")
        sources = {Path(__file__).resolve(), toolchain, llama / "CMakeLists.txt",
                   ROOT / "verification/qbs/check_ggml_tile_context.py",
                   ROOT / "verification/qbs/run_ggml_segmented.py",
                   ROOT / "verification/qbs/run_half_scale_soc.py",
                   ROOT / "verification/qbs/run_tile_context_engine.py",
                   ROOT / "apps/common/qbs_abi.h", qemu,
                   qemu.parent / "native-model-manifest.json",
                   platform / "images/Image", platform / "images/fw_dynamic.bin",
                   cpio_tool, tools / "riscv64-linux-gcc"}
        for directory in (source, runtime, llama / "ggml", llama / "cmake"):
            sources.update(p for p in directory.rglob("*") if p.is_file() and
                           (p.suffix in {".c", ".cpp", ".h", ".hpp", ".S", ".cmake"}
                            or p.name == "CMakeLists.txt"))
        pinned = hashes(sources)
        atomic_json(out / "manifest.json", pinned)

        def unchanged():
            drift = [p for p, sha in pinned.items() if digest(Path(p)) != sha]
            if drift:
                raise RuntimeError(f"Source/image drift: {drift}")

        state["state"] = "configuring"
        run(["cmake", "-S", source, "-B", build,
             "-DLLAMA_SOURCE_DIR=" + str(llama),
             "-DCMAKE_TOOLCHAIN_FILE=" + str(toolchain),
             "-DGGML_RISCV_QBS_RUNTIME_DIR=" + str(runtime),
             "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_SHARED_LIBS=OFF",
             "-DCMAKE_EXE_LINKER_FLAGS=-static", "-DGGML_NATIVE=OFF",
             "-DGGML_OPENMP=OFF", "-DGGML_RVV=ON", "-DGGML_RISCV_QBS=ON",
             "-DLLAMA_BUILD_TESTS=OFF", "-DLLAMA_BUILD_EXAMPLES=OFF",
             "-DLLAMA_BUILD_TOOLS=OFF", "-DLLAMA_CURL=OFF"], out / "configure.log")
        state["state"] = "building"
        run(["cmake", "--build", build, "--target", "qbs-ggml-tile-context",
             "-j" + str(args.jobs)], out / "build.log", 1800)
        unchanged()
        binary = build / "qbs-ggml-tile-context"
        if not binary.is_file():
            raise RuntimeError("Missing integration test executable")
        run([tools / "riscv64-linux-gcc", "-march=rv64gc", "-mabi=lp64d",
             "-O2", "-static", source / "init.c", "-o", out / "init"],
            out / "init-build.log")
        if any(c.isspace() for p in (out, binary) for c in str(p)):
            raise ValueError("cpio manifest paths must not contain whitespace")
        listing = out / "initramfs.list"
        listing.write_text("dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n"
                           f"file /init {out / 'init'} 755 0 0\n"
                           f"file /test {binary} 755 0 0\n")
        with (out / "initramfs.cpio").open("wb") as cpio, \
                (out / "cpio.log").open("wb") as log:
            subprocess.run([str(cpio_tool), str(listing)], stdout=cpio,
                           stderr=log, check=True, timeout=60)
        pinned.update(hashes({binary, build / "CMakeCache.txt", out / "init",
                              out / "initramfs.cpio", listing}))
        atomic_json(out / "manifest.json", pinned)
        unchanged()
        state["state"] = "running"
        # Thread-interleaving checks intentionally share one hart. This does not
        # validate migration or OS save/restore of the custom context state.
        command = [qemu, "-M", "virt", "-cpu", "rv64,v=true,vlen=1024,elen=64,xaraqbs=true",
                   "-smp", "1", "-m", "512M", "-display", "none", "-monitor", "none",
                   "-serial", "stdio", "-bios", platform / "images/fw_dynamic.bin",
                   "-kernel", platform / "images/Image", "-initrd", out / "initramfs.cpio",
                   "-append", "console=ttyS0 rdinit=/init"]
        atomic_json(out / "command.json", list(map(str, command)))
        run(command, out / "qemu.log", args.timeout)
        result = check_output((out / "qemu.log").read_text(errors="replace"))
        unchanged()
        verify_native_build(qemu)
        state.update(state="PASS", result=result, manifest_unchanged=True,
                     log_sha256=digest(out / "qemu.log"))
    except BaseException as exc:
        state.update(state="INTERRUPTED" if isinstance(exc, (KeyboardInterrupt, InterruptedError))
                     else "FAIL", error=repr(exc))
        raise
    finally:
        save()
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    main()
