#!/usr/bin/env python3
"""Build and pin the direct production-TU CSR gate. Never launch a simulator."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parents[2]
SPECIALIZATION = "_Z19ggml_quantize_mat_tILl1EL9ggml_type8EEvPKfPvll"
ORACLE = "ggml_quantize_mat_q8_0_4x1"
DEMANGLED_SPECIALIZATION = "void ggml_quantize_mat_t<1l, (ggml_type)8>(float const*, void*, long, long)"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def verify_map(text):
    owners = [line[len(DEMANGLED_SPECIALIZATION):].strip() for line in text.splitlines()
              if line.startswith(DEMANGLED_SPECIALIZATION + " ")]
    require(owners == ["tile-support/ggml/src/libggml-cpu.a(repack.cpp.o)"],
            "Missing/ambiguous production definition in linker cross-reference table")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--llama", type=Path, default=Path("/home/wangwy/llama/llama.cpp"))
    p.add_argument("--platform", type=Path, default=Path("/home/wangwy/llama/platforms/cva6-qemu"))
    p.add_argument("--toolchain", type=Path, default=Path("/home/wangwy/llama/toolchains/riscv64-cva6-rvv.cmake"))
    p.add_argument("--jobs", type=int, default=8)
    args = p.parse_args()
    require(args.jobs > 0, "jobs must be positive")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    build = out / "build"
    llama, platform, toolchain = (x.resolve(strict=True) for x in (args.llama, args.platform, args.toolchain))
    tools = platform / "tools/bin"
    cxx, nm, objdump = (tools / ("riscv64-linux-" + name) for name in ("g++", "nm", "objdump"))
    cpio = platform / "sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio"
    capture = ROOT / "apps/llama_qwen25_q8_0_prefill_m4_direct_qbs/generated/activation_f32.bin"
    require(capture.stat().st_size == 4 * 896 * 4, "Wrong capture geometry")
    repack = llama / "ggml/src/ggml-cpu/repack.cpp"
    helper = llama / "ggml/src/ggml-cpu/arch/riscv/q8_0-m4.h"
    sources = {toolchain, capture, cxx.resolve(), nm.resolve(), objdump.resolve(), cpio,
               platform / "images/Image", platform / "images/fw_dynamic.bin"}
    for name in ("libm.a", "libc.a", "libstdc++.a", "libgcc.a"):
        sources.add(Path(subprocess.check_output([cxx, "-print-file-name=" + name], text=True).strip()).resolve())
    for directory in (SOURCE, SOURCE.parent / "ggml_tile_context", llama / "ggml", llama / "cmake", ROOT / "software/qbs"):
        sources.update(f for f in directory.rglob("*") if f.is_file() and
                       (f.suffix in {".c", ".cpp", ".h", ".hpp", ".S", ".cmake", ".py"} or f.name == "CMakeLists.txt"))
    before = {str(path): sha(path) for path in sorted(sources)}
    write_json(out / "sources-before.json", before)
    commands = []

    def run(argv, name, timeout=120):
        argv = list(map(str, argv))
        commands.append(argv)
        write_json(out / "commands.json", commands)
        with (out / name).open("x") as log:
            subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=timeout)
        return (out / name).read_text()

    state = dict(state="BUILDING", scope=__doc__)
    try:
        run(["cmake", "-S", SOURCE, "-B", build, "-DLLAMA_SOURCE_DIR=" + str(llama),
             "-DCMAKE_TOOLCHAIN_FILE=" + str(toolchain), "-DGGML_RISCV_QBS_RUNTIME_DIR=" + str(ROOT / "software/qbs"),
             "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_SHARED_LIBS=OFF", "-DCMAKE_EXE_LINKER_FLAGS=-static",
             "-DGGML_CCACHE=OFF"], "configure.log")
        run(["cmake", "--build", build, "--target", "qbs-m4-production-csr", "qbs-m4-production-csr-init",
             "-j" + str(args.jobs)], "build.log", 600)
        compiles = json.loads((build / "compile_commands.json").read_text())
        prod_commands = [c for c in compiles if Path(c["file"]) == repack]
        test_commands = [c for c in compiles if Path(c["file"]) == SOURCE / "test.cpp"]
        require(len(prod_commands) == len(test_commands) == 1, "Unique production/test compile entries required")
        prod, test = prod_commands[0], test_commands[0]

        def object_path(entry):
            tokens = shlex.split(entry["command"])
            require(tokens.count("-o") == 1, "Unexpected compile command")
            require(Path(tokens[0]).resolve() == cxx.resolve(), "Compiler differs from pinned GNU toolchain")
            require(not any(t.startswith("-flto") for t in tokens), "LTO would obscure TU ownership")
            return (Path(entry["directory"]) / tokens[tokens.index("-o") + 1]).resolve()

        prod_object, test_object = object_path(prod), object_path(test)
        flags = shlex.split(prod["command"])
        require(all(f in flags for f in ("-DGGML_USE_RISCV_QBS", "-O3", "-DNDEBUG", "-march=rv64gcv")),
                "Production build policy differs")
        require(not any(f in flags for f in ("-ffast-math", "-ffinite-math-only", "-fno-tree-vectorize", "-UNDEBUG")),
                "Production object must retain production FP/optimization flags")
        write_json(out / "production-compile.json", prod)
        write_json(out / "test-compile.json", test)
        test_symbols = run([nm, test_object], "test-symbols.log")
        prod_symbols = run([nm, prod_object], "production-symbols.log")
        for symbol in (SPECIALIZATION, ORACLE):
            require(any(line.split() == ["U", symbol] for line in test_symbols.splitlines()),
                    "Test must reference, not define, production entry: " + symbol)
            require(sum(line.split()[1:] == ["T", symbol] for line in prod_symbols.splitlines()) == 1,
                    "Production object must define entry exactly once: " + symbol)
        require("ggml_riscv_q8_0_m4" not in test_symbols, "Test instantiated the helper")
        dependencies = Path(str(test_object) + ".d").read_text()
        require("q8_0-m4.h" not in dependencies, "Test included the helper")
        relocation = run([objdump, "-dr", test_object], "test-relocations.log")
        require("R_RISCV_CALL_PLT\t" + SPECIALIZATION in relocation and
                "R_RISCV_CALL_PLT\t" + ORACLE in relocation, "Missing direct production/oracle call relocations")
        binary = build / "qbs-m4-production-csr"
        final_symbols = run([nm, binary], "linked-symbols.log")
        for symbol in (SPECIALIZATION, ORACLE):
            require(sum(line.split()[1:] == ["T", symbol] for line in final_symbols.splitlines()) == 1,
                    "Linked production symbol missing/duplicated")
        library = build / "tile-support/ggml/src/libggml-cpu.a"
        archive_symbols = run([nm, "-A", "--defined-only", library], "archive-symbols.log")
        owner = [line for line in archive_symbols.splitlines() if line.endswith(" T " + SPECIALIZATION)]
        require(len(owner) == 1 and ":repack.cpp.o:" in owner[0], "Specialization has another archive owner")
        linkmap = (build / "csr.map").read_text()
        verify_map(linkmap)
        for name in ("m4_tu_production_call", "m4_tu_oracle_call", SPECIALIZATION):
            run([objdump, "-d", "--disassemble=" + name, binary], name + ".disasm")
        listing = out / "initramfs.list"
        listing.write_text("dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n"
                           f"file /init {build / 'qbs-m4-production-csr-init'} 755 0 0\n"
                           f"file /test {binary} 755 0 0\nfile /capture.bin {capture} 444 0 0\n")
        with (out / "initramfs.cpio").open("wb") as archive:
            subprocess.run([cpio, listing], stdout=archive, check=True, timeout=60)
        require(all(sha(path) == value for path, value in before.items()), "Source/toolchain drift during build")
        artifacts = {binary, build / "qbs-m4-production-csr-init", prod_object, test_object,
                     build / "csr.map", build / "CMakeCache.txt", build / "compile_commands.json",
                     out / "initramfs.cpio", listing, *out.glob("*.log"), *out.glob("*.disasm"),
                     *out.glob("*-compile.json"), out / "commands.json"}
        artifacts.update((build / "tile-support/ggml/src").glob("*.a"))
        manifest = dict(before)
        manifest.update({str(path): sha(path) for path in sorted(artifacts)})
        write_json(out / "manifest.json", manifest)
        state.update(state="READY", production_object_sha256=sha(prod_object),
                     helper_sha256=sha(helper), repack_sha256=sha(repack), binary_sha256=sha(binary),
                     manifest_sha256=sha(out / "manifest.json"), production_owner=owner[0],
                     test_owns_helper=False, execution="NOT_RUN")
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc))
        raise
    finally:
        write_json(out / "build.json", state)


if __name__ == "__main__":
    main()
