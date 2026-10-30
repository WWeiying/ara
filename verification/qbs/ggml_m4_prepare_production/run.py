#!/usr/bin/env python3
"""Private canonical M4 gate. Prepare first; run the pinned worker under systemd."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parents[2]
sys.path.insert(0, str(SOURCE.parent))
from run_half_scale_soc import atomic_json, digest, hashes
from run_tile_context_engine import run_command
from run_ggml_segmented import verify_native_build
from check import check_native_output, check_output

TARGETS = ["qbs-m4-prepare-" + suffix for suffix in
           ("native", "graph", "init", "native-init", "norvv", "fastmath")]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("prepare", "run"))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--qemu", type=Path)
    p.add_argument("--llama", type=Path, default=Path("/home/wangwy/llama/llama.cpp"))
    p.add_argument("--platform", type=Path, default=Path("/home/wangwy/llama/platforms/cva6-qemu"))
    p.add_argument("--toolchain", type=Path, default=Path("/home/wangwy/llama/toolchains/riscv64-cva6-rvv.cmake"))
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("--timeout", type=int, default=900)
    args = p.parse_args()
    if args.jobs < 1 or args.timeout < 1 or args.timeout > 900:
        p.error("jobs must be positive; timeout must be in 1..900")
    out = args.output.resolve()
    if args.mode == "prepare":
        if not args.qemu:
            p.error("prepare requires --qemu")
        out.mkdir(parents=True, exist_ok=False)
        state = dict(state="PREPARING", pid=os.getpid(), child_pid=None)
    else:
        state = json.loads((out / "status.json").read_text())
        if state["state"] != "READY":
            raise ValueError("Only a fresh READY archive can run")
        state.update(pid=os.getpid(), child_pid=None)

    def save():
        atomic_json(out / "status.json", state)

    def run(argv, log, timeout):
        def started(pid):
            state.update(child_pid=pid, command=list(map(str, argv)), log=str(log))
            save()
        try:
            rc = run_command(list(map(str, argv)), log, timeout, os.environ.copy(), started)
            if rc:
                raise RuntimeError(f"Command returned {rc}: {log}")
        finally:
            state["child_pid"] = None
            save()

    def unchanged(pins):
        changed = [path for path, sha in pins.items() if digest(Path(path)) != sha]
        if changed:
            raise ValueError(f"Pinned source/artifact drift: {changed}")

    def interrupted(signum, _frame):
        raise InterruptedError(f"signal {signum}")

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    save()
    try:
        if args.mode == "prepare":
            qemu, llama, platform = (x.resolve(strict=True) for x in (args.qemu, args.llama, args.platform))
            toolchain = args.toolchain.resolve(strict=True)
            model_files = verify_native_build(qemu)
            model = qemu.parent.parent / "qemu-10.2.0/target/riscv"
            for name, original in (("qbs_abi.h", ROOT / "apps/common/qbs_abi.h"),
                                   ("qbs_ref.c", ROOT / "verification/qbs/qbs_ref.c")):
                if digest(model / name) != digest(original):
                    raise ValueError("QEMU ABI/reference mismatch: " + name)
            expected_header = (ROOT / "verification/qbs/qbs_ref.h").read_text().replace(
                "../../apps/common/qbs_abi.h", "qbs_abi.h")
            if (model / "qbs_ref.h").read_text() != expected_header:
                raise ValueError("QEMU reference header mismatch")
            capture = ROOT / "apps/llama_qwen25_q8_0_prefill_m4_direct_qbs/generated/activation_f32.bin"
            if capture.stat().st_size != 4 * 896 * 4:
                raise ValueError("Wrong captured activation size")
            cpio = platform / "sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio"
            cxx = platform / "tools/bin/riscv64-linux-g++"
            objdump = platform / "tools/bin/riscv64-linux-objdump"
            sources = {Path(__file__), toolchain, qemu, capture, cpio, cxx.resolve(), objdump.resolve(),
                       platform / "images/Image", platform / "images/fw_dynamic.bin", *map(Path, model_files)}
            for name in ("libc.a", "libm.a", "libstdc++.a", "libgcc.a"):
                sources.add(Path(subprocess.check_output([cxx, "-print-file-name=" + name], text=True).strip()).resolve())
            for directory in (SOURCE, SOURCE.parent / "ggml_tile_context", ROOT / "software/qbs",
                              llama / "ggml", llama / "cmake"):
                sources.update(f for f in directory.rglob("*") if f.is_file() and
                               (f.suffix in {".c", ".cpp", ".h", ".hpp", ".S", ".cmake", ".py"}
                                or f.name == "CMakeLists.txt"))
            sources.update(SOURCE.parent / name for name in
                           ("check_ggml_tile_context.py", "run_half_scale_soc.py", "run_tile_context_engine.py",
                            "run_ggml_segmented.py", "qbs_ref.c", "qbs_ref.h"))
            sources.add(ROOT / "apps/common/qbs_abi.h")
            pins = hashes(sources)
            atomic_json(out / "sources-before.json", pins)
            for path in (llama / "ggml/src/ggml-cpu/repack.cpp",
                         llama / "ggml/src/ggml-cpu/arch/riscv/q8_0-m4.h", *SOURCE.glob("*")):
                if path.is_file():
                    dest = out / "snapshot" / path.relative_to(path.anchor)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, dest)
            build = out / "build"
            run(["cmake", "-S", SOURCE, "-B", build, "-DLLAMA_SOURCE_DIR=" + str(llama),
                 "-DCMAKE_TOOLCHAIN_FILE=" + str(toolchain),
                 "-DGGML_RISCV_QBS_RUNTIME_DIR=" + str(ROOT / "software/qbs"),
                 "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_SHARED_LIBS=OFF", "-DCMAKE_EXE_LINKER_FLAGS=-static"],
                out / "configure.log", 120)
            run(["cmake", "--build", build, "--target", *TARGETS, "-j" + str(args.jobs)],
                out / "build.log", 600)
            commands = json.loads((build / "compile_commands.json").read_text())
            repack = [c for c in commands if Path(c["file"]) == llama / "ggml/src/ggml-cpu/repack.cpp"]
            if len(repack) != 1 or "-DGGML_USE_RISCV_QBS" not in repack[0]["command"] or "-ffast-math" in repack[0]["command"]:
                raise ValueError("Expected one native non-fast-math production repack object")
            for key in ("CMAKE_C_COMPILER", "CMAKE_CXX_COMPILER"):
                # Pin the compiler selected by CMake, not only the platform alias.
                for line in (build / "CMakeCache.txt").read_text().splitlines():
                    if line.startswith(key + ":"):
                        pins.update(hashes({Path(line.split("=", 1)[1]).resolve(strict=True)}))
            for name in ("native", "graph"):
                run([objdump, "-d", "-C", build / ("qbs-m4-prepare-" + name)], out / (name + ".disasm"), 60)
            for vlen, init in ((128, "native-init"), (1024, "init")):
                listing = out / f"init-{vlen}.list"
                listing.write_text("dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n"
                    f"file /init {build / ('qbs-m4-prepare-' + init)} 755 0 0\n"
                    f"file /native {build / 'qbs-m4-prepare-native'} 755 0 0\n"
                    f"file /graph {build / 'qbs-m4-prepare-graph'} 755 0 0\n"
                    f"file /capture.bin {capture} 444 0 0\n")
                with (out / f"init-{vlen}.cpio").open("wb") as archive:
                    subprocess.run([cpio, listing], stdout=archive, check=True, timeout=60)
            unchanged(pins)
            pins.update(hashes({*build.glob("qbs-m4-prepare-*"), build / "CMakeCache.txt",
                                build / "compile_commands.json", *out.glob("*.cpio"), *out.glob("*.list"),
                                *out.glob("*.disasm"), *[p for p in (out / "snapshot").rglob("*") if p.is_file()]}))
            atomic_json(out / "manifest.json", pins)
            atomic_json(out / "configuration.json", dict(qemu=str(qemu), platform=str(platform)))
            state.update(state="READY", manifest_sha256=digest(out / "manifest.json"),
                         configuration_sha256=digest(out / "configuration.json"),
                         binaries=hashes(build.glob("qbs-m4-prepare-*")))
        else:
            if digest(out / "manifest.json") != state["manifest_sha256"] or \
                    digest(out / "configuration.json") != state["configuration_sha256"]:
                raise ValueError("Prepared manifest/configuration changed")
            pins = json.loads((out / "manifest.json").read_text())
            config = json.loads((out / "configuration.json").read_text())
            qemu, platform = Path(config["qemu"]), Path(config["platform"])
            unchanged(pins)
            verify_native_build(qemu)
            state.update(state="RUNNING", cases=[])
            for vlen in (128, 1024):
                command = [qemu, "-M", "virt", "-cpu", f"rv64,v=true,vlen={vlen},elen=64,xaraqbs=true",
                           "-smp", "1", "-m", "512M", "-display", "none", "-monitor", "none", "-serial", "stdio",
                           "-bios", platform / "images/fw_dynamic.bin", "-kernel", platform / "images/Image",
                           "-initrd", out / f"init-{vlen}.cpio", "-append", "console=ttyS0 rdinit=/init"]
                atomic_json(out / f"command-{vlen}.json", list(map(str, command)))
                log = out / f"qemu-{vlen}.log"
                run(command, log, args.timeout)
                report = (check_native_output if vlen == 128 else check_output)(log.read_text(errors="replace"))
                unchanged(pins)
                state["cases"].append(dict(vlen=vlen, log_sha256=digest(log), report=report))
                save()
            verify_native_build(qemu)
            unchanged(pins)
            atomic_json(out / "pins-after.json", hashes(map(Path, pins)))
            state.update(state="PASS", manifest_unchanged=True)
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc))
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
