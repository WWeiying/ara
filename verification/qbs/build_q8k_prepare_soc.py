#!/usr/bin/env python3
"""Build a real M4/K1536 preparation ABBA pair without changing RTL."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
from run_half_scale_soc import ROOT, atomic_json, digest, hashes


def extract(text, start, end):
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError("Production boundaries changed")
    body = text[text.index(start):text.index(end)]
    if not body.rstrip().endswith("}"):
        raise ValueError("Incomplete production function")
    return body


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--golden-run", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    golden_run = a.golden_run.resolve(strict=True)
    report = json.loads((golden_run/"golden.json").read_text())
    prior = json.loads((golden_run/"manifest.json").read_text())
    golden, capture = golden_run/"golden.bin", Path(report["capture"])
    if (report["state"] != "PASS" or report["k"] != 1536 or report["m"] != 4 or report["bytes"] != 7008
        or not 0 <= report["fcsr"] <= 31 or report["vcsr"] != 5
        or digest(golden) != report["golden_sha256"] or digest(capture) != report["capture_sha256"]
        or digest(golden_run/"qemu.log") != report["log_sha256"]
        or digest(golden_run/"manifest.json") != report["manifest_sha256"]
        or hashes(map(Path, prior)) != prior or hashes(map(Path, report["artifacts"])) != report["artifacts"]):
        raise ValueError("Independent golden/provenance mismatch")
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source, common = ROOT/"verification/qbs", ROOT/"apps/common"
    ggml = Path("/home/wangwy/llama/llama.cpp/ggml")
    repack = ggml/"src/ggml-cpu/repack.cpp"
    gcc = Path("/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc")
    cxx = gcc.with_name("riscv64-unknown-elf-g++")
    objdump = gcc.with_name("riscv64-unknown-elf-objdump")
    helper = ROOT/"apps/llama_qwen25_q8_0_prefill_m4_direct_qbs/script/build_pair.py"
    spec = importlib.util.spec_from_file_location("pair", helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    startup = [common/n for n in ("crt0.S", "printf.c", "string.c", "serial.c", "util.c", "print_trap_cause.c")]
    pins = dict(prior)
    pins.update(hashes([Path(__file__), source/"q8k_prepare_soc.cpp", source/"ggml_q8k_m4_prepare_candidate.h",
                       golden_run/"golden.json", golden_run/"manifest.json", golden_run/"qemu.log",
                       golden, capture, repack, helper, gcc.resolve(), cxx.resolve(), objdump.resolve(),
                       *startup, *common.glob("*.h"), common/"arch.link.ld", *ggml.rglob("*.h")]))
    atomic_json(out/"manifest.json", pins)
    text = repack.read_text()
    nearest = extract(text, "static inline int nearest_int(", "\n// Functions to create")
    generic = extract(text, "\nvoid ggml_quantize_mat_q8_K_4x1_ara_generic(", "\nvoid ggml_quantize_mat_q8_0_4x4_generic(")
    oracle = out/"oracle.cpp"
    oracle.write_text('#include "ggml_q8k_m4_prepare_candidate.h"\n'+nearest+'\nextern "C" {\n'+generic+'\n}\n')
    data = out/"capture.S"
    data.write_text(f'.section .rodata\n.balign 64\n.global q8k_capture\nq8k_capture:\n.incbin "{capture}"\n.balign 64\n.global q8k_golden\nq8k_golden:\n.incbin "{golden}"\n')
    (out/"golden_state.h").write_text(f'#define Q8K_GOLDEN_FCSR {report["fcsr"]}U\n')
    link = out/"link.ld"
    link.write_text((common/"arch.link.ld").read_text().replace("ALIGNMENT", "16").replace("LENGTH = 0x00100000", "LENGTH = 0x01000000"))
    flags = ["-march=rv64gcv", "-mabi=lp64d", "-mcmodel=medany", "-mno-relax", "-O3", "-DNDEBUG",
             "-fno-fast-math", "-ffunction-sections", "-fdata-sections", "-DNR_LANES=4", "-DVLEN=1024",
             *["-I"+str(d) for d in (common, out, ROOT/"apps/include", source)],
             *[s for d in (ggml/"include", ggml/"src", ggml/"src/ggml-cpu") for s in ("-isystem", str(d))]]
    commands, objects = [], []
    def run(cmd, label):
        cmd = list(map(str, cmd)); commands.append(cmd)
        atomic_json(out/"commands.json", commands)
        with (out/(label+".log")).open("x") as stream:
            subprocess.run(cmd, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=120)
    for i, path in enumerate([source/"q8k_prepare_soc.cpp", oracle, data, *startup]):
        cpp = path.suffix == ".cpp"
        obj = out/f"{i}.o"
        extra = ["-std=gnu++17", "-fno-exceptions", "-fno-rtti"] if cpp else ["-std=gnu11"]
        if path == common/"string.c": extra += ["-ffreestanding", "-fno-builtin", "-fno-tree-loop-distribute-patterns"]
        run([cxx if cpp else gcc, *flags, *extra, "-c", path, "-o", obj], f"compile-{i}")
        if path == common/"string.c": module.check_libc_calls(subprocess.check_output([objdump,"-dr",obj],text=True))
        objects.append(obj)
    elf = out/"qbs_q8k_prepare_soc"
    run([gcc,*flags,"-static","-nostartfiles","-nostdlib",*objects,"-Wl,--gc-sections","-Wl,-Map="+str(out/"link.map"),"-T",link,"-lm","-lgcc","-o",elf],"link")
    sections = module.allocated_sections(elf)
    if min(s["address"] for s in sections)<0x80000000 or max(s["address"]+s["bytes"] for s in sections)>0x81000000-65536:
        raise ValueError("ELF address range")
    disasm = subprocess.check_output([objdump,"-d",elf],text=True)
    (out/"disassembly.txt").write_text(disasm)
    oracle_disasm = subprocess.check_output([objdump,"-d","--disassemble=ggml_quantize_mat_q8_K_4x1_ara_generic",elf],text=True)
    (out/"oracle.disasm").write_text(oracle_disasm)
    if "fmadd.s" not in oracle_disasm or "vsse8.v" not in disasm:
        raise ValueError("Missing fused reference or vector candidate")
    if hashes(map(Path,pins)) != pins: raise ValueError("Source drift")
    atomic_json(out/"build.json",dict(state="BUILT_NOT_EXECUTED",elf_sha256=digest(elf),manifest_sha256=digest(out/"manifest.json"),golden_sha256=digest(golden),sections=sections))


if __name__ == "__main__":
    main()
