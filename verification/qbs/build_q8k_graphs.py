#!/usr/bin/env python3
"""Build actual GGML graph OFF/ON checks without touching live sources."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

from run_half_scale_soc import ROOT, atomic_json, digest, hashes
from build_q8k_production_candidate import adapt_production


def graph_production(text):
    declaration = "static bool q8k_production_vector_path;"
    tail = """        ggml_quantize_mat_q8_K_4x1_ara_generic(x, vy, n_per_row);
    }
}

template <int M, int N>"""
    trace = """        ggml_quantize_mat_q8_K_4x1_ara_generic(x, vy, n_per_row);
    }
    if (qbs_m4_prepare_trace_enabled()) {
        std::fprintf(stderr, "GGML_RISCV_QBS_Q8K_M4_PREPARE enabled=%d path=%s k=%lld\\n",
                     int(qbs_m4_prepare_enabled()), q8k_production_vector_path ? "rvv" : "generic",
                     (long long) n_per_row);
    }
}

template <int M, int N>"""
    if text.count(declaration) != 1 or text.count(tail) != 1:
        raise ValueError("Production candidate observer/selection changed")
    return text.replace(declaration, "static thread_local bool q8k_production_vector_path;").replace(tail, trace)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("accepted-run", "production-build", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args()
    run, production = args.accepted_run.resolve(strict=True), args.production_build.resolve(strict=True)
    state = json.loads((run / "status.json").read_text())
    pins = json.loads((run / "manifest.json").read_text())
    if state["state"] != "PASS" or state["checks"] != 12000 or hashes(map(Path, pins)) != pins:
        raise ValueError("Require accepted private production TU")
    repack = Path("/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/repack.cpp")
    here = Path(__file__).parent
    header = here / "ggml_q8k_m4_prepare_vla_candidate.h"
    compiler = Path("/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-g++")
    gcc = compiler.with_name("riscv64-linux-gcc")
    compile_record = production / "production-compile.json"
    record = json.loads(compile_record.read_text())
    command = shlex.split(record["command"])
    if Path(command[0]).resolve() != compiler.resolve():
        raise ValueError("Production compiler differs")
    libdir = production / "build/tile-support/ggml/src"
    libs = [libdir / ("lib" + n + ".a") for n in ("ggml", "ggml-cpu", "ggml-base")]
    if any(str(path) not in pins for path in libs):
        raise ValueError("Unsealed production library")
    graph = here / "ggml_m4_prepare_production/graph.cpp"
    init = here / "q8k_graph_init.c"
    cpio = Path("/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio")
    pins.update(hashes([Path(__file__), run / "status.json", run / "manifest.json", compile_record,
        here / "build_q8k_production_candidate.py", graph, init, here / "check_q8k_graphs.py",
        here / "check_ggml_tile_context.py", here / "ggml_m4_prepare_production/check.py",
        compiler.resolve(), gcc.resolve(), cpio]))
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    private = out / "repack.cpp"
    private.write_text(graph_production(adapt_production(repack.read_text(), header)))
    commands = []
    def invoke(argv, label, cwd=ROOT):
        argv = list(map(str, argv)); commands.append(dict(argv=argv, cwd=str(cwd)))
        atomic_json(out / "commands.json", commands)
        with (out / (label + ".log")).open("x") as stream:
            subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                           check=True, timeout=300)
    command[command.index("-o") + 1] = str(out / "production.o")
    command[command.index("-c") + 1] = str(private)
    invoke(command, "production-compile", Path(record["directory"]))
    ggml = repack.parents[2]
    includes = [s for d in (ggml / "include", ggml / "src", ggml / "src/ggml-cpu")
                for s in ("-isystem", str(d))]
    invoke([compiler, "-std=c++17", "-march=rv64gcv", "-mabi=lp64d", "-O3", "-UNDEBUG",
        "-fno-fast-math", "-ffp-contract=off", "-fno-tree-vectorize", "-Wall", "-Wextra", "-Werror",
        *includes, "-I" + str(ROOT / "software/qbs/include"), "-c", graph, "-o", out / "graph.o"], "graph-compile")
    invoke([compiler, "-march=rv64gcv", "-mabi=lp64d", "-static", out / "graph.o",
        out / "production.o", *libs, "-lm", "-ldl", "-pthread",
        "-Wl,-Map=" + str(out / "graph.map"), "-o", out / "graph"], "link")
    invoke([gcc, "-march=rv64gcv", "-mabi=lp64d", "-static", "-O2", "-Wall", "-Wextra",
            "-Werror", init, "-o", out / "init"], "init")
    listing = out / "initramfs.list"
    listing.write_text("dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n" +
                       f"file /init {out/'init'} 755 0 0\nfile /graph {out/'graph'} 755 0 0\n")
    with (out / "initramfs.cpio").open("xb") as stream:
        subprocess.run([cpio, listing], stdout=stream, check=True, timeout=60)
    if hashes(map(Path, pins)) != pins:
        raise ValueError("Input drift")
    pins.update(hashes(path for path in out.iterdir() if path.is_file()))
    atomic_json(out / "manifest.json", pins)
    atomic_json(out / "build.json", dict(state="READY", execution="NOT_RUN",
        manifest_sha256=digest(out / "manifest.json"),
        scope="Private GGML Q8_K and Q8_0 preparation OFF/ON with shared graph oracle"))


if __name__ == "__main__":
    main()
