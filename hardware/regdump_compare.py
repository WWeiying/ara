#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vector Register Comparison Tool
Compares vector register states between Spike (ideal) and hardware simulation (real)
"""

import re
import sys
import time
import argparse
from collections import defaultdict


# ==============================================================================
# Tee Output Handler
# ==============================================================================

class Tee:
    """Simultaneously writes output to console and log file"""
    def __init__(self, console, logfile):
        self.console = console
        self.logfile = logfile

    def write(self, message):
        self.console.write(message)
        self.logfile.write(message)
        self.logfile.flush()

    def flush(self):
        self.console.flush()
        self.logfile.flush()


# ==============================================================================
# Utility Functions
# ==============================================================================

def parse_ideal_vreg(line, sew=32):
    """Parse vector register from Spike ideal log"""
    matches = re.findall(r'\[\d+\]:\s*0x([0-9a-fA-F]{16})', line)
    if not matches:
        return []

    matches.reverse()

    elements = []
    for hex64 in matches:
        val64 = int(hex64, 16)
        if sew == 32:
            elem_low = val64 & 0xFFFFFFFF
            elem_high = (val64 >> 32) & 0xFFFFFFFF
            elements.append(f"0x{elem_low:08x}")
            elements.append(f"0x{elem_high:08x}")
        elif sew == 64:
            elements.append(f"0x{val64:016x}")

    return elements[:32]


def parse_real_vreg(hexstream, sew=32):
    """Parse vector register from hardware real log"""
    hexstream = hexstream.replace(" ", "").lower()
    width = sew // 4

    raw_elems = []
    for i in range(0, len(hexstream), width):
        part = hexstream[i:i + width]
        if len(part) == width:
            raw_elems.append("0x" + part)

    return list(reversed(raw_elems))[:32]


def strip_asm_comment(asm):
    if not asm:
        return ""
    return asm.split("#", 1)[0].strip()


def parse_asm(asm):
    asm = strip_asm_comment(asm)
    if not asm:
        return "", []

    parts = asm.split(None, 1)
    op = parts[0].strip()
    operands = []
    if len(parts) > 1:
        operands = [x.strip() for x in parts[1].split(",") if x.strip()]
    return op, operands


def is_vector_instruction(asm):
    asm = strip_asm_comment(asm)
    if not asm:
        return False
    op = asm.split()[0]
    return op.startswith("v")


def expand_vreg_group(base_vreg, count):
    m = re.match(r"^v(\d+)$", base_vreg)
    if not m:
        return []

    base = int(m.group(1))
    regs = []
    for i in range(count):
        regno = base + i
        if regno > 31:
            break
        regs.append(f"v{regno}")
    return regs


def get_dest_vregs_from_asm(asm):
    """
    Destination register extraction rule:
    - If opcode starts with "vs", treat as store, return []
    - If opcode starts with "vl", treat as load, first operand is destination
    - Otherwise, first operand is treated as destination if it is a vector register
    - For vlNr.v, expand destination register group
    """
    op, operands = parse_asm(asm)
    if not op or not operands:
        return []

    if op.startswith("vset"):
        return []

    if op.startswith("vs"):
        return []

    first = operands[0]
    m = re.match(r"^(v\d+)$", first)
    if not m:
        return []

    base_vreg = m.group(1)

    if op.startswith("vl"):
        m_whole = re.match(r"^vl(\d+)r\.v$", op)
        if m_whole:
            nreg = int(m_whole.group(1))
            return expand_vreg_group(base_vreg, nreg)

    return [base_vreg]


# ==============================================================================
# Ideal Log Parser
# ==============================================================================

class IdealParser:
    """Parser for Spike simulation logs"""

    def __init__(self, filename):
        self.entries = []
        self.parse(filename)

    def parse(self, filename):
        try:
            with open(filename) as f:
                lines = f.readlines()
        except FileNotFoundError:
            print(f"ERROR: Ideal log file not found: {filename}")
            sys.exit(1)

        i = 0
        while i < len(lines):
            m = re.search(r'core\s+\d+:\s+(0x[0-9a-fA-F]+)\s+\((0x[0-9a-fA-F]+)\)\s+(.+)', lines[i])
            if not m:
                i += 1
                continue

            pc = m.group(1).lower()
            instr = m.group(2).lower()
            asm = m.group(3).strip()

            block = []
            j = i + 1
            while j < len(lines) and not re.search(r'core\s+\d+:', lines[j]):
                block.append(lines[j])
                j += 1

            entry = self.parse_block(pc, instr, asm, block)
            if entry and entry["vregs"] and is_vector_instruction(entry["asm"]):
                self.entries.append(entry)

            i = j

        print(f"Parsed {len(self.entries)} vector instructions from ideal log")

    def parse_block(self, pc, instr, asm, block):
        entry = {
            "pc": pc,
            "instr": instr,
            "asm": asm,
            "vl": 0,
            "vsew": 32,
            "vregs": {}
        }

        for line in block:
            m = re.search(r'\bvl:\s+(\d+)', line)
            if m:
                entry["vl"] = int(m.group(1))
            m = re.search(r'\bvsew:\s+e(\d+)', line)
            if m:
                entry["vsew"] = int(m.group(1))

        for line in block:
            m = re.match(r'\s*v(\d+):', line)
            if m:
                vname = f"v{m.group(1)}"
                elems = parse_ideal_vreg(line, entry["vsew"])
                if elems:
                    entry["vregs"][vname] = elems

        return entry


# ==============================================================================
# Real Log Parser
# ==============================================================================

class RealParser:
    """Parser for hardware simulation logs"""

    def __init__(self, filename):
        self.entries = []
        self.parse(filename)

    def parse(self, filename):
        try:
            with open(filename) as f:
                lines = f.readlines()
        except FileNotFoundError:
            print(f"ERROR: Real log file not found: {filename}")
            sys.exit(1)

        current = None
        for line in lines:
            m = re.search(r'cycle\s*=\s*(\d+).*?instr\s*=\s*([0-9a-fA-F]+)', line, re.IGNORECASE)
            if m:
                if current:
                    self.entries.append(current)
                cycle_val = int(m.group(1))
                instr = "0x" + m.group(2).lower()
                current = {"instr": instr, "vregs": {}, "cycle": cycle_val}
                continue

            m = re.search(r'instr\s*=\s*([0-9a-fA-F]+)', line)
            if m:
                if current:
                    self.entries.append(current)
                instr = "0x" + m.group(1).lower()
                current = {"instr": instr, "vregs": {}}
                continue

            m = re.match(r'\s*v(\d+)\s*=\s*(.+)', line)
            if m and current:
                vname = f"v{m.group(1)}"
                hexstream = m.group(2).strip()
                elems = parse_real_vreg(hexstream, sew=32)
                if elems:
                    current["vregs"][vname] = elems
                continue

        if current:
            self.entries.append(current)

        print(f"Parsed {len(self.entries)} vector instructions from real log (with cycle info where available)")


# ==============================================================================
# Comparison Engine
# ==============================================================================

class Comparator:
    """Compares vector register states between ideal and real logs"""

    def __init__(self, ideal_entries, real_entries, args):
        self.ideal_map = defaultdict(list)
        for e in ideal_entries:
            self.ideal_map[e["instr"]].append(e)

        self.real_entries = real_entries
        self.args = args
        self.total = 0
        self.fail = 0
        self.skip = 0
        self.skip_vl = 0
        self.skip_vs = 0
        self.skip_no_dest = 0
        self.mismatch_cnt = 0
        self.failed_instructions = []

    def _has_unknown_value(self, val_str):
        s = val_str.replace(" ", "").lower()
        if not s.startswith("0x"):
            return "x" in s
        hex_digits = s[2:]
        return "x" in hex_digits

    def _should_skip_instruction(self, asm):
        op, _ = parse_asm(asm)
        if not op:
            return False, None

        if self.args.skip_vl and op.startswith("vl"):
            return True, "vl"

        if self.args.skip_vs and op.startswith("vs"):
            return True, "vs"

        return False, None

    def _get_compare_vregs(self, ide, rea):
        if self.args.dest_only:
            return get_dest_vregs_from_asm(ide["asm"])
        return sorted(rea["vregs"].keys())

    def run(self):
        cursor = defaultdict(int)
        real_idx = 0

        for real in self.real_entries:
            instr = real["instr"]

            if not real["vregs"]:
                real_idx += 1
                continue

            if instr not in self.ideal_map:
                if self.args.trace:
                    print(f"[SKIP] Instruction {instr} not found in ideal log")
                self.skip += 1
                real_idx += 1
                continue

            idx = cursor[instr]
            if idx >= len(self.ideal_map[instr]):
                print(f"[ERROR] Too many executions of {instr} (real #{real_idx})")
                self.fail += 1
                real_idx += 1
                continue

            ideal = self.ideal_map[instr][idx]
            cursor[instr] += 1

            if not is_vector_instruction(ideal["asm"]):
                if self.args.trace:
                    print(f"[SKIP] Non-vector instruction: {ideal['asm']}")
                self.skip += 1
                real_idx += 1
                continue

            should_skip, reason = self._should_skip_instruction(ideal["asm"])
            if should_skip:
                if self.args.trace:
                    print(f"[SKIP-{reason.upper()}] {ideal['asm']}")
                self.skip += 1
                if reason == "vl":
                    self.skip_vl += 1
                elif reason == "vs":
                    self.skip_vs += 1
                real_idx += 1
                continue

            self.total += 1

            if self.args.trace:
                self._print_instruction_header(ideal, real, real_idx, idx)

            result = self.compare_inst(ideal, real, real_idx, idx)
            if not result:
                self.fail += 1
                self.failed_instructions.append({
                    "pc": ideal["pc"],
                    "instr": ideal["instr"],
                    "asm": ideal["asm"],
                    "real_idx": real_idx,
                    "ideal_idx": idx,
                    "cycle": real.get("cycle", None)
                })

            if not self.args.trace:
                status = "PASS" if result else "FAIL"
                asm_short = ideal["asm"].split()[0] if ideal["asm"] else ideal["instr"]
                cycle_info = f"Cycle={real['cycle']}" if "cycle" in real else ""
                print(f"[{status}] {asm_short:12s} PC={ideal['pc']}  {cycle_info:15s} (Real #{real_idx} ↔ Spike #{idx})")

            real_idx += 1

        print("\n" + "=" * 70)
        print(f"TOTAL compared : {self.total}")
        print(f"PASS           : {self.total - self.fail}")
        print(f"FAIL           : {self.fail}")
        print(f"MISMATCHES     : {self.mismatch_cnt}")
        print(f"SKIPPED        : {self.skip}")
        print(f"SKIP-VL        : {self.skip_vl}")
        print(f"SKIP-VS        : {self.skip_vs}")
        print(f"SKIP-NO-DEST   : {self.skip_no_dest}")
        print("=" * 70)

        if self.failed_instructions:
            print("\nFAILED INSTRUCTIONS:")
            print("-" * 70)
            for i, fail in enumerate(self.failed_instructions):
                cycle_info = f"Cycle={fail['cycle']}" if fail.get("cycle") is not None else "Cycle=N/A"
                print(f"  [{i}] {fail['asm']}")
                print(f"        PC={fail['pc']}, instr={fail['instr']}, {cycle_info}")
                print(f"        Real #{fail['real_idx']} ↔ Spike #{fail['ideal_idx']}")
            print("-" * 70)

        return self.fail == 0

    def _print_instruction_header(self, ide, rea, real_idx, ideal_idx):
        print("\n" + "=" * 70)
        print(f"Comparing instruction {ide['instr']} (PC={ide['pc']})")
        print(f"Assembly    : {ide['asm']}")
        cycle_info = f"Cycle={rea['cycle']}" if "cycle" in rea else "Cycle=N/A"
        print(
            f"Config      : VL={ide['vl']}, VSEW={ide['vsew']}  |  {cycle_info}  |  "
            f"Real #{real_idx} ↔ Spike #{ideal_idx}"
        )
        print("=" * 70)

    def compare_inst(self, ide, rea, real_idx, ideal_idx):
        inst_fail = False

        target_vregs = self._get_compare_vregs(ide, rea)

        if self.args.dest_only and not target_vregs:
            if self.args.trace:
                print(f"  [SKIP-NO-DEST] No destination vector register detected: {ide['asm']}")
            self.skip_no_dest += 1
            return True

        if self.args.trace and self.args.trace_reg:
            if self.args.dest_only:
                trace_regs = target_vregs
            else:
                trace_regs = sorted(set(ide["vregs"].keys()) | set(rea["vregs"].keys()))

            for vname in trace_regs:
                if vname in ide["vregs"] and vname in rea["vregs"]:
                    ideal_vals = ide["vregs"][vname]
                    real_vals = rea["vregs"][vname]
                    compare_len = min(ide["vl"], len(ideal_vals), len(real_vals))
                    print(f"\n  Register {vname} (first {compare_len} elements):")
                    print(f"    Ideal : {ideal_vals[:compare_len]}")
                    print(f"    Real  : {real_vals[:compare_len]}")
                elif vname in ide["vregs"]:
                    print(f"\n  Register {vname}: present in ideal only")
                elif vname in rea["vregs"]:
                    print(f"\n  Register {vname}: present in real only")

        for vname in target_vregs:
            if vname not in rea["vregs"]:
                print(f"  [MISSING] {vname} not in real output")
                inst_fail = True
                continue

            if vname not in ide["vregs"]:
                print(f"  [MISSING] {vname} not in ideal output")
                inst_fail = True
                continue

            ideal_vals = ide["vregs"][vname]
            real_vals = rea["vregs"][vname]
            compare_len = min(ide["vl"], len(ideal_vals), len(real_vals))

            for i in range(compare_len):
                ideal_clean = ideal_vals[i].replace(" ", "").lower()
                real_clean = real_vals[i].replace(" ", "").lower()

                if self._has_unknown_value(ideal_clean) or self._has_unknown_value(real_clean):
                    print(f"  MISMATCH {vname}[{i}]: ideal={ideal_vals[i]} vs real={real_vals[i]} (contains unknown 'x')")
                    self.mismatch_cnt += 1
                    inst_fail = True
                    continue

                if ideal_clean != real_clean:
                    print(f"  MISMATCH {vname}[{i}]: ideal={ideal_vals[i]} vs real={real_vals[i]}")
                    self.mismatch_cnt += 1
                    inst_fail = True

        if self.args.trace:
            status = "PASS" if not inst_fail else "FAIL"
            print(f"  RESULT: {status}")

        return not inst_fail


# ==============================================================================
# Main Entry Point
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Compare vector register states between Spike (ideal) and hardware (real)"
    )
    parser.add_argument("ideal", help="Ideal log file (Spike simulation output)")
    parser.add_argument("real", help="Real log file (hardware simulation output)")
    parser.add_argument("--trace", action="store_true",
                        help="Show detailed per-instruction trace")
    parser.add_argument("--trace-reg", action="store_true",
                        help="Show register values in trace mode")
    parser.add_argument("--dest-only", action="store_true",
                        help="Compare destination vector register(s) only")
    parser.add_argument("--skip-vl", action="store_true",
                        help="Skip instructions whose opcode starts with 'vl'")
    parser.add_argument("--skip-vs", action="store_true",
                        help="Skip instructions whose opcode starts with 'vs'")
    parser.add_argument("--log-file",
                        help="Save complete output log to specified file (tee mode: console + file)")
    args = parser.parse_args()

    original_stdout = sys.stdout
    log_file_handle = None
    tee_handler = None

    if args.log_file:
        try:
            log_file_handle = open(args.log_file, "w", buffering=1)
            tee_handler = Tee(sys.stdout, log_file_handle)
            sys.stdout = tee_handler
            print(f"[LOG] Output will be saved to: {args.log_file}")
            print(f"[LOG] Comparison started at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception as e:
            print(f"ERROR: Failed to open log file '{args.log_file}': {e}")
            return 1

    try:
        ideal = IdealParser(args.ideal)
        real = RealParser(args.real)

        if not ideal.entries:
            print("ERROR: No vector instructions found in ideal log")
            return 1
        if not real.entries:
            print("ERROR: No vector instructions found in real log")
            return 1

        comp = Comparator(ideal.entries, real.entries, args)
        success = comp.run()
        return 0 if success else 1

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        if args.trace:
            import traceback
            traceback.print_exc()
        return 1

    finally:
        if tee_handler:
            sys.stdout = original_stdout
            if log_file_handle:
                log_file_handle.close()
                print(f"\n[LOG] Full log saved to: {args.log_file}")


if __name__ == "__main__":
    sys.exit(main())
