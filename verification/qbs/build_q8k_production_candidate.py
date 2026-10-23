#!/usr/bin/env python3
"""Gate Q8_K selection in a private full GGML TU, never edit live sources."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

from run_half_scale_soc import ROOT, atomic_json, digest, hashes


def adapt_production(text, header):
    old = '''    ggml_quantize_mat_q8_K_4x1_ara_generic(x, vy, n_per_row);
}

template <int M, int N>'''
    new = '''    if (qbs_m4_prepare_enabled()) {
        q8k_production_vector_path = qbs_q8k_m4_prepare_vla_candidate::quantize(x, vy, n_per_row);
    } else {
        q8k_production_vector_path = false;
        ggml_quantize_mat_q8_K_4x1_ara_generic(x, vy, n_per_row);
    }
}

template <int M, int N>'''
    if text.count(old) != 1:
        raise ValueError("Q8_K production selection boundary drift")
    prefix = (f'#include "{header}"\n'
              'static bool q8k_production_vector_path;\n'
              'extern "C" bool q8k_production_last_vector_path() {\n'
              '    return q8k_production_vector_path;\n}\n')
    return prefix + text.replace(old, new)


def adapt_harness(text):
    include = '#include "../ggml_q8k_m4_prepare_candidate.h"'
    start = '__attribute__((noinline)) static bool candidate('
    end = '\nstatic size_t cases = '
    if text.count(include) != 1 or text.count(start) != 1 or text.count(end) != 1:
        raise ValueError("Native harness boundaries changed")
    text = text.replace(include, '''#include "ggml-impl.h"
#include "simd-mappings.h"
#include "arch-fallback.h"
#include "repack.h"
#include <cassert>
#include <climits>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
template <int64_t INTER_SIZE, ggml_type PARAM_TYPE>
void ggml_quantize_mat_t(const float * GGML_RESTRICT x,
                         void * GGML_RESTRICT y, int64_t nrow, int64_t k);
template <>
void ggml_quantize_mat_t<1, GGML_TYPE_Q8_K>(const float * GGML_RESTRICT x,
                                          void * GGML_RESTRICT y, int64_t nrow, int64_t k);
extern "C" bool q8k_production_last_vector_path();''')
    first, last = text.index(start), text.index(end)
    # The three old AVL-cap observations become repeat checks of the one
    # production MaxAVL=16 entry. They are NOT three production AVL modes.
    text = text[:first] + '''__attribute__((noinline)) static bool candidate(
    const float * x, void * y, int64_t k, size_t repeat) {
    if (repeat != 1 && repeat != 7 && repeat != 16) fail("dispatch", "invalid_repeat");
    ggml_quantize_mat_t<1, GGML_TYPE_Q8_K>(x, y, 4, k);
    return q8k_production_last_vector_path();
}
''' + text[last:]
    needle = 'int main(int argc, char ** argv) {\n'
    if text.count(needle) != 1:
        raise ValueError("Main entry changed")
    return text.replace(needle, needle +
        '    if (setenv("GGML_RISCV_QBS_M4_PREPARE", "1", 1)) return 1;\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("native-build", "native-run", "production-build", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    previous, run, production = (getattr(args, n).resolve(strict=True)
        for n in ("native_build", "native_run", "production_build"))
    accepted = json.loads((run / "status.json").read_text())
    pins = json.loads((run / "manifest.json").read_text())
    if (accepted["state"] != "PASS" or accepted["checks"] != 12000 or
            digest(run / "manifest.json") != accepted["manifest_sha256"] or
            hashes(map(Path, pins)) != pins):
        raise ValueError("Require unchanged original numerical acceptance")
    source = ROOT / "verification/qbs"
    suite = source / "ggml_q8k_m4_prepare_native"
    header = source / "ggml_q8k_m4_prepare_vla_candidate.h"
    repack = Path("/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/repack.cpp")
    compile_record = production / "production-compile.json"
    entry = json.loads(compile_record.read_text())
    command = shlex.split(entry["command"])
    if (Path(entry["file"]).resolve() != repack or
        any(f not in command for f in ("-O3", "-DNDEBUG", "-DGGML_USE_RISCV_QBS")) or
        any(f.startswith(("-flto", "-ffast-math", "-ffinite-math-only", "-march=rv64gcv_z")) for f in command)):
        raise ValueError("Unexpected production compiler/optimization policy")
    platform = Path("/home/wangwy/llama/platforms/cva6-qemu")
    tools = platform / "tools/bin"
    cxx, gcc, nm, objdump = [tools / ("riscv64-linux-" + n)
                           for n in ("g++", "gcc", "nm", "objdump")]
    if Path(command[0]).resolve() != cxx.resolve():
        raise ValueError("Compiler differs from production")
    cpio = platform / "sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio"
    libdir = production / "build/tile-support/ggml/src"
    libs = [libdir / ("lib" + n + ".a") for n in ("ggml", "ggml-cpu", "ggml-base")]
    if any(str(p) not in pins for p in libs):
        raise ValueError("Unsealed production library")
    pins.update(hashes([Path(__file__), header, source / "q8k_m4_domain_vla.h",
        suite / "native.cpp", suite / "init.c", suite / "check.py", repack,
        compile_record, run / "manifest.json", run / "status.json", cpio,
        *[p.resolve() for p in (cxx, gcc, nm, objdump)]]))
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    private = out / "repack.cpp"
    private.write_text(adapt_production(repack.read_text(), header))
    native = out / "native.cpp"
    native.write_text(adapt_harness((suite / "native.cpp").read_text()))
    for name in ("captures.txt", "captures.json", *(n + ".bin" for n in
        ("real_attn_first", "real_attn_last", "real_gate_first", "real_gate_last",
         "real_down_first", "real_down_last"))):
        if str(previous / name) not in pins:
            raise ValueError("Unpinned capture")
        (out / name).write_bytes((previous / name).read_bytes())
    commands = []
    def invoke(argv, label, cwd=ROOT):
        argv = list(map(str, argv))
        commands.append(dict(argv=argv, cwd=str(cwd)))
        atomic_json(out / "commands.json", commands)
        with (out / (label + ".log")).open("x") as stream:
            subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                           check=True, timeout=300)
        return (out / (label + ".log")).read_text()
    command[command.index("-o") + 1] = str(out / "production.o")
    command[command.index("-c") + 1] = str(private)
    invoke(command, "production-compile", Path(entry["directory"]))
    ggml = repack.parents[2]
    includes = [s for d in (ggml / "include", ggml / "src", ggml / "src/ggml-cpu")
                for s in ("-isystem", str(d))]
    invoke([cxx, "-std=c++17", "-march=rv64gcv", "-mabi=lp64d", "-O3", "-UNDEBUG",
        "-fno-fast-math", "-ffp-contract=off", "-fno-tree-vectorize", "-Wall", "-Wextra", "-Werror",
        *includes, "-c", native, "-o", out / "native.o"], "test-compile")
    symbol = "_Z19ggml_quantize_mat_tILl1EL9ggml_type15EEvPKfPvll"
    # Validate the pinned GGML enum and external-TU ownership explicitly.
    names = invoke([nm, "-C", out / "native.o"], "test-symbols-demangled")
    if ("U void ggml_quantize_mat_t<1l, (ggml_type)15>" not in names or
            "qbs_q8k_m4_prepare" in names):
        raise ValueError("Test must call, not instantiate, production Q8_K quantization")
    names = invoke([nm, out / "native.o"], "test-symbols")
    if not any(line.split() == ["U", symbol] for line in names.splitlines()):
        raise ValueError("Missing external specialization reference")
    invoke([cxx, "-march=rv64gcv", "-mabi=lp64d", "-static", out / "native.o",
        out / "production.o", *libs, "-lm", "-ldl", "-Wl,-Map=" + str(out / "native.map"),
        "-o", out / "native"], "link")
    disassembly = invoke([objdump, "-d", "--disassemble=" + symbol, out / "native"], "production-entry")
    if not all(token in disassembly for token in (
            "vle32.v", "vfmacc.vf", "vsse8.v", "frrm",
            "<ggml_quantize_mat_q8_K_4x1_ara_generic>")):
        raise ValueError("Production entry lacks candidate RVV or generic fallback")
    invoke([gcc, "-march=rv64gcv", "-mabi=lp64d", "-O2", "-static", suite / "init.c",
            "-o", out / "init"], "init")
    listing = ["dir /dev 755 0 0", "nod /dev/console 600 0 0 c 5 1",
               f"file /init {out/'init'} 755 0 0", f"file /native {out/'native'} 755 0 0",
               f"file /captures.txt {out/'captures.txt'} 444 0 0"]
    listing += [f"file /{p.name} {p} 444 0 0" for p in sorted(out.glob("real_*.bin"))]
    (out / "initramfs.list").write_text("\n".join(listing) + "\n")
    with (out / "initramfs.cpio").open("xb") as stream:
        subprocess.run([cpio, out / "initramfs.list"], stdout=stream, check=True, timeout=60)
    if hashes(map(Path, pins)) != pins:
        raise ValueError("Input drift")
    pins.update(hashes(p for p in out.iterdir() if p.is_file()))
    atomic_json(out / "manifest.json", pins)
    atomic_json(out / "build.json", dict(state="READY", execution="NOT_RUN",
        manifest_sha256=digest(out / "manifest.json"), binary_sha256=digest(out / "native"),
        scope="Private full production TU selection candidate, MaxAVL16 repeated three times per environment; live GGML unchanged"))


if __name__ == "__main__":
    main()
