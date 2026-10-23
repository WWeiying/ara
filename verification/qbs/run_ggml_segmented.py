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


def verify_native_build(qemu):
    receipt = qemu.parent / "native-model-manifest.json"
    data = json.loads(receipt.read_text())
    if data.get("state") != "PASS" or data.get("executable") != str(qemu) or data.get("executable_sha256") != digest(qemu):
        raise RuntimeError("Native QEMU executable differs from its build receipt")
    sources = data.get("source_sha256", {})
    model = qemu.parent.parent / "qemu-10.2.0/target/riscv"
    config = qemu.parent / "config-host.mak"
    ninja = qemu.parent / "build.ninja"
    configured = re.findall(r"^SRC_PATH=(.+)$", config.read_text(), re.M)
    if len(configured) != 1 or Path(configured[0]).resolve() != model.parents[1]:
        raise RuntimeError("Native QEMU build uses a different source tree")
    if str(config) not in sources or str(ninja) not in sources:
        raise RuntimeError("Native QEMU receipt omits build configuration")
    for name in ("qbs_helper.c", "qbs_ref.c"):
        inputs = re.findall(r"^build libqemu-riscv64-softmmu\.a\.p/target_riscv_" +
                            re.escape(name) + r"\.o: c_COMPILER (\S+)", ninja.read_text(), re.M)
        if len(inputs) != 1 or (qemu.parent / inputs[0]).resolve() != model / name:
            raise RuntimeError("Native QEMU model compile input differs from audited source")
    if not all(str(model / name) in sources for name in ("qbs_abi.h", "qbs_ref.h", "qbs_ref.c", "qbs_helper.c")):
        raise RuntimeError("Native QEMU build receipt omits model sources")
    if any(digest(path) != sha for path, sha in sources.items()):
        raise RuntimeError("Native QEMU source/configuration differs from build receipt")
    if digest(qemu.parent / "native-model-build.log") != data.get("build_log_sha256"):
        raise RuntimeError("Native QEMU build log differs from receipt")
    return [receipt, qemu.parent / "native-model-build.log", *map(Path, sources)]


def check_natural_dispatch(output):
    runs = re.findall(r"QBS_GRAPH_RUN_BEGIN segment=(\d+) wide=(\d+)\s+(.*?)QBS_GRAPH_RUN_END", output, re.S)
    if [(s, w) for s, w, _ in runs] != [("0", "0"), ("256", "0"), ("256", "1")]:
        raise RuntimeError("Missing natural-K layout runs")
    expected = {(kind, m, k, threads) for kind, k in (("q4_K", 71680), ("q8_0", 8960))
                for m in (1, 3, 4) for threads in (1, 3)}
    baseline_digests = {}
    for requested, _, trace in runs:
        graphs = re.findall(
            r"QBS_MATRIX_BEGIN type=(\S+) m=(\d+) n=(\d+) k=(\d+) threads=(\d+) segment=(\d+)\s+"
            r"(.*?)QBS MUL_MAT graph: PASS", trace, re.S)
        keys = [(kind, int(m), int(k), int(threads)) for kind, m, _, k, threads, _, _ in graphs]
        if len(keys) != len(expected) or set(keys) != expected:
            raise RuntimeError("Natural-K matrix shape coverage differs")
        for kind, m, n, k, threads, segment, body in graphs:
            m, n, k = int(m), int(n), int(k)
            hashes = re.findall(r"QBS_NATURAL_DIGEST value=([0-9a-f]{16})", body)
            if len(hashes) != 1:
                raise RuntimeError("Missing natural-K output digest")
            key = kind, m, k, threads
            if requested == "0":
                baseline_digests[key] = hashes[0]
            elif baseline_digests.get(key) != hashes[0]:
                raise RuntimeError("Natural-K segmented output differs bitwise from global-R4 baseline")
            if n != 37 or segment != requested:
                raise RuntimeError("Natural-K geometry or effective layout differs")
            calls = re.findall(r"GGML_RISCV_QBS_CALL type=(\S+) mode=\S+ k=(\d+) input_rows=(\d+) output_rows=(\d+) split_k=(\d+)", body)
            if not calls or any(t != kind or int(depth) != k or split != "1" for t, depth, _, _, split in calls):
                raise RuntimeError("Natural-K graph did not select split-K")
            if sum(int(rows) * int(cols) for _, _, rows, cols, _ in calls) != m * n:
                raise RuntimeError("Natural-K dispatch output count differs")
            commands = re.findall(r"GGML_RISCV_QBS_COMMAND[^\n]+ weight_type=(\S+)[^\n]+ m=(\d+) n=(\d+) k_blocks=(\d+) access=(\d+)[^\n]+ emulated=(\d+)", body)
            if not commands or any(t != kind or not 1 <= int(rows) <= 4 or not 1 <= int(cols) <= 32 or
                                   depth not in {"256", "24"} or access != "0" or emulated != "1"
                                   for t, rows, cols, depth, access, emulated in commands):
                raise RuntimeError("Natural-K command contract differs")
            for depth in ("256", "24"):
                if sum(int(rows) * int(cols) for _, rows, cols, blocks, _, _ in commands if blocks == depth) != m * n:
                    raise RuntimeError("Natural-K command work or K-tail coverage differs")
            if threads == "1":
                expected_tiles = [(m, 5), (m, 32)] if requested == "256" else [(m, 1)] + [(m, 4)] * 9
                for depth in ("256", "24"):
                    tiles = sorted((int(rows), int(cols)) for _, rows, cols, blocks, _, _ in commands if blocks == depth)
                    if tiles != expected_tiles:
                        raise RuntimeError("Natural-K per-depth command tiling differs")


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


