#!/usr/bin/env python3
"""Build a private native M4 preparation pair, extracting the production oracle.

No production edit, shared app output, RTL build or simulator launch occurs.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess

from run_half_scale_soc import ROOT, atomic_json, digest, hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--golden-run", type=Path, required=True)
    parser.add_argument("--llama", type=Path, default=Path("/home/wangwy/llama/llama.cpp"))
    parser.add_argument("--gcc", type=Path, default=Path(
        "/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc"))
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    gcc = args.gcc.resolve(strict=True)
    cxx = gcc.with_name(gcc.name.removesuffix("gcc") + "g++")
    objdump = gcc.with_name(gcc.name.removesuffix("gcc") + "objdump")
    ggml = args.llama.resolve(strict=True) / "ggml"
    source = ROOT / "verification/qbs"
    common = ROOT / "apps/common"
    capture = ROOT / "apps/llama_qwen25_q8_0_prefill_m4_direct_qbs/generated/activation_f32.bin"
    golden_run = args.golden_run.resolve(strict=True)
    golden = golden_run / "golden.bin"
    golden_report = json.loads((golden_run / "golden.json").read_text())
    if (golden_report["state"] != "PASS" or golden.stat().st_size != 3808
            or golden_report["golden_sha256"] != digest(golden)
            or golden_report["capture_sha256"] != digest(capture)
            or golden_report["initial_fcsr"] != 0 or golden_report["initial_vcsr"] != 5
            or golden_report["vcsr"] != 5 or not 0 <= golden_report["fcsr"] <= 31):
        raise ValueError("Independent Linux GGML golden does not match this capture")
    for key in ("source_pins", "log_pins", "pre_exec_artifacts"):
        if hashes(map(Path, golden_report[key])) != golden_report[key]:
            raise ValueError("Independent golden provenance drift: " + key)
    repack = ggml / "src/ggml-cpu/repack.cpp"
    helper = ROOT / "apps/llama_qwen25_q8_0_prefill_m4_direct_qbs/script/build_pair.py"
    spec = importlib.util.spec_from_file_location("paired_build", helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    common_sources = [common / name for name in
                      ("crt0.S", "printf.c", "string.c", "serial.c", "util.c", "print_trap_cause.c")]
    tool_inputs = []
    for name in ("libm.a", "libgcc.a"):
        tool_inputs.append(Path(subprocess.check_output(
            [gcc, "-print-file-name=" + name], text=True).strip()).resolve(strict=True))
    pins = hashes([Path(__file__), source / "m4_prepare_soc.cpp",
                   source / "ggml_m4_prepare_candidate.h", repack, capture, helper,
                   golden, golden_run / "golden.json",
                   *common_sources, *common.glob("*.h"), common / "arch.link.ld",
                   *ggml.rglob("*.h"), gcc, cxx, objdump, *tool_inputs])
    atomic_json(out / "manifest.json", pins)
    text = repack.read_text()
    start_marker = "\nvoid ggml_quantize_mat_q8_0_4x1_generic("
    end_marker = "\nvoid ggml_quantize_mat_q8_K_4x1_ara_generic("
    if text.count(start_marker) != 1 or text.count(end_marker) != 1:
        raise ValueError("Production function boundaries changed")
    body = text[text.index(start_marker):text.index(end_marker)]
    if not body.rstrip().endswith("}"):
        raise ValueError("Incomplete production function")
    oracle = out / "production_oracle.cpp"
    oracle.write_text('#include "ggml_m4_prepare_candidate.h"\nextern "C" {\n' + body + '\n}\n')
    data = out / "capture.S"
    if capture.stat().st_size != 14336:
        raise ValueError("Wrong capture geometry")
    data.write_text('.section .rodata\n.balign 64\n.global m4_capture\nm4_capture:\n'
                    f'.incbin "{capture}"\n.balign 64\n.global m4_golden\nm4_golden:\n'
                    f'.incbin "{golden}"\n')
    (out / "golden_state.h").write_text(f'#define M4_GOLDEN_FCSR {int(golden_report["fcsr"])}U\n')
    script = out / "link.ld"
    script.write_text((common / "arch.link.ld").read_text().replace("ALIGNMENT", "16")
                      .replace("LENGTH = 0x00100000", "LENGTH = 0x01000000"))
    flags = ["-march=rv64gcv", "-mabi=lp64d", "-mcmodel=medany", "-mno-relax", "-O3",
             "-DNDEBUG", "-fno-fast-math", "-ffunction-sections", "-fdata-sections",
             "-DNR_LANES=4", "-DVLEN=1024", "-I" + str(common),
             "-I" + str(out),
             "-I" + str(ROOT / "apps/include"), "-I" + str(source),
             "-isystem", str(ggml / "include"), "-isystem", str(ggml / "src"),
             "-isystem", str(ggml / "src/ggml-cpu")]
    commands = []

    def run(command, label):
        command = list(map(str, command))
        commands.append(command)
        atomic_json(out / "commands.json", commands)
        with (out / (label + ".log")).open("x") as log:
            subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=120)

    objects = []
    for i, path in enumerate([source / "m4_prepare_soc.cpp", oracle, data, *common_sources]):
        cpp = path.suffix == ".cpp"
        obj = out / f"{i}-{path.name}.o"
        extra = (["-std=gnu++17", "-fno-exceptions", "-fno-rtti", "-Wall", "-Wextra", "-Werror"]
                 if cpp else ["-std=gnu11"])
        if path == common / "string.c":
            extra += ["-ffreestanding", "-fno-builtin", "-fno-tree-loop-distribute-patterns"]
        run([cxx if cpp else gcc, *flags, *extra, "-c", path, "-o", obj], f"compile-{i}")
        if path == common / "string.c":
            disasm = subprocess.check_output([objdump, "-dr", obj], text=True)
            module.check_libc_calls(disasm)
        objects.append(obj)
    elf = out / "qbs_m4_prepare_soc"
    run([gcc, *flags, "-static", "-nostartfiles", "-nostdlib", *objects,
         "-Wl,--gc-sections", "-Wl,-Map=" + str(out / "link.map"),
         "-T", script, "-lm", "-lgcc", "-o", elf], "link")
    sections = module.allocated_sections(elf)
    if min(s["address"] for s in sections) < 0x80000000 or max(
            s["address"] + s["bytes"] for s in sections) > 0x81000000 - 65536:
        raise ValueError("Invalid memory layout")
    disasm = subprocess.check_output([objdump, "-d", elf], text=True)
    (out / "disassembly.txt").write_text(disasm)
    # arch-fallback.h maps the generic function to this public symbol on RVV.
    if "vsse8.v" not in disasm or "<ggml_quantize_mat_q8_0_4x1>:" not in disasm:
        raise ValueError("Missing candidate or production oracle")
    if hashes(map(Path, pins)) != pins:
        raise ValueError("Source drift")
    atomic_json(out / "build.json", dict(state="BUILT_NOT_EXECUTED", elf_sha256=digest(elf),
                oracle_sha256=digest(oracle), capture_sha256=digest(capture),
                manifest_sha256=digest(out / "manifest.json"), sections=sections,
                scope="Real M4/K896 fused production generic versus candidate, ABBA"))
    print(elf)


if __name__ == "__main__":
    main()
