#!/usr/bin/env python3
"""Derive bounded slide-index stimuli; never rewrite the frozen source in place.

This is deliberately not a general assembler/dataflow engine. It accepts the
specific riscv-dv slide initializer with fractional data LMUL, and fails closed
on unrecognized code. Only destructive scalar-source instrumentation inside
proven index rotations is deleted. Random operations and fault handlers remain.
"""
from __future__ import annotations

import argparse
import difflib
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
ISA = "rv64gcv_zvfh_zvl1024b"
INDEXED = re.compile(r"v[ls][ou]x(?:seg([2-8]))?ei(8|16|32|64)\.v (v\d+), \((\w+)\), (v\d+)(?:, v0\.t)?$")
CONFIG = re.compile(r"vsetvli (\w+), (\w+), e(8|16|32|64), (m[f]?[1248]), tu, mu$")
GAP_OPS = {"li", "csrrw", "vnmsub.vx", "vmsgtu.vi", "srlw", "vnsra.wv",
           "vredmaxu.vs", "vmerge.vim", "vsub.vx", "vrgather.vi", "c.andi",
           "vmand.mm", "vsext.vf2"}
GPRS = "zero ra sp gp tp t0 t1 t2 s0 s1 a0 a1 a2 a3 a4 a5 a6 a7 s2 s3 s4 s5 s6 s7 s8 s9 s10 s11 t3 t4 t5 t6".split()


def register(name):
    return f"x{GPRS.index(name)}" if name in GPRS else name


def require(condition, message):
    if not condition:
        raise ValueError(message)


def instruction(line):
    text = line.split("#", 1)[0].strip()
    if ":" in text:
        text = text.split(":", 1)[1].strip()
    return re.sub(r"\s+", " ", text)


def multiplier(text):
    return Fraction(1, int(text[2:])) if text.startswith("mf") else Fraction(int(text[1:]))


def region_sizes(lines):
    sizes = {}
    current = None
    for line in lines:
        text = line.strip()
        if re.fullmatch(r"region_\d+:", text):
            current = text[:-1]
            sizes[current] = 0
        elif current and text == f"__ara_{current}_end:":
            current = None
        elif current:
            match = re.fullmatch(r"\.(byte|half|word|dword)\s+([^#]+)(?:#.*)?", text)
            if text and not text.startswith("#"):
                require(match, f"unsupported region data: {text}")
                sizes[current] += {"byte": 1, "half": 2, "word": 4, "dword": 8}[match[1]] * len(match[2].split(","))
    require(current is None, "unterminated region")
    return sizes


