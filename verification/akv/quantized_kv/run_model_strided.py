#!/usr/bin/env python3
"""Fresh native-QBS full-model strided-K gate, after accepted strided graph evidence.

Functional only. Run as the directly owned worker; no queueing or simulator
launch occurs merely by importing this module. Historical interleave pins are
archival identity only, never substituted for current-source acceptance.
"""

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
from run_model_live import (HERE, ROOT, PRIOR, MODEL_PATH, require, digest, hashes,
                            atomic_json, run_command, verify_native_build)
from check_model_strided import check_log
sys.path.insert(0, str(HERE.parent))
from run_after_verified_gate import wait_owner


def json_file(path):
    return json.loads(path.read_text(encoding="utf-8"))


def check_pins(pins):
    require(isinstance(pins, dict) and bool(pins), "empty source manifest")
    for name, sha in pins.items():
        require(Path(name).is_absolute() and digest(Path(name)) == sha,
                "input drift: " + name)


def prerequisite(path, llama):
    receipt = json_file(path / "result.json")
    status = json_file(path / "status.json")
    require(receipt.get("state") == "PASS" and status.get("state") == "PASS"
            and status.get("child_pid") is None,
            "strided graph prerequisite not terminal PASS; do not launch")
    require(receipt.get("current_inputs_match") is True and receipt.get("whole_model") is False,
            "prerequisite is not current graph evidence")
    require(receipt.get("log_sha256") == digest(path / "qemu.log") and
            receipt.get("source_pins_sha256") == digest(path / "source-pins.json"),
            "graph receipt/log/manifest mismatch")
    pins = json_file(path / "source-pins.json")
    critical = {HERE / "check_strided_graph.py", HERE / "run_strided_graph.py",
                HERE / "ggml_strided/test.cpp", llama / "ggml/src/ggml-cpu/arch/riscv/quant-kv.cpp",
                ROOT / "software/akv/experimental/quantized_kv/runtime_strided.c",
                ROOT / "software/akv/experimental/quantized_kv/ggml_entry_strided.h"}
    require(all(str(p) in pins for p in critical), "prerequisite omits strided implementation/checker")
    check_pins(pins)
    checker = importlib.import_module("check_strided_graph")
    checked = checker.check_log((path / "qemu.log").read_bytes().decode("utf-8"))
    require(checked.get("native_calls") == 16 and checked.get("native_command_attempts") == 160
            and checked.get("key_panels") == 40 and checked.get("key_bytes") == 110656,
            "wrong strided graph coverage/work")
    for key, value in checked.items():
        if key != "state":
            require(receipt.get(key) == value, "raw prerequisite disagrees with receipt: " + key)
    return pins


def check_snapshot(snapshot, llama):
    manifest = json_file(snapshot / "manifest.json")
    require(manifest.get("source") == str(llama) and
            digest(snapshot / "source.patch") == manifest.get("patch_sha256"),
            "external integration snapshot identity mismatch")
    sources = manifest.get("source_sha256", {})
    require("ggml/src/ggml-cpu/arch/riscv/quant-kv.cpp" in sources and
            "ggml/src/ggml-cpu/CMakeLists.txt" in sources, "incomplete external snapshot")
    paths = set()
    for name, sha in sources.items():
        path = (llama / name).resolve(strict=True)
        require(path.is_relative_to(llama) and digest(path) == sha,
                "current external source differs from snapshot: " + name)
        paths.add(path)
    return paths | {snapshot / "manifest.json", snapshot / "source.patch"}


