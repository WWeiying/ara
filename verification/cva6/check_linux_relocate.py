#!/usr/bin/env python3
"""Independent host oracle for Linux-source MMU relocation (not OS signoff)."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ara_verify.probes import check_probe_capture

MASK = (1 << 64) - 1
PA, VA, MODE = 0x80000000, 0xffffffff80000000, 8 << 60
DELTA = VA - PA


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canon(value):
    # CVA6's internal PC ports are 39 bits; sign-extend only that representation.
    if value < (1 << 39) and value & (1 << 38):
        return value | (MASK ^ ((1 << 39) - 1))
    return value


def parse_dump(text):
    symbols, code = {}, {}
    in_text = False
    for line in text.splitlines():
        if line.startswith("Disassembly of section "):
            in_text = line == "Disassembly of section .text:"
        match = re.fullmatch(r"([0-9a-f]+) <([^>]+)>:", line)
        if match:
            symbols[match[2]] = int(match[1], 16)
        match = re.match(r"\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s", line)
        if match and in_text:
            code[int(match[1], 16)] = int(match[2], 16)
    names = ("_start", "linux_satp_trampoline", "linux_virtual_entry", "linux_satp_final",
             "linux_debug_park", "reloc_s_resume", "reloc_s_ecall", "m_handler",
             "trampoline_pg_dir", "final_pg_dir", "pages")
    require(all(n in symbols for n in names), "missing frozen disassembly symbols")
    require(symbols["_start"] == PA, "unexpected program base")
    for name in ("trampoline_pg_dir", "final_pg_dir", "pages"):
        require(PA <= symbols[name] < PA + 0x200000 and symbols[name] % 4096 == 0,
                f"unmapped or unaligned object: {name}")
    require(symbols["pages"] + 8192 <= PA + 0x200000, "data exceeds kernel superpage")
    # Independently decode crt0's AUIPC/ADDI, instead of accepting the DUT's GP.
    upper, lower = code[PA], code[PA + 4]
    require(upper & 0xfff == 0x197 and lower & 0xfffff == 0x18193, "unsupported GP initializer")
    hi = upper & 0xfffff000
    hi -= (1 << 32) if hi & (1 << 31) else 0
    lo = lower >> 20
    lo -= 4096 if lo & 2048 else 0
    symbols["gp_expected"] = (PA + hi + lo) & MASK
    return symbols, code


def expected_observations(s):
    leaf = lambda pa: ((pa >> 12) << 10) | 0xc7
    return [MODE | (s["final_pg_dir"] >> 12), 12,
            s["linux_virtual_entry"], s["linux_virtual_entry"],
            s["reloc_s_resume"] + DELTA, s["gp_expected"] + DELTA,
            0x1122334455667788, 0x8877665544332211, 0x13579bdf2468ace0,
            s["linux_debug_park"] + DELTA, 1, leaf(s["pages"]), leaf(s["pages"] + 4096)]


def check_console(text, s):
    def fields(prefix, count):
        pairs = re.findall(rf"^{prefix} (\d+) ([0-9a-f]{{16}})$", text, re.M)
        require(len(pairs) == count and sorted(int(i) for i, _ in pairs) == list(range(count)),
                f"missing/duplicate {prefix} observations")
        return {int(i): int(v, 16) for i, v in pairs}
    obs, trap = fields("RELOC_OBS", 13), fields("RELOC_TRAP", 4)
    for i, expected in enumerate(expected_observations(s)):
        require(obs[i] == expected, f"observation {i}: {obs[i]:016x} != {expected:016x}")
    require(trap[0] == 9 and trap[1] == s["reloc_s_ecall"] + DELTA and trap[2] == 0,
            "wrong final M trap")
    require(trap[3] & 0x1800 == 0x800, "final trap did not originate in S")
    require(re.findall(r"^RELOC_MEMORY (.*)$", text, re.M) ==
            ["6b6b6b6b6b6b6b6b 13579bdf2468ace0"], "write reached wrong physical page")
    require("linux_mmu_relocate: checks=26 failures=0" in text and
            "PASSED: linux_mmu_relocate" in text, "incomplete program checker")


def probe_rows(path):
    return [dict(word.split("=", 1) for word in line.split())
            for line in path.read_text().splitlines() if line.startswith("cycle=")]


def check_trace(rows, s, code):
    retired = [r for r in rows if r["event"] == "retire"]
    pcs = [canon(int(r["pc"], 16)) for r in retired]
    counts = Counter(pcs)
    keys = [s["linux_satp_trampoline"], s["linux_virtual_entry"] + DELTA,
            s["linux_satp_final"] + DELTA, s["reloc_s_resume"] + DELTA, s["m_handler"]]
    require(all(counts[p] == 1 for p in keys), "missing/duplicate relocation milestone")
    indices = [pcs.index(p) for p in keys]
    require(indices == sorted(indices), "wrong relocation order")
    require(counts[s["linux_virtual_entry"]] == 0, "physical fall-through incorrectly retired")
    high_count = 0
    for row, pc in zip(retired[indices[0] + 1:indices[-1]], pcs[indices[0] + 1:indices[-1]]):
        require(VA <= pc < VA + 0x200000, f"unexpected low or unmapped S PC {pc:x}")
        require(code.get(pc - DELTA) == int(row["insn"], 16), "high-VA instruction differs from frozen ELF dump")
        high_count += 1
    require(high_count > 10, "no substantive high-VA execution")
    return {"retire_count": len(retired), "high_va_retire_count": high_count}


def check_csr_and_traps(csr, traps, s):
    expected = {s["linux_satp_trampoline"]: MODE | (s["trampoline_pg_dir"] >> 12),
                s["linux_satp_final"] + DELTA: MODE | (s["final_pg_dir"] >> 12)}
    seen = Counter()
    for r in csr:
        pc = canon(int(r["commit0_pc"], 16))
        if pc in expected and int(r["ack"], 2) & 1 and r["csr_we"] == "1":
            require(r["priv"] == "01" and r["csr_addr"] == "180", "SATP write outside S mode")
            require(int(r["csr_wdata"], 16) == expected[pc], "wrong SATP written")
            seen[pc] += 1
    require(all(seen[pc] == 1 for pc in expected), "SATP write evidence not unique/complete")
    faults = [r for r in traps if r["ex_valid"] == "1" and int(r["ex_cause"], 16) == 12]
    require(faults, "missing real instruction page fault")
    for r in faults:
        require(r["priv_q"] == "01" and r["trap_to_priv"] == "01", "page fault not delegated S->S")
        require(canon(int(r["pc"], 16)) == s["linux_virtual_entry"], "wrong fault PC")
        require(int(r["ex_tval"], 16) == s["linux_virtual_entry"], "wrong fault address")
        require(canon(int(r["trap_vector"], 16)) == s["linux_virtual_entry"] + DELTA,
                "fault not redirected to high-VA continuation")


def audit(run, dump):
    from elftools.elf.elffile import ELFFile
    summaries = json.loads((run / "summary.json").read_text())
    selected = [r for r in summaries if r["name"] == "rvv:linux_mmu_relocate"]
    require(len(selected) == 1 and selected[0]["status"] == "PASS", "VCS relocation test did not pass")
    test = run / "tests/rvv_linux_mmu_relocate"
    inputs = json.loads((test / "inputs.json").read_text())
    require(hashlib.sha256((test / "input.elf").read_bytes()).hexdigest() == inputs["binary"]["sha256"],
            "ELF snapshot hash changed")
    s, code = parse_dump(dump.read_text())
    with (test / "input.elf").open("rb") as f:
        elf = ELFFile(f)
        require(elf.elfclass == 64 and elf.little_endian and elf["e_machine"] == "EM_RISCV",
                "wrong ELF architecture")
        segments = [(seg["p_vaddr"], seg.data()) for seg in elf.iter_segments()
                    if seg["p_type"] == "PT_LOAD"]
        for pc, insn in code.items():
            size = 4 if insn & 3 == 3 else 2
            matches = [data[pc - base:pc - base + size] for base, data in segments
                       if base <= pc and pc + size <= base + len(data)]
            require(len(matches) == 1 and int.from_bytes(matches[0], "little") == insn,
                    f"disassembly does not match frozen ELF at {pc:x}")
    check_console((test / "console.log").read_text(), s)
    integrity = check_probe_capture(test / "work", ["csr", "trap_ctrl", "mmu", "ptw"])
    require(integrity["status"] == "PASS", "incomplete/corrupt probe capture")
    with (test / "commit_trace.csv").open() as f:
        details = check_trace(list(csv.DictReader(f)), s, code)
    check_csr_and_traps(probe_rows(test / "work/state_prereq.csr.log"),
                       probe_rows(test / "work/state_prereq.trap_ctrl.log"), s)
    return {"status": "PASS", "scope": "Linux-derived MMU relocation and directed TLB remap, not OS boot",
            "binary_sha256": inputs["binary"]["sha256"],
            "dump_sha256": hashlib.sha256(dump.read_bytes()).hexdigest(), **details}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--dump", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = audit(args.run, args.dump)
    except (ValueError, KeyError, OSError, ImportError) as error:
        result = {"status": "FAIL", "reason": str(error)}
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
