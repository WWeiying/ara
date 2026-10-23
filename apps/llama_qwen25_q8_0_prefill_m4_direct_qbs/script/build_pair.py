#!/usr/bin/env python3
"""Build only the paired apps with GNU, using private objects/linker scripts.

No simulator is invoked. --l2-mb is a simulation-only link bound; the actual
SoC memory must independently match before either ELF can be run.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
APPS = ("llama_qwen25_q8_0_prefill_m4_direct_qbs", "llama_qwen25_q8_0_prefill_m4_context_qbs")


def allocated_sections(elf):
    data = elf.read_bytes()
    if data[:6] != b"\x7fELF\x02\x01":
        raise ValueError("Expected ELF64 little-endian")
    header = struct.unpack_from("<16sHHIQQQIHHHHHH", data)
    section_offset, section_stride, count, names_index = header[6], header[11], header[12], header[13]
    records = [struct.unpack_from("<IIQQQQIIQQ", data, section_offset + i * section_stride)
               for i in range(count)]
    name_record = records[names_index]
    names = data[name_record[4]:name_record[4] + name_record[5]]
    result = []
    for entry in records:
        if entry[2] & 2 and entry[5]:
            end = names.index(b"\0", entry[0])
            result.append({"name": names[entry[0]:end].decode(), "address": entry[3],
                           "bytes": entry[5], "nobits": entry[1] == 8})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gcc", type=Path,
                        default=ROOT / "install/riscv-gcc/bin/riscv64-unknown-elf-gcc")
    parser.add_argument("--build-name", default="build-gnu-m4-pair")
    parser.add_argument("--l2-mb", type=int, choices=(1, 16), default=16)
    args = parser.parse_args()
    if Path(args.build_name).name != args.build_name or args.build_name in ("", ".", ".."):
        raise ValueError("Build name must be a child directory name")
    gcc = args.gcc.resolve(strict=True)
    if "gcc" not in gcc.name or "zcc" in gcc.name:
        raise ValueError("Only the explicitly supplied GNU compiler is supported")
    version = subprocess.check_output([str(gcc), "--version"], text=True)
    flags = ["-march=rv64gcv_zfh_zvfh", "-mabi=lp64d", "-mcmodel=medany", "-mno-relax",
             "-O2", "-std=gnu11", "-fno-fast-math", "-ffp-contract=off", "-fno-tree-vectorize",
             "-fno-common", "-fno-builtin-printf", "-ffunction-sections", "-fdata-sections",
             "-fstack-usage", "-DNR_LANES=4", "-DVLEN=1024",
             "-I" + str(ROOT / "apps/common"), "-I" + str(ROOT / "apps/include"),
             "-I" + str(ROOT / "software/qbs/include")]
    for name in APPS:
        app = ROOT / "apps" / name
        out = app / args.build_name
        out.mkdir(exist_ok=False)
        commands = []

        def run(argv, label, cwd=out):
            argv = list(map(str, argv))
            commands.append({"argv": argv, "cwd": str(cwd)})
            (out / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
            with (out / (label + ".log")).open("x") as log:
                result = subprocess.run(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
            if result.returncode:
                raise RuntimeError(f"Failed {label}; see {out / (label + '.log')}")

        # Generator stdout is assembly; data and provenance stay in this app.
        run([sys.executable, app / "script/gen_data.py"], "generate", cwd=app)
        assembly = out / "data.S"
        assembly.write_bytes((out / "generate.log").read_bytes())
        linker = (ROOT / "apps/common/arch.link.ld").read_text()
        linker = linker.replace("ALIGNMENT", "16")
        if args.l2_mb != 1:
            linker = linker.replace("LENGTH = 0x00100000", "LENGTH = 0x01000000")
        script = out / "link.ld"
        script.write_text(linker)
        sources = [app / "main.c", assembly,
                   *(ROOT / "apps/common" / leaf for leaf in
                     ("crt0.S", "printf.c", "string.c", "serial.c", "util.c", "print_trap_cause.c")),
                   ROOT / "software/qbs/src/qbs_runtime.c", ROOT / "software/qbs/src/qbs_native_riscv.c"]
        objects = []
        for index, source in enumerate(sources):
            obj = out / f"{index}-{source.name}.o"
            run([gcc, *flags, "-c", source, "-o", obj], f"compile-{index}")
            objects.append(obj)
        elf = out / (name + ".elf")
        run([gcc, *flags, "-static", "-nostartfiles", "-nostdlib", *objects,
             "-Wl,--gc-sections", "-Wl,-Map=" + str(out / "link.map"),
             "-T", script, "-lm", "-lgcc", "-o", elf], "link")
        sections = allocated_sections(elf)
        low = min(section["address"] for section in sections)
        high = max(section["address"] + section["bytes"] for section in sections)
        memory_end = 0x80000000 + args.l2_mb * 1024 * 1024
        if low < 0x80000000 or high > memory_end - 65536:
            raise ValueError("ELF overlaps the conservative 64KiB stack headroom")
        report = {"app": name, "compiler": str(gcc), "compiler_version": version,
                  "elf_sha256": hashlib.sha256(elf.read_bytes()).hexdigest(),
                  "simulation_l2_mb": args.l2_mb, "alloc_sections": sections,
                  "allocated_bytes": sum(section["bytes"] for section in sections),
                  "address_low": low, "address_high_exclusive": high, "span_bytes": high - low,
                  "headroom_to_stack_top_bytes": memory_end - high,
                  "stack_reserve_check_bytes": 65536,
                  "runtime_verification": "NOT_RUN", "scope": "single_full_projection"}
        (out / "build.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
