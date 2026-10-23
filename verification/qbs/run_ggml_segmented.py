#!/usr/bin/env python3
"""Run actual GGML graph checks under RVV QEMU; no RTL performance claims."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_graph_dispatch(output):
    runs = re.findall(r"QBS_GRAPH_RUN_BEGIN segment=(\d+) wide=(\d+)\s+(.*?)QBS_GRAPH_RUN_END", output, re.S)
    if [(s, w) for s, w, _ in runs] != [("0", "0"), ("3", "0"), ("256", "1"), ("3", "1")]:
        raise RuntimeError("Missing layout runs")
    for requested, wide, trace in runs:
        effective = re.findall(r"QBS_MATRIX_BEGIN[^\n]+segment=(\d+)", trace)
        if len(effective) != 126 or any(s != requested for s in effective):
            raise RuntimeError("Requested and effective weight layout differ")
        commands = re.findall(r"GGML_RISCV_QBS_COMMAND[^\n]+ m=(\d+) ", trace)
        if wide == "1" and requested == "256" and "8" not in commands:
            raise RuntimeError("Wide-M path did not execute")
        if requested == "3" and any(int(m) > 4 for m in commands):
            raise RuntimeError("Forced split-K selected incompatible wide-M")
        experts = re.findall(r"repack: repack tensor qbs_moe_weights[^\n]*\n(.*?)"
                             r"QBS MUL_MAT_ID Q2_K 3-expert graph: PASS \(threads (\d+),", trace, re.S)
        if [threads for _, threads in experts] != ["1", "3"]:
            raise RuntimeError("Missing expert graph dispatch")
        for expert_trace, threads in experts:
            calls = re.findall(r"GGML_RISCV_QBS_CALL type=(\S+) mode=\S+ k=(\d+) input_rows=(\d+) output_rows=(\d+) split_k=(\d+)", expert_trace)
            if not calls or any(t != "q2_K" or k != "1792" or m != "1" or int(split) != (requested == "3")
                                for t, k, m, _, split in calls):
                raise RuntimeError("Wrong expert graph QBS dispatch")
            if sum(int(n) for _, _, _, n, _ in calls) != 48:
                raise RuntimeError("Wrong expert graph output count")
            if requested == "3" and threads == "1" and not re.search(r"GGML_RISCV_QBS_COMMAND[^\n]+ m=1 n=8 k_blocks=3 ", expert_trace):
                raise RuntimeError("Expert graph did not exercise segment-major N8")
    graphs = re.findall(
        r"QBS_MATRIX_BEGIN type=(\S+) m=(\d+) n=(\d+) k=(\d+) threads=(\d+) segment=(\d+)\s+"
        r"(.*?)QBS MUL_MAT graph: PASS", output, re.S)
    if len(graphs) != 504:
        raise RuntimeError(f"Expected 504 independently checked graphs, got {len(graphs)}")
    for kind, m, n, k, threads, segment, trace in graphs:
        calls = re.findall(r"GGML_RISCV_QBS_CALL type=(\S+) mode=\S+ k=(\d+) input_rows=(\d+) output_rows=(\d+) split_k=(\d+)", trace)
        if not calls or any(t != kind or int(depth) != int(k) or int(split) != (int(segment) == 3)
                            for t, depth, _, _, split in calls):
            raise RuntimeError(f"Wrong QBS dispatch for {kind} M{m} N{n} K{k} threads={threads} segment={segment}")
        if sum(int(rows) * int(cols) for _, _, rows, cols, _ in calls) != int(m) * int(n):
            raise RuntimeError("QBS graph output coverage differs from the logical matrix")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--llama", type=Path, default=Path("/home/wangwy/llama/llama.cpp"))
    parser.add_argument("--platform", type=Path, default=Path("/home/wangwy/llama/platforms/cva6-qemu"))
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    platform = args.platform.resolve()
    init_source = Path(__file__).with_name("ggml_segmented_init.c")
    cpio_tool = platform / "sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio"
    tools = platform / "tools/bin"
    build = args.binary.resolve().parent.parent
    if args.binary.name != "test-ara-q4k-repack" or not (build / "CMakeCache.txt").is_file():
        raise RuntimeError("Use the test binary in its CMake build/bin directory")
    files = [init_source.resolve(), Path(__file__).resolve(), build / "CMakeCache.txt",
             tools / "qemu-system-riscv64", platform / "images/Image", platform / "images/fw_dynamic.bin",
             cpio_tool, tools / "riscv64-linux-gcc"]
    files += [args.llama / relative for relative in (
        "ggml/src/ggml-cpu/repack.cpp", "ggml/src/ggml-cpu/arch/riscv/qbs.cpp",
        "ggml/src/ggml-cpu/arch/riscv/qbs.h", "tests/test-ara-q4k-repack.cpp")]
    runtime = Path(__file__).resolve().parents[2] / "software/qbs"
    files += sorted(runtime.glob("src/*.c")) + sorted(runtime.glob("include/qbs/*.h"))
    cache = (build / "CMakeCache.txt").read_text()
    if not re.search(r"CMAKE_HOME_DIRECTORY:[^=]+=" + re.escape(str(args.llama.resolve())) + r"\n", cache):
        raise RuntimeError("CMake source directory differs from the audited llama checkout")
    if not re.search(r"GGML_RISCV_QBS_RUNTIME_DIR:[^=]+=" + re.escape(str(runtime)) + r"\n", cache):
        raise RuntimeError("CMake build must use this worktree's QBS runtime")
    files += sorted(path for path in (args.llama / "ggml").rglob("*")
                    if path.is_file() and path.suffix in {".c", ".cpp", ".h", ".hpp", ".S", ".cmake"})
    hashes = {str(path): digest(path) for path in files}
    with (args.out / "compile.log").open("wb") as log:
        subprocess.run(["cmake", "--build", str(build), "--target", "test-ara-q4k-repack", "-j8"],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    if any(digest(path) != sha for path, sha in hashes.items()):
        raise RuntimeError("Source/configuration changed during build")
    hashes[str(args.binary.resolve())] = digest(args.binary)
    (args.out / "manifest.json").write_text(json.dumps(hashes, indent=2) + "\n")
    (args.out / "llama.patch").write_bytes(subprocess.check_output(
        ["git", "-C", str(args.llama), "diff", "--", "ggml/src/ggml-cpu/repack.cpp",
         "ggml/src/ggml-cpu/arch/riscv/qbs.cpp", "ggml/src/ggml-cpu/arch/riscv/qbs.h",
         "tests/test-ara-q4k-repack.cpp"]))
    status = {"state": "preparing", "kind": "QEMU GGML software functional checks"}

    def save():
        (args.out / "status.json").write_text(json.dumps(status, indent=2) + "\n")

    save()
    try:
        with (args.out / "build.log").open("wb") as log:
            subprocess.run([str(tools / "riscv64-linux-gcc"), "-march=rv64gc", "-mabi=lp64d",
                            "-O2", "-static", str(init_source), "-o", str(args.out / "init")],
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        listing = args.out / "initramfs.list"
        listing.write_text("dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n"
                           f"file /init {args.out / 'init'} 755 0 0\n"
                           f"file /test {args.binary.resolve()} 755 0 0\n")
        with (args.out / "initramfs.cpio").open("wb") as cpio:
            subprocess.run([str(cpio_tool), str(listing)], stdout=cpio, check=True)
        command = [str(tools / "qemu-system-riscv64"), "-M", "virt", "-cpu", "rv64,v=true,vlen=1024,elen=64",
                   "-smp", "3", "-m", "512M", "-display", "none", "-monitor", "none", "-serial", "stdio",
                   "-bios", str(platform / "images/fw_dynamic.bin"), "-kernel", str(platform / "images/Image"),
                   "-initrd", str(args.out / "initramfs.cpio"), "-append", "console=ttyS0 rdinit=/init"]
        (args.out / "command.json").write_text(json.dumps(command, indent=2) + "\n")
        with (args.out / "qemu.log").open("wb") as log:
            with subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT) as process:
                status.update(state="running", qemu_pid=process.pid)
                save()
                try:
                    rc = process.wait(timeout=args.timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    raise
        output = (args.out / "qemu.log").read_text(errors="replace")
        ends = re.findall(r"QBS_GRAPH_RUN_END segment=(\d+) wide=(\d+) exit=(\d+)", output)
        expected = [("0", "0", "0"), ("3", "0", "0"), ("256", "1", "0"), ("3", "1", "0")]
        if rc != 0 or ends != expected or "GUEST_TEST_EXIT=0" not in output:
            raise RuntimeError(f"QEMU/guest failure rc={rc}, completed={ends}")
        if output.count("QBS matrix graph suite: PASS cases=126") != 4:
            raise RuntimeError("Missing matrix graph checks")
        if output.count("QBS MUL_MAT_ID Q2_K 3-expert graph: PASS") != 8:
            raise RuntimeError("Missing expert graph checks")
        check_graph_dispatch(output)
        drift = [path for path, sha in hashes.items() if digest(path) != sha]
        if drift:
            raise RuntimeError(f"Source/image drift: {drift}")
        status.update(state="PASS", matrix_graphs=504, expert_graphs=8, manifest_unchanged=True)
    except Exception as exc:
        status.update(state="FAIL", error=str(exc))
        save()
        raise
    save()
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
