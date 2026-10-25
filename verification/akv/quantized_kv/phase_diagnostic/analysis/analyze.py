#!/usr/bin/env python3
"""Offline, diagnostic-only retirement accounting; never launch a simulator."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
CSV_SOURCE = ROOT / "verification/akv/run_refill_overlap_probe.py"
spec = importlib.util.spec_from_file_location("phase_commit_csv", CSV_SOURCE)
csv_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(csv_module)
COMMIT_HEADER = csv_module.COMMIT_HEADER
EVENTS = {"retire", "arch_start", "uop_alloc", "uop_done", "cvx_req", "cvx_resp"}
MASK64 = (1 << 64) - 1
PREFIX = "QUANT_DIAG_HSB_"
SUITE = PREFIX + "SUITE_PASS trials=3 outputs=768 rvv_exact=1 repeat_checks=0"
BEGIN = re.compile(PREFIX + r"BEGIN trial=([0-2]) mode=([0-2])")
RESULT = re.compile(
    PREFIX + r"RESULT trial=([0-2]) mode=([0-2]) cycles=([1-9][0-9]*) "
    r"calls=([0-9]+) dots=([0-9]+) commands=([0-9]+) values=([0-9]+) "
    r"panels=([0-9]+) copied=([0-9]+) quantizations=6 map=0 status=0 selection=0 "
    r"groups=([01]) executor=0 fcsr=([0-9]+) vcsr=5 max_abs=([0-9a-f]{8}) "
    r"pair_max_abs=([0-9a-f]{8}) pair_bits_differ=([0-9]+) errors=0 hex=([0-9a-f]{6144})")
CAP = (PREFIX + "CAP kind=1 heads=6 d=128 visible=128 kv_head=0 "
       "trials=3 scale=3db504f3 k_token_stride=144 v_token_stride=272 workspace=13120")
CUSTOM_SEQUENCE = [0x06B5045B, 0x02B5045B] * 4


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, "Duplicate JSON key: " + key)
        obj[key] = value
    return obj


def read_json(path):
    return json.loads(Path(path).read_text(), object_pairs_hook=unique_object)


def call_log(text):
    """Bind timings to the actual three-call diagnostic transcript, not ABBA."""
    calls, active, cap, suite, terminal = [], None, False, False, False
    baseline_flags = None
    for line in text.splitlines():
        require(not re.search(r"\b(?:FAIL|FAILED|TIMEOUT)\b|Fatal:|Error:", line, re.I),
                "Failure in diagnostic log")
        if "UVM_ERROR" in line or "UVM_FATAL" in line:
            require(re.fullmatch(r"UVM_(?:ERROR|FATAL)\s*:\s*0", line), "UVM error text")
        if "Core Test" in line:
            require(line == "Core Test *** SUCCESS ***" and suite and not terminal,
                    "Premature/duplicate terminal")
            terminal = True
        require(not any(prefix in line for prefix in
                        ("QUANT_PHASE_", "QUANT_THREEWAY_", "QUANT_ATTN_", "QUANT_STRIDED_", "QUANT_COMMON_")),
                "Predecessor/draft protocol cannot substitute for diagnostic")
        if PREFIX not in line:
            continue
        require(not terminal, "Diagnostic evidence after terminal")
        if line == CAP:
            require(not cap and not calls, "Duplicate/early capability")
            cap = True
        elif BEGIN.fullmatch(line):
            m = BEGIN.fullmatch(line)
            i, mode = int(m[1]), int(m[2])
            require(cap and not suite and active is None and i == mode == len(calls),
                    "Diagnostic order is not H/S/B")
            active = i
        elif RESULT.fullmatch(line):
            m = RESULT.fullmatch(line)
            i, mode, cycles = (int(m[j]) for j in (1, 2, 3))
            require(active == i == mode == len(calls) and cycles <= MASK64,
                    "Unpaired diagnostic result")
            expected = ((768, 768, 0, 768, 0, 0, 0), (8, 768, 0, 128, 0, 0, 0),
                        (8, 0, 8, 128, 4, 9216, 1))[mode]
            require(tuple(int(m[j]) for j in range(4, 11)) == expected, "Diagnostic work mismatch")
            flags = int(m[11])
            if baseline_flags is None:
                baseline_flags = flags
            require(flags <= 31 and flags == baseline_flags, "Cross-mode flags mismatch")
            calls.append(dict(trial=i, mode=mode, cycles=cycles))
            active = None
        elif line == SUITE:
            require(len(calls) == 3 and active is None and not suite, "Incomplete/duplicate suite")
            suite = True
        else:
            raise ValueError("Unknown/malformed diagnostic protocol")
    require(cap and suite and terminal and len(calls) == 3 and active is None,
            "Incomplete diagnostic transcript")
    return calls


class LinkedELF:
    """Small ELF64-LE RISC-V executable reader; no dependency or DWARF guessing."""

    def __init__(self, data):
        self.data = data
        require(len(data) >= 64 and data[:7] == b"\x7fELF\x02\x01\x01", "Not ELF64 little-endian")
        header = struct.unpack_from("<HHIQQQIHHHHHH", data, 16)
        kind, machine, version, _, _, shoff, _, ehsize, _, _, shsize, shnum, _ = header
        require((kind, machine, version, ehsize, shsize) == (2, 243, 1, 64, 64) and shnum > 0,
                "Require linked RISC-V executable with ordinary section table")
        require(shoff + 64 * shnum <= len(data), "Truncated ELF section table")
        sections = [struct.unpack_from("<IIQQQQIIQQ", data, shoff + 64 * i) for i in range(shnum)]
        self.code, self.functions = [], []
        for section in sections:
            _, typ, flags, addr, off, size, _, _, _, _ = section
            if flags & 4:
                require(typ == 1 and off + size <= len(data), "Invalid executable section")
                self.code.append((addr, addr + size, off))
        require(self.code, "No executable ELF sections")
        for section in sections:
            _, typ, _, _, off, size, link, _, _, entsize = section
            if typ != 2:
                continue
            require(entsize == 24 and size % 24 == 0 and off + size <= len(data) and link < shnum,
                    "Invalid ELF symbol table")
            strings = sections[link]
            require(strings[1] == 3 and strings[4] + strings[5] <= len(data), "Invalid symbol strings")
            names = data[strings[4]:strings[4] + strings[5]]
            for pos in range(off, off + size, 24):
                name, info, _, index, addr, length = struct.unpack_from("<IBBHQQ", data, pos)
                if info & 15 != 2 or index == 0 or length == 0:
                    continue
                require(name < len(names) and b"\0" in names[name:], "Invalid symbol name")
                label = names[name:names.index(b"\0", name)].decode("ascii")
                self.bytes_at(addr, length)
                entry = (addr, addr + length, label)
                if entry not in self.functions:
                    self.functions.append(entry)
        require(self.functions, "No sized function symbols; cannot infer function extents from next label")
        self.functions.sort()

    def bytes_at(self, pc, size):
        sections = [(start, off) for start, end, off in self.code if start <= pc and pc + size <= end]
        require(len(sections) == 1, "PC absent/ambiguous in executable ELF bytes")
        start, off = sections[0]
        return self.data[off + pc - start:off + pc - start + size]

    def function_at(self, pc, size):
        matches = [(start, end, name) for start, end, name in self.functions
                   if start <= pc and pc + size <= end]
        if not matches:
            return "UNMAPPED_FUNCTION"
        require(len({(a, b) for a, b, _ in matches}) == 1, "Overlapping non-alias function symbols")
        return "|".join(sorted(name for _, _, name in matches))


def disassembly_map(text, elf):
    instructions = {}
    for line in text.splitlines():
        m = re.match(r"\s*([0-9a-f]+):\s+([0-9a-f]{8}|[0-9a-f]{4})\s+(\S+)(.*)$", line)
        if not m:
            continue
        pc, raw, mnemonic = int(m[1], 16), m[2], m[3]
        size, bits = len(raw) // 2, int(raw, 16)
        require(pc not in instructions and pc % 2 == 0, "Duplicate/unaligned disassembly PC")
        require(int.from_bytes(elf.bytes_at(pc, size), "little") == bits, "Disassembly differs from ELF")
        require((size == 2 and bits & 3 != 3) or (size == 4 and bits & 3 == 3 and bits & 31 != 31),
                "Unexpected instruction length")
        instructions[pc] = dict(bits=bits, bytes=size, mnemonic=mnemonic,
                                function=elf.function_at(pc, size))
    require(instructions, "No linked instructions")
    return instructions


def is_cycle_read(item):
    return item["bytes"] == 4 and item["bits"] & ~0xF80 == 0xC0002073


def instruction_type(item):
    bits, mnemonic = item["bits"], item["mnemonic"]
    if bits in CUSTOM_SEQUENCE:
        return "qbs_command"
    require(not mnemonic.startswith(".") and bits & 127 != 0x5B, "Unknown/custom architectural opcode")
    if mnemonic.startswith("vset"):
        require(bits & 127 == 0x57, "Bad vector configuration decode")
        return "rvv_configuration"
    if mnemonic.startswith("v"):
        require(bits & 127 in (0x57, 0x07, 0x27), "Bad RVV decode")
        return "rvv_memory" if bits & 127 in (0x07, 0x27) else "rvv_compute"
    scalar_fp = (bits & 127 in (0x07, 0x27, 0x43, 0x47, 0x4B, 0x4F, 0x53)
                 if item["bytes"] == 4 else bool(re.match(r"(?:c\.)?f[ls]", mnemonic)))
    return "scalar_fp" if scalar_fp else "scalar_other"


def phase_classifier(mapping, instructions):
    require(set(mapping) == {"schema", "functions", "ranges"} and
            mapping["schema"] == "quantkv_phase_map_v1", "Wrong phase map schema")
    require(isinstance(mapping["functions"], dict) and isinstance(mapping["ranges"], list), "Bad phase map")
    available = {part for item in instructions.values() for part in item["function"].split("|")}
    for name, phase in mapping["functions"].items():
        require(name in available and isinstance(phase, str) and re.fullmatch(r"[a-z][a-z0-9_]*", phase),
                "Missing function/invalid phase label")
        require(not re.match(r"^(?:main|akv_quant_strided_execute)(?:\.|$)", name),
                "Mixed orchestration cannot be a whole-function phase")
    ranges = []
    for region in mapping["ranges"]:
        require(set(region) == {"start", "end", "function", "phase", "evidence"}, "Bad phase range fields")
        require(all(isinstance(region[k], str) for k in region), "Phase range values must be strings")
        start, end = int(region["start"], 0), int(region["end"], 0)
        require(start in instructions and end > start and region["evidence"].strip() and
                re.fullmatch(r"[a-z][a-z0-9_]*", region["phase"]), "Invalid or unjustified phase PC range")
        cursor = start
        while cursor < end:
            require(cursor in instructions and region["function"] in instructions[cursor]["function"].split("|"),
                    "Phase range crosses unknown code/function")
            cursor += instructions[cursor]["bytes"]
        require(cursor == end and all(end <= a or start >= b for a, b, _ in ranges),
                "Overlapping/misaligned phase ranges")
        ranges.append((start, end, region["phase"]))

    def classify(pc):
        for start, end, label in ranges:
            if start <= pc < end:
                return label
        labels = {mapping["functions"][name] for name in instructions[pc]["function"].split("|")
                  if name in mapping["functions"]}
        require(len(labels) <= 1, "Contradictory phase labels for function aliases")
        return next(iter(labels), "unclassified_orchestration")
    return classify


def analyze(disassembly, commit_stream, calls, boundary_pcs, phase_map):
    """disassembly is an ELF-validated PC map; reject incomplete retirement proof."""
    require(len(calls) == 3 and all(set(c) == {"trial", "mode", "cycles"} and
            all(type(c[k]) is int for k in c) and 0 < c["cycles"] <= MASK64 and c["trial"] == c["mode"] == i
            for i, c in enumerate(calls)), "Require own complete three-call timing contract")
    require(len(boundary_pcs) == 2 and len(set(boundary_pcs)) == 2 and
            all(pc in disassembly and is_cycle_read(disassembly[pc]) and
                disassembly[pc]["bits"] >> 7 & 31 for pc in boundary_pcs), "Invalid start/end cycle CSR PCs")
    require({pc for pc, item in disassembly.items() if is_cycle_read(item)} == set(boundary_pcs),
            "Extra cycle CSR read sites: boundary contract requires source review")
    phase_for = phase_classifier(phase_map, disassembly)
    windows, reads, current = [], [], None
    last_order, last_retire_cycle, last_port = -1, -1, -1
    for row in csv_module.csv_records(commit_stream, COMMIT_HEADER, EVENTS):
        require(all(row[k] <= MASK64 for k in ("cycle", "pc", "rd_wdata", "mem_addr", "mem_wdata")) and
                row["insn"] <= 0xFFFFFFFF and row["rd"] < 32 and row["trap"] in (0, 1),
                "Out-of-range trace fields")
        if row["event"] != "retire":
            continue
        require(row["order"] == last_order + 1 and 0 <= row["port"] < 2 and row["trans_id"] == -1,
                "Missing/duplicate retire order or invalid commit port")
        require(row["cycle"] != last_retire_cycle or row["port"] > last_port,
                "Same-cycle retirement port order violation")
        last_order, last_retire_cycle, last_port = row["order"], row["cycle"], row["port"]
        pc = row["pc"]
        if current is None and pc not in boundary_pcs:
            continue
        require(row["trap"] == 0 and pc in disassembly, "Trap or unknown PC inside measurement")
        item = disassembly[pc]
        require(row["insn"] == item["bits"], "Retired instruction differs from linked ELF")
        if pc in boundary_pcs:
            require(len(reads) < 6 and pc == boundary_pcs[len(reads) % 2] and
                    row["rd"] == (item["bits"] >> 7 & 31), "Wrong/repeated cycle CSR boundary")
            reads.append(dict(pc=hex(pc), order=row["order"], monitor_cycle=row["cycle"], value=row["rd_wdata"]))
            if current is None:
                current = dict(types=Counter(), functions=Counter(), phases=Counter(), mnemonics=Counter(),
                               function_gaps=Counter(), phase_gaps=Counter(), custom=[], previous_cycle=row["cycle"])
                continue
            start, end = reads[-2:]
            elapsed = (end["value"] - start["value"]) & MASK64
            require(elapsed == calls[len(windows)]["cycles"], "CSR rd_wdata delta != own printed call cycles")
            count = sum(current["types"].values())
            require(count == end["order"] - start["order"] - 1, "Retirement accounting incomplete")
            expected = CUSTOM_SEQUENCE if len(windows) == 2 else []
            require(current["custom"] == expected, "Wrong QBS retired command sequence/work")
            tail = row["cycle"] - current["previous_cycle"]
            span = end["monitor_cycle"] - start["monitor_cycle"]
            require(sum(current["function_gaps"].values()) + tail == span and
                    sum(current["phase_gaps"].values()) + tail == span and
                    sum(current["functions"].values()) == sum(current["phases"].values()) == count,
                    "PC-context interval accounting incomplete")
            unknown = current["phases"]["unclassified_orchestration"]
            windows.append(dict(**calls[len(windows)], start=start, end=end, csr_cycle_delta=elapsed,
                monitor_retire_span=span, monitor_minus_csr_delta=span-elapsed,
                retired_instructions=count, retirement_types=dict(sorted(current["types"].items())),
                functions=dict(sorted(current["functions"].items())), phases=dict(sorted(current["phases"].items())),
                mapped_phase_instructions=count-unknown, unmapped_phase_instructions=unknown,
                mnemonics=dict(sorted(current["mnemonics"].items())),
                function_next_pc_gap_cycles=dict(sorted(current["function_gaps"].items())),
                phase_next_pc_gap_cycles=dict(sorted(current["phase_gaps"].items())),
                end_csr_gap_cycles=tail, qbs_command_words=[f"{x:08x}" for x in current["custom"]]))
            current = None
            continue
        category = instruction_type(item)
        phase = phase_for(pc)
        current["types"][category] += 1
        current["functions"][item["function"]] += 1
        current["phases"][phase] += 1
        current["mnemonics"][item["mnemonic"]] += 1
        gap = row["cycle"] - current["previous_cycle"]
        current["function_gaps"][item["function"]] += gap
        current["phase_gaps"][phase] += gap
        current["previous_cycle"] = row["cycle"]
        if category == "qbs_command":
            current["custom"].append(item["bits"])
    require(len(reads) == 6 and len(windows) == 3 and current is None, "Missing complete six-CSR/three-call proof")
    return dict(schema="quantkv_phase_analysis_v1", state="DIAGNOSTIC_RETIREMENT_PROVEN",
        windows=windows, measurement_pcs=[hex(pc) for pc in boundary_pcs], csr_reads=6,
        phase_coverage="PARTIAL" if any(w["unmapped_phase_instructions"] for w in windows) else "ALL_RETIRED_PCS_LABELLED",
        interval_semantics="[previous retire cycle, current retire cycle) assigned to NEXT retired PC; end-CSR gap separate; same-cycle gaps zero",
        boundary_semantics="Both cycle CSR instructions excluded from instruction counts; monitor span and CSR rd_wdata delta reported separately",
        limitations=["PC-context retirement interarrival accounting, NOT execution/stall cycles or utilization",
                     "No call-stack attribution; common callees are not charged to inferred caller phases",
                     "Source/PC phase labels require review; all labelled PCs do not prove every software stage",
                     "Diagnostic H/S/B is not mirrored performance acceptance, numerical oracle or independent UVM certification"],
        functional_acceptance=False, performance_acceptance=False, hardware_utilization_claimed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True,
                        help="Pinned quantkv_phase_inputs_v1 JSON; all paths relative to this manifest")
    parser.add_argument("--inputs-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(digest(args.inputs) == args.inputs_sha256, "Input manifest identity mismatch")
    config = read_json(args.inputs)
    require(set(config) == {"schema", "files", "start_pc", "end_pc"} and
            config["schema"] == "quantkv_phase_inputs_v1", "Wrong input manifest schema")
    require(set(config["files"]) == {"elf", "log", "commit", "phase_map", "objdump", "monitor"},
            "Missing/extra input roles")
    paths, pins = {}, {str(args.inputs.resolve()): args.inputs_sha256}
    for role, entry in config["files"].items():
        require(set(entry) == {"path", "sha256"} and re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]),
                "Malformed input identity")
        path = (args.inputs.parent / entry["path"]).resolve(strict=True)
        require(path.is_file() and digest(path) == entry["sha256"], "Input identity mismatch: " + role)
        paths[role] = path
        pins[str(path)] = entry["sha256"]
    require(len(set(paths.values())) == len(paths), "Input roles must be distinct")
    out = args.output.resolve()
    require(not out.exists(), "Output must be fresh")
    for path in (Path(__file__), HERE / "README.md", HERE / "test_analyze.py", CSV_SOURCE, Path(sys.executable).resolve()):
        pins[str(path.resolve())] = digest(path)
    monitor = paths["monitor"].read_text()
    require("cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr," in monitor and
            "rvfi_instr_i[port].pc_rdata" in monitor and "rvfi_instr_i[port].rd_wdata" in monitor,
            "Monitor does not match reviewed retire field contract")
    command = [str(paths["objdump"]), "-d", str(paths["elf"])]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=True)
    elf = LinkedELF(paths["elf"].read_bytes())
    instructions = disassembly_map(completed.stdout, elf)
    calls = call_log(paths["log"].read_text())
    with paths["commit"].open(newline="") as stream:
        report = analyze(instructions, stream, calls,
                         [int(config["start_pc"], 0), int(config["end_pc"], 0)], read_json(paths["phase_map"]))
    for name, expected in pins.items():
        require(digest(name) == expected, "Post-analysis input drift: " + name)
    report.update(elf_sha256=pins[str(paths["elf"])], objdump_command=command,
                  disassembly_sha256=hashlib.sha256(completed.stdout.encode()).hexdigest(),
                  input_manifest_sha256=args.inputs_sha256, pre_post_pins_match=True)
    out.mkdir(parents=True, exist_ok=False)
    (out / "disassembly.txt").write_text(completed.stdout)
    (out / "objdump.stderr").write_text(completed.stderr)
    (out / "pins.json").write_text(json.dumps(pins, sort_keys=True, indent=2) + "\n")
    report["pins_sha256"] = digest(out / "pins.json")
    (out / "result.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "result": str(out / "result.json")}))


if __name__ == "__main__":
    main()
