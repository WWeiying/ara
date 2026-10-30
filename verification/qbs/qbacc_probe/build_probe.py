#!/usr/bin/env python3
"""Build and inspect a GNU-only QBACC SoC probe; never launch simulation."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
HELPER = ROOT / "verification/akv/refill_overlap_probe/build.py"
sys.path.insert(0, str(HELPER.parent))
from build import alloc_sections, check_libc


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gcc", type=Path, default=Path(
        "/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc"))
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    gcc = args.gcc.resolve(strict=True)
    if not gcc.name.endswith("gcc") or "zcc" in str(gcc).lower():
        raise ValueError("GNU GCC required")
    prefix = gcc.name.removesuffix("gcc")
    objdump = gcc.with_name(prefix + "objdump").resolve(strict=True)
    nm = gcc.with_name(prefix + "nm").resolve(strict=True)
    commands = []

    def run(argv, name):
        argv = list(map(str, argv))
        commands.append(argv)
        (out / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        with (out / (name + ".log")).open("x") as stream:
            subprocess.run(argv, cwd=out, stdout=stream, stderr=subprocess.STDOUT,
                           check=True, timeout=120)
        return (out / (name + ".log")).read_text()

    version = run([gcc, "--version"], "compiler-version")
    flags = ["-march=rv64gcv", "-mabi=lp64d", "-mcmodel=medany", "-mno-relax",
             "-O2", "-std=gnu11", "-fno-fast-math", "-ffp-contract=off",
             "-fno-tree-vectorize", "-ffreestanding", "-fno-builtin",
             "-fno-tree-loop-distribute-patterns", "-fno-common",
             "-ffunction-sections", "-fdata-sections", "-fstack-usage",
             "-DNR_LANES=4", "-DVLEN=1024", "-I" + str(ROOT / "apps/common"),
             "-I" + str(ROOT / "apps/include")]
    sources = [HERE / "main.c", HERE / "probe.S", *(ROOT / "apps/common" / name
        for name in ("crt0.S", "printf.c", "string.c", "serial.c", "util.c",
                     "print_trap_cause.c"))]
    inputs = {Path(__file__).resolve(), HELPER, ROOT / "apps/common/arch.link.ld"}
    for i, source in enumerate(sources):
        dep = out / f"{i}.d"
        run([gcc, *flags, "-M", "-MF", dep, "-MT", "probe", source], f"deps-{i}")
        deps = dep.read_text().replace("\\\n", " ").split(":", 1)[1]
        inputs.update(Path(p).resolve(strict=True) for p in shlex.split(deps))
    pins = {str(p): digest(p) for p in sorted(inputs)}
    (out / "inputs-before.json").write_text(json.dumps(pins, indent=2) + "\n")
    linker = (ROOT / "apps/common/arch.link.ld").read_text()
    if linker.count("LENGTH = 0x00100000") != 1:
        raise ValueError("Unexpected linker template")
    script = out / "link.ld"
    script.write_text(linker.replace("ALIGNMENT", "16").replace(
        "LENGTH = 0x00100000", "LENGTH = 0x01000000"))
    objects = []
    for i, source in enumerate(sources):
        obj = out / f"{i}-{source.name}.o"
        warnings = ["-Wall", "-Wextra", "-Werror"] if source.parent == HERE else []
        run([gcc, *flags, *warnings, "-c", source, "-o", obj], f"compile-{i}")
        if source.name == "string.c":
            check_libc(run([objdump, "-dr", obj], "libc-disassembly"))
        objects.append(obj)
    elf = out / "qbacc_soc_probe.elf"
    run([gcc, *flags, "-static", "-nostartfiles", "-nostdlib", *objects,
         "-Wl,--gc-sections", "-Wl,-Map=" + str(out / "link.map"),
         "-T", script, "-lm", "-lgcc", "-o", elf], "link")
    symbols = {}
    for line in run([nm, "-n", elf], "symbols").splitlines():
        fields = line.split()
        if len(fields) == 3:
            symbols[fields[2]] = int(fields[0], 16)
    if symbols["mtvec_handler"] & 3:
        raise ValueError("Unaligned direct-mode mtvec")
    disasm = run([objdump, "-d", elf], "disassembly")
    instructions = {}
    for line in disasm.splitlines():
        match = re.match(r"\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(.+)$", line)
        if match:
            instructions[int(match[1], 16)] = (int(match[2], 16), match[3])
    probe_pcs = {}
    for m in (1, 3, 4, 5, 8):
        opcode = ((m - 1 + 8) << 25) | (11 << 20) | (10 << 15) | (8 << 7) | 0x5b
        for width in (8, 32):
            name = f"qbacc_m{m}_e{width}"
            start = symbols[name]
            end = min(address for address in symbols.values() if address > start)
            points = [pc for pc, (word, _) in instructions.items()
                      if start <= pc < end and word & 0x7f == 0x5b]
            if len(points) != 1 or instructions[points[0]][0] != opcode:
                raise ValueError("Incorrect QBACC body: " + name)
            probe_pcs[name] = points[0]
    sections = alloc_sections(elf)
    low = min(s["address"] for s in sections)
    high = max(s["address"] + s["bytes"] for s in sections)
    if low < 0x80000000 or high > 0x81000000 - 65536:
        raise ValueError("ELF exceeds 16 MiB L2 / stack reserve")
    if pins != {str(p): digest(p) for p in sorted(inputs)}:
        raise ValueError("Source changed during build")
    report = dict(elf=str(elf), elf_sha256=digest(elf), compiler=str(gcc),
        compiler_sha256=digest(gcc), compiler_version=version, input_hashes=pins,
        simulation_l2_mb=16, required_vlen=1024, required_lanes=4,
        required_feature="ARA_QBS_VRF_CONTINUATION=1", probe_pcs=probe_pcs,
        handler_pc=symbols["mtvec_handler"], address_high_exclusive=high,
        allocated_bytes=sum(s["bytes"] for s in sections),
        disassembly_checks="PASS", runtime_verification="NOT_RUN")
    (out / "build.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: report[k] for k in ("elf", "elf_sha256", "allocated_bytes",
                     "disassembly_checks", "runtime_verification")}))


if __name__ == "__main__":
    main()
