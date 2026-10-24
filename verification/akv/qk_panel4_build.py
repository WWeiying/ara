#!/usr/bin/env python3
"""Build one-query PANEL4 objects and bounded host checks; never run a simulator."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
from qk_panel4_check import check, SINGLE, PANEL

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SRC = ROOT / "software/akv/src"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--before", type=Path, required=True,
                        help="Archived pre-edit assembly and native C sources")
    parser.add_argument("--gcc", type=Path, default=Path(
        "/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc"))
    args = parser.parse_args()
    out = args.output.resolve()
    before_dir = args.before.resolve(strict=True)
    gcc = args.gcc.resolve(strict=True)
    if not gcc.name.endswith("gcc") or "zcc" in str(gcc).lower():
        raise ValueError("GNU compiler required")
    prefix = gcc.name.removesuffix("gcc")
    objdump, objcopy, nm = [gcc.with_name(prefix + tool) for tool in ("objdump", "objcopy", "nm")]
    host = shutil.which("gcc")
    native = SRC / "akv_v2_native_riscv.c"
    assembly = SRC / "akv_v2_attention_rvv.S"
    source = native.read_text()
    start = source.index("/* Optional on freestanding targets:")
    end = source.index("static inline float negative_infinity_f32", start)
    selection = source[start:end]
    declaration = (f"extern void {PANEL}(\n"
                   "    const uint16_t *query, float *score, uint32_t tile_tokens,\n"
                   "    size_t q_row_stride_bytes);\n")
    dispatch = ("  const int qk_panel4 = qk_panel4_enabled_for_plan(plan);\n"
                "  void (*const compute_scores_d128_gqa6)(const uint16_t *, float *, uint32_t, size_t) =\n"
                f"      qk_panel4 ? {PANEL}\n"
                f"                : {SINGLE};\n")
    restored = source.replace(selection, "", 1).replace(declaration, "", 1).replace(dispatch, "", 1)
    restored = restored.replace("      compute_scores_d128_gqa6(\n", f"      {SINGLE}(\n", 1)
    if restored != (before_dir / native.name).read_text():
        raise ValueError("native changes extend beyond the selector/declaration/Decode call")
    if source.count("qk_panel4_enabled_for_plan(plan)") != 1 or \
            source.count("compute_scores_d128_gqa6(\n") != 1:
        raise ValueError("selection must occur once, with one Decode call site")
    out.mkdir(parents=True, exist_ok=False)
    commands = []

    def run(argv, name):
        argv = list(map(str, argv))
        commands.append(argv)
        (out / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        with (out / (name + ".log")).open("x") as log:
            subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                           timeout=120, check=True)
        return (out / (name + ".log")).read_text()

    flags = ["-march=rv64gcv_zfh_zvfh", "-mabi=lp64d", "-mcmodel=medany", "-mno-relax",
             "-O3", "-std=gnu11", "-fno-fast-math", "-ffp-contract=off", "-fno-tree-vectorize",
             "-ffreestanding", "-fno-builtin", "-fno-tree-loop-distribute-patterns", "-fno-common",
             "-ffunction-sections", "-fdata-sections", "-DAKV_REFILL_OVERLAP=0",
             "-DNR_LANES=4", "-DVLEN=1024", "-I" + str(ROOT / "apps/common"),
             "-I" + str(ROOT / "apps/include")]
    monolithic = ROOT / "apps/llama_q4km_operator/akv_runtime.c"
    inputs = {native, assembly, monolithic, SRC / "akv_runtime.c",
              before_dir / native.name, before_dir / assembly.name,
              *HERE.glob("qk_panel4_*.py"), HERE / "qk_panel4_selection_test.c",
              HERE / "qk_panel4_gate.md"}
    for index, path in enumerate((native, assembly, monolithic, SRC / "akv_runtime.c")):
        dep = out / f"deps-{index}.d"
        run([gcc, *flags, "-M", "-MF", dep, path], f"deps-{index}")
        inputs.update(Path(p).resolve(strict=True) for p in shlex.split(
            dep.read_text().replace("\\\n", " ").split(":", 1)[1]))
    pins = {str(p): digest(p) for p in sorted(inputs)}
    (out / "sources-before.json").write_text(json.dumps(pins, indent=2) + "\n")
    run([gcc, "--version"], "gcc-version")
    (out / "qk_panel4_selection.inc").write_text(selection)
    host_flags = ["-O2", "-std=c11", "-Wall", "-Wextra", "-Werror", "-DNDEBUG",
                  "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
                  "-I", ROOT / "software/akv/include", "-I", out]
    for absent, expected in ((False, 39), (True, 1)):
        tag = "selection-no-env" if absent else "selection-env"
        binary = out / tag
        run([host, *host_flags, *(["-DQK_TEST_NO_ENV"] if absent else []),
             HERE / "qk_panel4_selection_test.c", SRC / "akv_runtime.c", "-lm", "-o", binary], tag + "-build")
        if run([binary], tag + "-run") != f"AKV_QK_PANEL4_SELECTION_PASS cases={expected}\n":
            raise ValueError("selection test exact marker/count")
    for tag, path in (("attention", assembly), ("attention-before", before_dir / assembly.name),
                      ("native", native), ("shared-runtime", monolithic)):
        run([gcc, *flags, "-c", path, "-o", out / (tag + ".o")], tag + "-build")
    run([gcc, *flags, "-nostdlib", "-static", "-Wl,-e," + SINGLE,
         out / "attention.o", "-o", out / "attention.elf"], "assembly-link")
    dis = run([objdump, "-d", out / "attention.elf"], "assembly-disassembly")
    native_dis = run([objdump, "-dr", out / "native.o"], "native-disassembly")
    run([objdump, "-dr", out / "shared-runtime.o"], "shared-runtime-disassembly")
    if PANEL not in native_dis or SINGLE not in native_dis or "getenv" not in native_dis:
        raise ValueError("production native object missing selection targets/provider")
    native_symbols = run([nm, out / "native.o"], "native-symbols")
    if not re.search(r"\bw getenv$", native_symbols, re.MULTILINE):
        raise ValueError("freestanding getenv reference is not weak")
    # Compare existing assembly symbol bodies byte-for-byte, not just source.
    symbol_maps, blobs = [], []
    for tag in ("attention-before", "attention"):
        listing = run([nm, "-S", "--defined-only", out / (tag + ".o")], tag + "-symbols")
        symbols = {}
        for line in listing.splitlines():
            fields = line.split()
            if len(fields) == 4 and fields[2] == "T":
                symbols[fields[3]] = (int(fields[0], 16), int(fields[1], 16))
        symbol_maps.append(symbols)
        blob = out / (tag + ".text.bin")
        run([objcopy, "--dump-section", ".text.akv_v2_attention=" + str(blob),
             out / (tag + ".o"), out / (tag + "-dump.o")], tag + "-dump")
        blobs.append(blob.read_bytes())
    for name, (offset, size) in symbol_maps[0].items():
        new_offset, new_size = symbol_maps[1][name]
        if size != new_size or blobs[0][offset:offset+size] != blobs[1][new_offset:new_offset+size]:
            raise ValueError("changed existing assembly symbol: " + name)
    if set(symbol_maps[1]) - set(symbol_maps[0]) != {PANEL}:
        raise ValueError("unexpected assembly exports")
    matrix = check(dis)
    after = {str(p): digest(p) for p in sorted(inputs)}
    (out / "sources-after.json").write_text(json.dumps(after, indent=2) + "\n")
    if after != pins:
        raise ValueError("source drift")
    artifacts = {str(p): digest(p) for p in sorted(out.iterdir()) if p.is_file()}
    result = dict(status="PASS", execution="HOST_ONLY_NO_NATIVE_SIMULATION",
                  helper=PANEL, selection_cases=40, unchanged_symbols=len(symbol_maps[0]),
                  matrix=matrix, sources=pins, artifacts=artifacts,
                  tools={str(p): digest(p) for p in (gcc, objdump, objcopy, nm)})
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"AKV_QK_PANEL4_BUILD_PASS output={out}")


if __name__ == "__main__":
    main()