def check_context_dispatch(output):
    runs = re.findall(r"QBS_GRAPH_RUN_BEGIN segment=(\d+) wide=(\d+)\s+(.*?)QBS_GRAPH_RUN_END", output, re.S)
    if [(s, w) for s, w, _ in runs] != [("0", "0"), ("3", "0"), ("256", "0"), ("256", "0")]:
        raise RuntimeError("Missing context policy runs")
    expected = {(b, m, shared, threads, epoch) for b, m, shared, threads in
                ((2, 1, 1, 1), (7, 1, 1, 1), (7, 1, 0, 1), (7, 1, 1, 3), (7, 3, 1, 1), (7, 4, 1, 1))
                for epoch in (0, 1)}
    for run_index, (requested, _, trace) in enumerate(runs):
        enabled = run_index != 3
        if re.findall(r"QBS_CONTEXT_POLICY enabled=(\d+)", trace) != [str(int(enabled))]:
            raise RuntimeError("Wrong cross-operator context policy")
        graphs = re.findall(r"QBS_CONTEXT_BEGIN blocks=(\d+) m=(\d+) n=(\d+) shared=(\d+) threads=(\d+) epoch=(\d+) segment=(\d+)\s+(.*?)QBS_CONTEXT_PASS outputs=(\d+)", trace, re.S)
        keys = [(int(b), int(m), int(shared), int(threads), int(epoch)) for b, m, _, shared, threads, epoch, _, _, _ in graphs]
        if len(keys) != 12 or set(keys) != expected:
            raise RuntimeError("Incomplete context graph shape/epoch coverage")
        epochs = set()
        for blocks, m, n, shared, threads, _, segment, body, outputs in graphs:
            blocks, m, n, threads = int(blocks), int(m), int(n), int(threads)
            if n != 37 or segment != requested or int(outputs) != 3 * m * n:
                raise RuntimeError("Wrong context graph geometry or checked outputs")
            split = requested == "3" and blocks > 3
            eligible = enabled and shared == "1" and m == 1 and threads == 1 and not split
            actions = re.findall(r"GGML_RISCV_QBS_CROSS_OP graph_epoch=(\d+) action=(\w+) source_id=(\S+)[^\n]+ generation=(\d+)[^\n]+ quantization_skipped=(\d+)", body)
            if eligible:
                if len(actions) != 2 or [(a, skip) for _, a, _, _, skip in actions] != [("fill_keep", "0"), ("reuse_release", "1")]:
                    raise RuntimeError("Eligible graph did not fill/reuse/release exactly once")
                first, second = actions
                if first[0] != second[0] or first[2:4] != second[2:4] or first[0] in epochs:
                    raise RuntimeError("Context identity/generation/epoch mismatch")
                epochs.add(first[0])
            elif actions:
                raise RuntimeError("Ineligible graph skipped activation preparation")
            calls = re.findall(r"GGML_RISCV_QBS_CALL type=(\S+) mode=\S+ k=(\d+) input_rows=(\d+) output_rows=(\d+) split_k=(\d+)", body)
            if not calls or any(t != "q4_K" or int(k) != blocks * 256 or int(s) != split for t, k, _, _, s in calls):
                raise RuntimeError("Wrong context graph dispatch")
            if sum(int(rows) * int(cols) for _, _, rows, cols, _ in calls) != 2 * m * n:
                raise RuntimeError("Missing context graph projection work")
            commands = re.findall(r"GGML_RISCV_QBS_COMMAND[^\n]+ weight_type=(\S+)[^\n]+ m=(\d+) n=(\d+) k_blocks=(\d+) access=(\d+)[^\n]+ emulated=(\d+)", body)
            if not commands or any(t != "q4_K" or emulated != "0" or not 1 <= int(rows) <= 4 or not 1 <= int(cols) <= 32
                                   for t, rows, cols, _, _, emulated in commands):
                raise RuntimeError("Context graph did not execute native QBS commands")
            if sum(int(rows) * int(cols) * int(k) for _, rows, cols, k, _, _ in commands) != 2 * m * n * blocks:
                raise RuntimeError("Context command work differs")
            depths = {3: 2, 1: 1} if split else {blocks: 1}
            if {int(k) for _, _, _, k, _, _ in commands} != set(depths):
                raise RuntimeError("Context command K partitions differ")
            for depth, repetitions in depths.items():
                group = [c for c in commands if int(c[3]) == depth]
                if sum(int(c[1]) * int(c[2]) for c in group) != 2 * m * n * repetitions:
                    raise RuntimeError("Context per-depth command work differs")
                if threads == 1 and sorted((int(c[1]), int(c[2])) for c in group) != sorted([(m, 32), (m, 5)] * (2 * repetitions)):
                    raise RuntimeError("Context single-worker tiling differs")
            accesses = [c[4] for c in commands]
            if split or m != 1 or threads != 1:
                if any(access != "0" for access in accesses):
                    raise RuntimeError("Ineligible command used resident activation context")
            elif accesses != (["1", "2", "2", "3"] if eligible else ["1", "3", "1", "3"]):
                raise RuntimeError("Native context lifetime commands differ")