def check_compile_sources(build, llama, pins):
    arch = llama / "ggml/src/ggml-cpu/arch/riscv"
    required = {arch / name for name in ("quant-kv.cpp", "qbs.cpp", "akv.cpp")}
    required.update({HERE / "model_live/test.cpp", llama / "src/llama-context.cpp",
                     llama / "src/llama-model.cpp", ROOT / "software/qbs/src/qbs_runtime.c",
                     ROOT / "software/akv/experimental/quantized_kv/runtime_strided.c"})
    observed = {}
    for row in json_file(build / "compile_commands.json"):
        path = Path(row["file"])
        path = (path if path.is_absolute() else Path(row["directory"]) / path).resolve(strict=True)
        require((path.is_relative_to(llama) or path.is_relative_to(ROOT)) and str(path) in pins,
                "foreign/unpinned compile unit: " + str(path))
        flags = row.get("arguments") or shlex.split(row["command"])
        driver = Path(flags[0])
        require(driver.is_absolute() and driver.name in ("riscv64-linux-gcc", "riscv64-linux-g++")
                and str(driver.resolve(strict=True)) in pins, "foreign/unpinned compiler driver")
        if path in required:
            require(path not in observed, "duplicate required compile unit")
            observed[path] = flags
    require(set(observed) == required, "missing full-model/strided/native compile units")
    flags = observed[HERE / "model_live/test.cpp"]
    require("-UNDEBUG" in flags and all(i < flags.index("-UNDEBUG") for i, flag in enumerate(flags)
                                       if flag.startswith("-DNDEBUG")), "model test assertions disabled")
    for name in ("quant-kv.cpp", "qbs.cpp", "akv.cpp"):
        require("-DGGML_USE_RISCV_QUANT_KV" in observed[arch / name], "quantized native hook disabled")
    cache = dict(line.split("=", 1) for line in (build / "CMakeCache.txt").read_text().splitlines()
                 if "=" in line and not line.startswith(("#", "//")))
    for key, wanted in (("LLAMA_SOURCE_DIR:PATH", str(llama)),
                        ("GGML_RISCV_QBS_RUNTIME_DIR:PATH", str(ROOT / "software/qbs")),
                        ("GGML_RISCV_AKV_RUNTIME_DIR:PATH", str(ROOT / "software/akv")),
                        ("GGML_RISCV_AKV_QUANT_KV:BOOL", "ON"), ("GGML_RISCV_QBS:BOOL", "ON")):
        require(cache.get(key) == wanted, "wrong CMake cache: " + key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prerequisite", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--gate-owner-pid", type=int, default=0,
                        help="event-wait up to 1800s for this verified graph-worker PID")
    args = parser.parse_args()
    require(1 <= args.timeout <= 7200, "timeout must be 1..7200 seconds")
    require(args.gate_owner_pid >= 0, "gate owner PID must be nonnegative")
    out, build, gate = args.output.resolve(), args.build.resolve(), args.prerequisite.resolve(strict=True)
    require(not out.is_relative_to(build) and not build.is_relative_to(out), "separate build/output required")
    require(not build.exists(), "use a fresh private build directory")
    require(not out.is_relative_to(gate) and not build.is_relative_to(gate), "do not alter prerequisite artifacts")
    out.mkdir(parents=True, exist_ok=False)
    llama = Path("/home/wangwy/llama/llama.cpp")
    platform = Path("/home/wangwy/llama/platforms/cva6-qemu")
    model = Path("/home/wangwy/llama/models/qwen2.5-1.5b-instruct-q4_k_m.gguf")
    disk = platform / "images/qwen2.5-q4km-capture.ext4"
    qemu = ROOT / "verification/out/qbs-native-qemu-build-20261023/qemu-10.2.0-build/qemu-system-riscv64"
    toolchain = Path("/home/wangwy/llama/toolchains/riscv64-cva6-rvv.cmake")
    snapshot = HERE / "llama_integration_strided_20261024"
    cpio = platform / "sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio"
    compiler = platform / "tools/bin/riscv64-linux-gcc"
    state = dict(state="PREFLIGHT", pid=os.getpid(), child_pid=None, build=str(build),
                 prerequisite=str(gate), qemu=str(qemu), scope=__doc__)

    def save():
        atomic_json(out / "status.json", state)

    def interrupted(sig, _frame):
        raise InterruptedError(f"Signal {sig}")

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    for name in list(env):
        if name.startswith(("GGML_", "AKV_", "LLAMA_")) or name in {
                "LD_PRELOAD", "LD_LIBRARY_PATH", "CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS",
                "CC", "CXX", "CMAKE_TOOLCHAIN_FILE", "CMAKE_PREFIX_PATH"}:
            env.pop(name, None)

    def run(argv, name, timeout):
        def started(pid):
            state.update(state=name.upper(), child_pid=pid)
            save()
        atomic_json(out / (name + ".command.json"), list(map(str, argv)))
        try:
            require(run_command(list(map(str, argv)), out / (name + ".log"), timeout, env, started) == 0,
                    name + " failed")
        finally:
            state["child_pid"] = None
            save()

    save()
    try:
        sources = check_snapshot(snapshot, llama)
        sources.update(verify_native_build(qemu))
        # Import before the pre-wait inventory so transitive local checker
        # dependencies are sealed too, without reading incomplete gate artifacts.
        importlib.import_module("check_strided_graph")
        # Historical receipts are pinned as documents, not merged as live source pins.
        prior = json_file(PRIOR / "result.json")
        require(prior.get("state") == "PASS" and digest(PRIOR / "source-pins.json") ==
                prior.get("source_pins_sha256"), "historical interleave receipt identity mismatch")
        atomic_json(out / "prior-only.json", dict(path=str(PRIOR), historical_only=True,
                    current_source_acceptance=False, result_sha256=digest(PRIOR / "result.json"),
                    source_pins_sha256=digest(PRIOR / "source-pins.json")))
        sources.update({Path(__file__).resolve(), HERE / "check_model_strided.py",
                        HERE / "test_model_strided_check.py", HERE / "check_model_live.py",
                        HERE / "test_model_live_check.py", HERE / "run_model_live.py",
                        HERE / "run_live_graph.py", HERE / "run_strided_graph.py",
                        HERE / "check_strided_graph.py", HERE / "test_strided_graph_check.py",
                        PRIOR / "result.json", PRIOR / "source-pins.json", out / "prior-only.json",
                        llama / "CMakeLists.txt", model, disk, toolchain, qemu, cpio, compiler,
                        platform / "images/Image", platform / "images/fw_dynamic.bin",
                        Path("/usr/sbin/debugfs"),
                        Path("/usr/bin/timeout"), Path("/usr/bin/cmake"), Path("/usr/bin/make"),
                        Path(sys.executable).resolve()})
        for directory in (llama / "ggml", llama / "src", llama / "include", llama / "cmake", llama / "vendor",
                          ROOT / "software/qbs", ROOT / "software/akv", HERE / "model_live"):
            sources.update(p for p in directory.rglob("*") if p.is_file() and
                           (p.suffix.lower() in {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".s", ".cmake", ".in"}
                            or p.name == "CMakeLists.txt"))
        for module in tuple(sys.modules.values()):
            name = getattr(module, "__file__", None)
            if name:
                path = Path(name).resolve()
                if path.is_relative_to(ROOT) and path.is_file():
                    sources.add(path)
        tool_bin = Path("/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin")
        for directory in (tool_bin, platform / "tools/bin"):
            for name in ("riscv64-linux-gcc", "riscv64-linux-g++"):
                sources.add(directory / name)
                sources.add((directory / name).resolve(strict=True))
        pins = hashes(sources)
        atomic_json(out / "pre-wait-pins.json", pins)

        def unchanged():
            check_pins(pins)

        unchanged()
        if args.gate_owner_pid:
            state.update(state="WAITING_GATE", gate_owner_pid=args.gate_owner_pid)
            save()
            wait_owner(gate, args.gate_owner_pid, HERE / "run_strided_graph.py", 1800)
        unchanged()
        gate_pins = prerequisite(gate, llama)
        gate_paths = {Path(name) for name in gate_pins} | {
            gate / "result.json", gate / "status.json", gate / "source-pins.json", gate / "qemu.log",
            out / "pre-wait-pins.json"}
        completed_pins = hashes(gate_paths)
        require(all(completed_pins.get(name) == sha for name, sha in gate_pins.items()),
                "prerequisite inputs changed while collecting fresh pins")
        for name, sha in completed_pins.items():
            require(name not in pins or pins[name] == sha, "pre-wait/prerequisite source mismatch: " + name)
        pins.update(completed_pins)
        atomic_json(out / "source-pins.json", pins)
        unchanged()
        require(not build.exists(), "build directory appeared while waiting; refuse reuse")
        run(["/usr/bin/cmake", "-S", HERE / "model_live", "-B", build,
             "-DLLAMA_SOURCE_DIR=" + str(llama), "-DCMAKE_TOOLCHAIN_FILE=" + str(toolchain),
             "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_EXE_LINKER_FLAGS=-static"], "configure", 180)
        check_compile_sources(build, llama, pins)
        run(["/usr/bin/cmake", "--build", build, "--target", "quant-kv-model-live", "-j16"], "build", 1800)
        check_compile_sources(build, llama, pins)
        unchanged()
        argv = ["/usr/bin/timeout", "-k", "10", "180", "/usr/sbin/debugfs", "-R", "cat " + MODEL_PATH, str(disk)]
        atomic_json(out / "disk-model.command.json", argv)
        with (out / "disk-model.log").open("xb") as log:
            process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=log, env=env, start_new_session=True)
            state.update(state="CHECKING_MODEL_DISK", child_pid=process.pid)
            save()
            value, length = hashlib.sha256(), 0
            try:
                for chunk in iter(lambda: process.stdout.read(4 * 1024 * 1024), b""):
                    value.update(chunk)
                    length += len(chunk)
                require(process.wait(timeout=10) == 0, "cannot read guest model from disk")
            finally:
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
                process.stdout.close()
                state["child_pid"] = None
                save()
        require(length == model.stat().st_size and value.hexdigest() == pins[str(model)],
                "guest disk model differs from selected GGUF")
        atomic_json(out / "model-identity.json", dict(host=str(model), guest=MODEL_PATH, bytes=length,
                    sha256=value.hexdigest(), disk=str(disk), disk_sha256=pins[str(disk)]))
        run([compiler, "-march=rv64gc", "-mabi=lp64d", "-O2", "-static", HERE / "model_live/init.c",
             "-o", out / "init"], "init-build", 120)
        binary = build / "quant-kv-model-live"
        require(binary.is_file(), "missing full-model executable")
        listing = out / "initramfs.list"
        require(all(not any(c.isspace() for c in str(p)) for p in (out, binary)), "cpio paths contain whitespace")
        listing.write_text("dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\ndir /model 755 0 0\n"
                           f"file /init {out / 'init'} 755 0 0\nfile /test {binary} 755 0 0\n")
        with (out / "initramfs.cpio").open("xb") as dest, (out / "cpio.log").open("xb") as log:
            subprocess.run([cpio, listing], stdout=dest, stderr=log, env=env, check=True, timeout=60)
        pins.update(hashes([binary, build / "CMakeCache.txt", build / "compile_commands.json",
                            out / "init", listing, out / "initramfs.cpio", out / "model-identity.json"]))
        atomic_json(out / "source-pins.json", pins)
        unchanged()
        verify_native_build(qemu)
        run([qemu, "-M", "virt", "-cpu", "rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true",
             "-smp", "1", "-m", "4G", "-display", "none", "-monitor", "none", "-serial", "stdio",
             "-bios", platform / "images/fw_dynamic.bin", "-kernel", platform / "images/Image",
             "-initrd", out / "initramfs.cpio", "-drive", f"file={disk},if=virtio,format=raw,readonly=on",
             "-append", "console=ttyS0 rdinit=/init"], "qemu", args.timeout)
        checked = check_log((out / "qemu.log").read_bytes().decode("utf-8"))
        unchanged()
        verify_native_build(qemu)
        checked.update(state="PASS", current_inputs_match=True, log_sha256=digest(out / "qemu.log"),
                       source_pins_sha256=digest(out / "source-pins.json"), model_sha256=value.hexdigest(),
                       prerequisite_result_sha256=digest(gate / "result.json"), historical_prior_only=str(PRIOR))
        atomic_json(out / "result.json", checked)
        state.update(state="PASS", result=checked)
    except BaseException as exc:
        state.update(state="INTERRUPTED" if isinstance(exc, InterruptedError) else "FAIL", error=repr(exc))
        atomic_json(out / "result.json", dict(state=state["state"], error=repr(exc)))
        raise
    finally:
        state["child_pid"] = None
        save()


if __name__ == "__main__":
    main()