def repair(source):
    lines = source.splitlines(keepends=True)
    ops = [instruction(line) for line in lines]
    sizes = region_sizes(lines)
    deletions = set()
    reports = []
    for access, text in enumerate(ops):
        mem = INDEXED.fullmatch(text)
        if not mem:
            continue
        nf, eew, _, base, index = mem.groups()
        nf, eew = int(nf or 1), int(eew)
        starts = [i for i in range(access) if "#start riscv_vector_load_store_instr_stream_" in lines[i]]
        require(starts, f"no initializer before line {access + 1}")
        start = starts[-1]
        require(not any(":" in line.split("#", 1)[0] for line in lines[start + 1:access + 1]),
                "label inside initializer/access window")
        cfg = CONFIG.fullmatch(ops[start])
        require(cfg and cfg[2] == "zero" and int(cfg[3]) == eew, "unrecognized index configuration")
        scalar = cfg[1]
        n = 1024 // eew * multiplier(cfg[4])
        require(n.denominator == 1 and multiplier(cfg[4]) <= 1, "multi-register index initializer unsupported")
        n = int(n)
        slide = f"vslide1down.vx {index}, {index}, {scalar}"
        cursor = start + 1
        offsets = []
        while cursor + 1 < access and ops[cursor + 1] == slide:
            literal = re.fullmatch(rf"li {scalar}, (0x[0-9a-f]+|[0-9]+)", ops[cursor])
            require(literal, "unrecognized literal index")
            offsets.append(int(literal[1], 0))
            cursor += 2
        require(0 < len(offsets) < n, "expected partial literal initializer followed by rotations")
        blocks = []
        while cursor < access and "# ARA_DSA_DEFINED_SCALAR_SOURCE_" in lines[cursor]:
            begin = cursor
            stack = re.fullmatch(r"addi (x\d+), \1, -16", ops[cursor + 1])
            require(stack, "unrecognized instrumentation stack")
            stack = stack[1]
            scratch = re.fullmatch(rf"sd (x\d+), 0\({stack}\)", ops[cursor + 2])
            require(scratch, "unrecognized instrumentation scratch")
            scratch = scratch[1]
            expected = [f"addi {stack}, {stack}, -16", f"sd {scratch}, 0({stack})",
                        f"csrr {scratch}, vstart", f"sd {scratch}, 8({stack})",
                        "csrw vstart, zero", f"la {scratch}, __ara_defined_scalar_source",
                        f"vl1re8.v {index}, ({scratch})", f"ld {scratch}, 8({stack})",
                        f"csrw vstart, {scratch}", f"ld {scratch}, 0({stack})",
                        f"addi {stack}, {stack}, 16"]
            require(ops[cursor + 1:cursor + 12] == expected, "instrumentation changed; review required")
            require(ops[cursor + 12:cursor + 14] == [f"vmv.x.s {scalar}, {index}", slide],
                    "instrumentation does not guard an index rotation")
            blocks.append({"first_line": begin + 1, "last_line": begin + 12})
            deletions.update(range(begin, begin + 12))
            cursor += 14
        require(len(offsets) + len(blocks) == n, "initializer does not cover exactly VLMAX slots")
        require(ops[cursor] in (f"li {scalar}, {len(offsets)}", f"li {scalar}, {hex(len(offsets))}"),
                "final VL differs from literal offset count")
        data_cfg = CONFIG.fullmatch(ops[cursor + 1])
        require(data_cfg and data_cfg[2] == scalar and multiplier(data_cfg[4]) <= Fraction(1, 2),
                "unsupported data configuration")
        sew = int(data_cfg[3])
        require(multiplier(data_cfg[4]) * eew / sew == multiplier(cfg[4]), "index EMUL mismatch")
        require(len(offsets) <= 1024 // sew * multiplier(data_cfg[4]), "VL exceeds data VLMAX")
        base_offset = None
        region = None
        for pos in range(cursor + 2, access):
            op = ops[pos]
            if not op:
                continue
            addr = re.fullmatch(rf"la {base}, (region_\d+)\+([0-9]+)", op)
            if addr:
                region, base_offset = addr[1], int(addr[2])
                continue
            require(op.split()[0] in GAP_OPS, f"unsupported initializer gap operation: {op}")
            destination = op.split(" ", 1)[1].split(",")[0] if " " in op else ""
            require(register(destination) not in {index, register(base)}, f"reserved index/base overwritten: {op}")
            # Fractional data LMUL <= 1/2 limits ordinary/widening destinations
            # to one register. Whole-register moves and memory ops need review.
            if op.startswith("csrrw"):
                require(re.fullmatch(r"csrrw \w+, vstart, \w+", op), "unexpected CSR writer")
        require(region in sizes and base_offset is not None, "missing known memory base")
        require(all(0 <= value < (1 << eew) and value % (sew // 8) == 0 for value in offsets),
                "unaligned or truncated offset")
        end = base_offset + max(offsets) + nf * (sew // 8)
        require(end <= sizes[region], "literal indices (including segment footprint) exceed region")
        reports.append({"access_line": access + 1, "instruction": text, "index_register": index,
                        "index_eew": eew, "vl": len(offsets), "index_vlmax": n,
                        "offsets": offsets, "region": region, "region_bytes": sizes[region],
                        "base_offset": base_offset, "max_access_end_exclusive": end,
                        "removed_blocks": blocks})
    require(reports and deletions, "no proven destructive index instrumentation found")
    return "".join(line for i, line in enumerate(lines) if i not in deletions), reports


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def run(command, output, name, timeout):
    save(output / f"{name}.command.json", {"command": command, "cwd": str(output), "timeout_s": timeout})
    start = time.monotonic()
    with (output / f"{name}.log").open("wb") as log:
        try:
            result = subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
            return {"returncode": result.returncode, "timeout": False, "elapsed_s": time.monotonic() - start}
        except subprocess.TimeoutExpired:
            return {"returncode": None, "timeout": True, "elapsed_s": time.monotonic() - start}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--build-spike", action="store_true")
    parser.add_argument("--spike", type=Path, default=Path("/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike"))
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    text = source.read_text()
    derived, accesses = repair(text)
    original_elf = source.with_suffix(".o")
    require(original_elf.is_file(), "frozen original ELF missing")
    inputs = {str(path): sha(path) for path in (source, original_elf, Path(__file__).resolve())}
    output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(source, output / "original.S")
    shutil.copy2(original_elf, output / "original.elf")
    (output / "derived.S").write_text(derived)
    (output / "repair.diff").write_text("".join(difflib.unified_diff(text.splitlines(True), derived.splitlines(True),
                                                                           fromfile="original.S", tofile="derived.S")))
    manifest = {"status": "DERIVED_NOT_RUN", "classification": "NEW_STIMULUS_NOT_ORIGINAL_PASS",
                "original_failure_preserved": True, "input_hashes": inputs, "accesses": accesses,
                "derived_source_sha256": sha(output / "derived.S"), "isa": ISA,
                "change": "delete only destructive scalar-source instrumentation inside proven index rotations"}
    save(output / "manifest.json", manifest)
    if args.build_spike:
        clang = (ROOT / "install/riscv-llvm/bin/clang").resolve()
        support = ROOT / "verification/tools/riscv-dv-rvv1"
        build_inputs = [support / "scripts/link.ld", *(support / "user_extension").glob("*")]
        build_inputs = [p for p in build_inputs if p.is_file()]
        frozen = output / "build_inputs"
        frozen.mkdir()
        for path in build_inputs:
            inputs[str(path)] = sha(path)
            shutil.copy2(path, frozen / path.name)
        inputs[str(clang)] = sha(clang)
        inputs[str(args.spike.resolve())] = sha(args.spike.resolve())
        command = [str(clang), "--target=riscv64", "-fuse-ld=lld", "-march=rv64gcv_zfh_zvfh", "-mabi=lp64",
                   "-static", "-mcmodel=medany", "-fvisibility=hidden", "-nostdlib", "-nostartfiles",
                   "-I", str(frozen), "-Wl,-T," + str(frozen / "link.ld"),
                   str(output / "derived.S"), "-o", str(output / "derived.elf")]
        manifest["build"] = run(command, output, "build", 60)
        if manifest["build"]["returncode"] == 0:
            manifest["derived_elf_sha256"] = sha(output / "derived.elf")
            # No original Spike logs are read; new bounded logs contain exceptions
            # and instruction addresses, not full vector register commit payloads.
            command = [str(args.spike.resolve()), f"--isa={ISA}", "-m0x80000000:0x200000",
                       "-l", "--instructions=200000",
                       "--log=" + str(output / "spike.trace"), str(output / "derived.elf")]
            result = run(command, output, "spike", 60)
            manifest["spike"] = result
            trace = (output / "spike.trace").read_text() if (output / "spike.trace").exists() else ""
            faults = [line for line in trace.splitlines() if re.search(r"trap_.*(?:access_fault|page_fault|misaligned)", line)]
            manifest["spike_memory_faults"] = faults[:20]
            exceptions = re.findall(r"exception (trap_\w+), epc (0x[0-9a-f]+)", trace)
            manifest["spike_exceptions"] = exceptions
            # Spike's instruction budget also returns zero; require the program's
            # explicit tohost exit store in addition to rc=0 (resolved below).
            nm = (ROOT / "install/riscv-llvm/bin/llvm-nm").resolve()
            symbols = subprocess.check_output([str(nm), "-n", str(output / "derived.elf")], text=True)
            exit_symbol = re.search(r"^([0-9a-f]+) \w write_tohost$", symbols, re.M)
            exit_reached = bool(exit_symbol and re.search(rf"0x{int(exit_symbol[1], 16):016x}\b", trace))
            manifest["spike_exit_label_reached"] = exit_reached
            records = re.findall(r"core\s+0: (0x[0-9a-f]+) \(0x[0-9a-f]+\)\s+(\S+)", trace)
            manifest["spike_instruction_records"] = len(records)
            # These bounded, branch-free main programs finish far below the
            # instruction cap. Do not mistake Spike's cap exit(0) for success.
            required = [entry["instruction"].split()[0] for entry in accesses]
            observed = [(pc, mnemonic) for pc, mnemonic in records if mnemonic in required]
            indexed_pcs = {pc for pc, _ in observed}
            indexed_ok = sorted(required) == sorted(mnemonic for _, mnemonic in observed)
            exception_ok = all(kind in {"trap_illegal_instruction", "trap_machine_ecall"}
                               and pc not in indexed_pcs for kind, pc in exceptions)
            manifest["spike_indexed_instructions"] = observed
            manifest["status"] = ("SPIKE_PASS" if result["returncode"] == 0 and not faults
                                  and exit_reached and indexed_ok and exception_ok
                                  and len(records) < 100000 else "SPIKE_NOT_PASS")
        else:
            manifest["status"] = "BUILD_FAILED"
    manifest["input_hashes_after"] = {path: sha(path) for path in inputs}
    require(manifest["input_hashes_after"] == inputs, "input drift")
    save(output / "manifest.json", manifest)
    print(json.dumps({"output": str(output), "status": manifest["status"], "accesses": len(accesses)}))
    return 0 if manifest["status"] in {"DERIVED_NOT_RUN", "SPIKE_PASS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