def check_barrier_dispatch(output):
    runs = re.findall(r"QBS_GRAPH_RUN_BEGIN segment=(\d+) wide=(\d+)\s+(.*?)QBS_GRAPH_RUN_END", output, re.S)
    if [(s, w) for s, w, _ in runs] != [("0", "0"), ("3", "0"), ("256", "0"), ("256", "0")]:
        raise RuntimeError("Missing barrier policy runs")
    for index, (segment, _, trace) in enumerate(runs):
        if re.findall(r"QBS_CONTEXT_POLICY enabled=(\d+)", trace) != [str(int(index != 3))]:
            raise RuntimeError("Wrong barrier context policy")
        graphs = re.findall(r"QBS_CONTEXT_BEGIN blocks=2 m=1 n=37 shared=1 threads=1 epoch=(\d+) segment=(\d+)\s+(.*?)QBS_CONTEXT_MOE_PASS outputs=(\d+)", trace, re.S)
        if [(epoch, s, outputs) for epoch, s, _, outputs in graphs] != [("0", segment, "36"), ("1", segment, "36")]:
            raise RuntimeError("Missing barrier graph/epoch checks")
        for _, _, body, _ in graphs:
            if "GGML_RISCV_QBS_CROSS_OP" in body or "GGML_RISCV_QBS_CONTEXT_WAIT" in body:
                raise RuntimeError("Context reservation crosses a matrix barrier")
            if "QBS_CONTEXT_MOE_BARRIER expert=1 rows=36" not in body or "QBS_CONTEXT_PASS outputs=111" not in body:
                raise RuntimeError("Missing barrier numerical checks")
            calls = re.findall(r"GGML_RISCV_QBS_CALL type=(\S+) mode=\S+ k=(\d+) input_rows=(\d+) output_rows=(\d+) split_k=(\d+)", body)
            if calls != [("q4_K", "512", "1", str(n), "0") for n in (37, 36, 37)]:
                raise RuntimeError("Wrong projection/expert execution order")
            commands = re.findall(r"GGML_RISCV_QBS_COMMAND[^\n]+ weight_type=(\S+)[^\n]+ m=(\d+) n=(\d+) k_blocks=(\d+) access=(\d+)[^\n]+ emulated=(\d+)", body)
            if commands != [("q4_K", "1", str(n), "2", str(a), "0") for n, a in ((32, 1), (5, 3), (32, 1), (4, 3), (32, 1), (5, 3))]:
                raise RuntimeError("Barrier operation-local context lifetimes differ")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--llama", type=Path, default=Path("/home/wangwy/llama/llama.cpp"))
    parser.add_argument("--platform", type=Path, default=Path("/home/wangwy/llama/platforms/cva6-qemu"))
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--suite", choices=("full", "natural", "context", "barrier"), default="full")
    parser.add_argument("--native-qemu", type=Path)
    args = parser.parse_args()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    platform = args.platform.resolve()
    init_source = Path(__file__).with_name("ggml_segmented_init.c")
    cpio_tool = platform / "sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio"
    tools = platform / "tools/bin"
    native = args.suite in {"context", "barrier"}
    if native != (args.native_qemu is not None):
        raise RuntimeError("Context suite requires an explicit native QBS QEMU; other suites use software emulation")
    qemu = args.native_qemu.resolve() if args.native_qemu else tools / "qemu-system-riscv64"
    build = args.binary.resolve().parent.parent
    if args.binary.name != "test-ara-q4k-repack" or not (build / "CMakeCache.txt").is_file():
        raise RuntimeError("Use the test binary in its CMake build/bin directory")
    files = [init_source.resolve(), Path(__file__).resolve(), build / "CMakeCache.txt",
             qemu, platform / "images/Image", platform / "images/fw_dynamic.bin",
             cpio_tool, tools / "riscv64-linux-gcc"]
    files += [args.llama / relative for relative in (
        "ggml/src/ggml-cpu/repack.cpp", "ggml/src/ggml-cpu/arch/riscv/qbs.cpp",
        "ggml/src/ggml-cpu/arch/riscv/qbs.h", "tests/test-ara-q4k-repack.cpp")]
    runtime = Path(__file__).resolve().parents[2] / "software/qbs"
    files += sorted(runtime.glob("src/*.c")) + sorted(runtime.glob("include/qbs/*.h"))
    if args.native_qemu:
        files += verify_native_build(qemu)
        root = runtime.parents[1]
        model = qemu.parent.parent / "qemu-10.2.0/target/riscv"
        if digest(model / "qbs_abi.h") != digest(root / "apps/common/qbs_abi.h") or digest(model / "qbs_ref.c") != digest(root / "verification/qbs/qbs_ref.c"):
            raise RuntimeError("Native QEMU ABI/reference differs from this worktree")
        reference_header = (root / "verification/qbs/qbs_ref.h").read_text().replace("../../apps/common/qbs_abi.h", "qbs_abi.h")
        if (model / "qbs_ref.h").read_text() != reference_header:
            raise RuntimeError("Native QEMU reference header differs")
        files += [model / name for name in ("qbs_abi.h", "qbs_ref.h", "qbs_ref.c", "qbs_helper.c")]
        files += [root / "apps/common/qbs_abi.h", root / "verification/qbs/qbs_ref.h", root / "verification/qbs/qbs_ref.c",
                  root / "verification/qbs/qemu/qemu-10.2.0-xaraqbs.patch"]
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
    status = {"state": "preparing", "kind": "QEMU native QBS functional checks" if native else "QEMU GGML software functional checks", "suite": args.suite}

    def save():
        (args.out / "status.json").write_text(json.dumps(status, indent=2) + "\n")

    save()
    try:
        with (args.out / "build.log").open("wb") as log:
            defines = (["-DQBS_CONTEXT", "-DQBS_BARRIER"] if args.suite == "barrier" else ["-DQBS_CONTEXT"]
                       if native else ["-DQBS_NATURAL_K"] if args.suite == "natural" else [])
            subprocess.run([str(tools / "riscv64-linux-gcc"), *defines, "-march=rv64gc", "-mabi=lp64d",
                            "-O2", "-static", str(init_source), "-o", str(args.out / "init")],
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        listing = args.out / "initramfs.list"
        listing.write_text("dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n"
                           f"file /init {args.out / 'init'} 755 0 0\n"
                           f"file /test {args.binary.resolve()} 755 0 0\n")
        with (args.out / "initramfs.cpio").open("wb") as cpio:
            subprocess.run([str(cpio_tool), str(listing)], stdout=cpio, check=True)
        cpu = "rv64,v=true,vlen=1024,elen=64" + (",xaraqbs=true" if native else "")
        command = [str(qemu), "-M", "virt", "-cpu", cpu,
                   "-smp", "1" if native else "3", "-m", "512M", "-display", "none", "-monitor", "none", "-serial", "stdio",
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
        expected = ([("0", "0", "0"), ("3", "0", "0"), ("256", "0", "0"), ("256", "0", "0")]
                    if native else [("0", "0", "0"), ("256", "0", "0"), ("256", "1", "0")]
                    if args.suite == "natural" else [("0", "0", "0"), ("3", "0", "0"), ("256", "1", "0"), ("3", "1", "0")])
        if rc != 0 or ends != expected or "GUEST_TEST_EXIT=0" not in output:
            raise RuntimeError(f"QEMU/guest failure rc={rc}, completed={ends}")
        if args.suite == "barrier":
            if output.count("QBS context graph suite: PASS cases=2") != 4:
                raise RuntimeError("Missing barrier graph checks")
            check_barrier_dispatch(output)
        elif args.suite == "context":
            if output.count("QBS context graph suite: PASS cases=12") != 4:
                raise RuntimeError("Missing context graph checks")
            check_context_dispatch(output)
        elif args.suite == "natural":
            if output.count("QBS matrix graph suite: PASS cases=12") != 3:
                raise RuntimeError("Missing natural-K graph checks")
            check_natural_dispatch(output)
        else:
            if output.count("QBS matrix graph suite: PASS cases=126") != 4:
                raise RuntimeError("Missing matrix graph checks")
            if output.count("QBS MUL_MAT_ID Q2_K 3-expert graph: PASS") != 8:
                raise RuntimeError("Missing expert graph checks")
            check_graph_dispatch(output)
        drift = [path for path, sha in hashes.items() if digest(path) != sha]
        if drift:
            raise RuntimeError(f"Source/image drift: {drift}")
        status.update(state="PASS", matrix_graphs=8 if args.suite == "barrier" else 48 if args.suite == "context" else 36 if args.suite == "natural" else 504,
                      expert_graphs=8 if args.suite == "full" else 0, manifest_unchanged=True)
    except Exception as exc:
        status.update(state="FAIL", error=str(exc))
        save()
        raise
    save()
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
