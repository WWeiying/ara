#!/usr/bin/env python3
"""Build the success-only SoC probe with GNU; NEVER launch a simulator.

All generated objects, link script and receipts live in a fresh child directory.
The linked image requires VLEN1024, AKV-v2, and the selected L2 size. Default:
  python3 verification/akv/refill_overlap_probe/build.py --build-name build-gnu-01

Parent runner: +AKV_PERF +AKV_SUMMARY, normal integrated protocol/AXI checks,
Core Test *** SUCCESS, exactly two mode PASS lines and one SUITE_PASS line.
The EXPECT line is a software expectation, NOT a hardware-counter observation.
Per mode command order: V2_FULL, 7 LOAD, V2_REFILL, 17 LOAD, RELEASE.
Old tile checks Q0, K/V tokens 0,31,63; new tail checks Q0 and all eight K/V rows.
FULL: q=256, kv=32768, read_ranges=130, read_payload_bytes=33088.
REFILL: q=0, kv=4096, read_ranges=16, read_payload_bytes=4096.
Each LOAD: load=1, v2_row_load=1, replay=256, external/read_ranges=0.
RELEASE: no payload/replay; context_ready=0. All 54 terminals success, fault=0;
no legacy FULL/REFILL, column commands, rejected commands or bank conflicts.
Do not use the old handoff checker's unrelated 10-command expectation.
Cycle markers include issue/drain overhead; backend trace is required to infer
an overlap window. This build receipt is not functional or performance proof.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import struct
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def alloc_sections(path):
    data = path.read_bytes()
    if data[:6] != b"\x7fELF\x02\x01":
        raise ValueError("Expected little-endian ELF64")
    header = struct.unpack_from("<16sHHIQQQIHHHHHH", data)
    records = [struct.unpack_from("<IIQQQQIIQQ", data,
                                 header[6] + i * header[11])
               for i in range(header[12])]
    names_section = records[header[13]]
    names = data[names_section[4]:names_section[4] + names_section[5]]
    return [{"name": names[s[0]:names.index(b"\0", s[0])].decode(),
             "address": s[3], "bytes": s[5], "nobits": s[1] == 8}
            for s in records if s[2] & 2 and s[5]]


def check_libc(disassembly):
    current = None
    seen = set()
    for line in disassembly.splitlines():
        label = re.match(r"^\s*[0-9a-f]+ <([^>]+)>:$", line)
        if label:
            current = label[1]
            seen.add(current)
        call = re.search(r"R_RISCV_(?:CALL_PLT|CALL|JAL)\s+(\w+)(?:\s|$|[+-])", line)
        if current in ("memcpy", "memset") and call and call[1] == current:
            raise ValueError("Recursive bare-metal libc: " + current)
    if not {"memcpy", "memset"} <= seen:
        raise ValueError("Missing memcpy/memset object bodies")


def check_windows(disassembly, symbols):
    instructions = {}
    for line in disassembly.splitlines():
        match = re.match(r"\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(.+)$", line)
        if match:
            instructions[int(match[1], 16)] = (int(match[2], 16), match[3])
    markers = {}
    for mode, gap in (("immediate", 4), ("serial", 8)):
        prefix = "probe_" + mode
        points = {name: symbols[prefix + "_" + name] for name in
                  ("start", "fma_first", "fma_last", "refill", "returned", "drained")}
        if not (points["fma_first"] == points["start"] + 4 and
                points["fma_last"] == points["fma_first"] + 15 * 4 and
                points["refill"] == points["fma_last"] + gap and
                points["returned"] == points["refill"] + 4 and
                points["drained"] == points["returned"] + 8):
            raise ValueError("Unexpected timing-window layout: " + mode)
        for pc in range(points["fma_first"], points["fma_last"] + 4, 4):
            if not re.fullmatch(r"vfmacc\.vv\s+v8,v16,v20", instructions[pc][1].strip()):
                raise ValueError("FMA window contains another instruction")
        if instructions[points["refill"]][0] != 0x02A0605B:
            raise ValueError("Incorrect REFILL opcode")
        if mode == "serial" and not re.fullmatch(
                r"vsetvli\s+zero,t0,e16,m1,ta,ma",
                instructions[points["refill"] - 4][1].strip()):
            raise ValueError("Serial drain missing")
        for name in ("start", "returned", "drained"):
            if not instructions[points[name]][1].startswith("rdcycle"):
                raise ValueError("Cycle marker missing: " + name)
        markers[mode] = points
    expected_custom = {0x0005455B: 1, 0x00B5605B: 1, 0x0000505B: 1,
                       0x0205345B: 1, 0x02A0605B: 2}
    actual_custom = {}
    for opcode, _ in instructions.values():
        if opcode & 0x7F == 0x5B:
            actual_custom[opcode] = actual_custom.get(opcode, 0) + 1
    if actual_custom != expected_custom:
        raise ValueError("Unexpected linked custom instructions: " + str(actual_custom))
    return markers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gcc", type=Path, default=Path(
        "/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc"))
    parser.add_argument("--build-name", default="build-gnu-01")
    parser.add_argument("--l2-mb", type=int, choices=(1, 16), default=16)
    args = parser.parse_args()
    if Path(args.build_name).name != args.build_name or args.build_name in ("", ".", ".."):
        raise ValueError("Build name must be a fresh child directory name")
    gcc = args.gcc.resolve(strict=True)
    if not gcc.name.endswith("gcc") or "zcc" in str(gcc).lower():
        raise ValueError("GNU GCC only")
    objdump = gcc.with_name(gcc.name.removesuffix("gcc") + "objdump").resolve(strict=True)
    nm = gcc.with_name(gcc.name.removesuffix("gcc") + "nm").resolve(strict=True)
    out = HERE / args.build_name
    out.mkdir(exist_ok=False)
    commands = []

    def run(argv, label):
        argv = list(map(str, argv))
        commands.append({"argv": argv, "cwd": str(out)})
        (out / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        with (out / (label + ".log")).open("x") as log:
            subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=120)
        return (out / (label + ".log")).read_text()

    version = run([gcc, "--version"], "compiler-version")
    flags = ["-march=rv64gcv", "-mabi=lp64d", "-mcmodel=medany", "-mno-relax",
             "-O2", "-std=gnu11", "-fno-fast-math", "-ffp-contract=off",
             "-fno-tree-vectorize", "-ffreestanding", "-fno-builtin",
             "-fno-tree-loop-distribute-patterns", "-fno-common",
             "-ffunction-sections", "-fdata-sections", "-fstack-usage",
             "-DNR_LANES=4", "-DVLEN=1024", "-I" + str(ROOT / "apps/common"),
             "-I" + str(ROOT / "apps/include"),
             "-I" + str(ROOT / "software/akv/include/akv")]
    sources = [HERE / "main.c", HERE / "probe.S", *(ROOT / "apps/common" / name
               for name in ("crt0.S", "printf.c", "string.c", "serial.c",
                            "util.c", "print_trap_cause.c"))]
    inputs = {Path(__file__).resolve(), ROOT / "apps/common/arch.link.ld"}
    # Get exact transitive input files BEFORE compilation; do not repin drift.
    for i, source in enumerate(sources):
        depfile = out / f"{i}.d"
        run([gcc, *flags, "-M", "-MF", depfile, "-MT", "probe", source], f"deps-{i}")
        dependencies = depfile.read_text().replace("\\\n", " ").split(":", 1)[1]
        inputs.update(Path(p).resolve(strict=True) for p in shlex.split(dependencies))
    before = {str(p): digest(p) for p in sorted(inputs)}
    (out / "inputs-before.json").write_text(json.dumps(before, indent=2) + "\n")
    linker = (ROOT / "apps/common/arch.link.ld").read_text()
    if linker.count("LENGTH = 0x00100000") != 1:
        raise ValueError("Unexpected common linker template")
    linker = linker.replace("ALIGNMENT", "16").replace(
        "LENGTH = 0x00100000", f"LENGTH = 0x{args.l2_mb * 1024 * 1024:08x}")
    script = out / "link.ld"
    script.write_text(linker)
    objects = []
    for i, source in enumerate(sources):
        obj = out / f"{i}-{source.name}.o"
        extra = ["-Wall", "-Wextra", "-Werror"] if source.parent == HERE else []
        run([gcc, *flags, *extra, "-c", source, "-o", obj], f"compile-{i}")
        if source.name == "string.c":
            check_libc(run([objdump, "-dr", obj], "libc-disassembly"))
        objects.append(obj)
    elf = out / "akv_refill_overlap_probe.elf"
    run([gcc, *flags, "-static", "-nostartfiles", "-nostdlib", *objects,
         "-Wl,--gc-sections", "-Wl,-Map=" + str(out / "link.map"),
         "-T", script, "-lm", "-lgcc", "-o", elf], "link")
    symbols = {}
    for line in run([nm, "-n", elf], "symbols").splitlines():
        fields = line.split()
        if len(fields) == 3:
            symbols[fields[2]] = int(fields[0], 16)
    markers = check_windows(run([objdump, "-d", elf], "disassembly"), symbols)
    sections = alloc_sections(elf)
    low = min(s["address"] for s in sections)
    high = max(s["address"] + s["bytes"] for s in sections)
    memory_end = 0x80000000 + args.l2_mb * 1024 * 1024
    if low < 0x80000000 or high > memory_end - 65536:
        raise ValueError("ELF violates L2 bound / 64 KiB stack reserve")
    after = {str(p): digest(p) for p in sorted(inputs)}
    (out / "inputs-after.json").write_text(json.dumps(after, indent=2) + "\n")
    if before != after:
        raise ValueError("Build input changed; reject ELF")
    report = {"elf": str(elf), "elf_sha256": digest(elf), "compiler": str(gcc),
              "compiler_sha256": digest(gcc), "compiler_version": version,
              "simulation_l2_mb": args.l2_mb, "required_vlen": 1024,
              "alloc_sections": sections, "address_low": low,
              "address_high_exclusive": high, "span_bytes": high - low,
              "allocated_bytes": sum(s["bytes"] for s in sections),
              "headroom_to_stack_top_bytes": memory_end - high,
              "stack_reserve_bytes": 65536, "marker_pcs": markers,
              "input_hashes": before, "runtime_verification": "NOT_RUN",
              "disassembly_checks": "PASS", "expected_akv_commands": 54}
    (out / "build.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: report[k] for k in ("elf", "elf_sha256", "span_bytes",
                     "address_high_exclusive", "runtime_verification",
                     "disassembly_checks", "expected_akv_commands")}, sort_keys=True))


if __name__ == "__main__":
    main()
