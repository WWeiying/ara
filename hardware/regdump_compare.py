#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vector Register Comparison Tool
Compares vector register states between Spike (ideal) and hardware simulation (real)
"""

import re
import sys
import argparse
from collections import defaultdict


# ==============================================================================
# Tee Output Handler (for logging to both console and file)
# ==============================================================================

class Tee:
    """Simultaneously writes output to console and log file"""
    def __init__(self, console, logfile):
        self.console = console
        self.logfile = logfile
    
    def write(self, message):
        self.console.write(message)
        self.logfile.write(message)
        self.logfile.flush()  # Ensure real-time logging
    
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
    
    matches.reverse()  # Reverse to get memory order [0] -> [15]
    
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
        part = hexstream[i:i+width]
        if len(part) == width:
            raw_elems.append("0x" + part)
    
    return list(reversed(raw_elems))[:32]  # Reverse to get elem0..31 order


# ==============================================================================
# Ideal Log Parser (Spike Output)
# ==============================================================================

class IdealParser:
    """Parser for Spike simulation logs (ideal reference)"""
    
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
            if entry and entry["vregs"]:
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
# Real Log Parser (Hardware Simulation)
# ==============================================================================

class RealParser:
    """Parser for hardware simulation logs (real implementation)"""
    
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
            # Pattern 1: Lines containing both cycle and instruction (e.g., "cycle = 40, id = 0, instr = 5208a2d7")
            m = re.search(r'cycle\s*=\s*(\d+).*?instr\s*=\s*([0-9a-fA-F]+)', line, re.IGNORECASE)
            if m:
                if current:
                    self.entries.append(current)
                cycle_val = int(m.group(1))
                instr = "0x" + m.group(2).lower()
                current = {"instr": instr, "vregs": {}, "cycle": cycle_val}
                continue
            
            # Pattern 2: Lines containing only instruction (for compatibility)
            m = re.search(r'instr\s*=\s*([0-9a-fA-F]+)', line)
            if m:
                if current:
                    self.entries.append(current)
                instr = "0x" + m.group(1).lower()
                current = {"instr": instr, "vregs": {}}
                continue
            
            # Pattern 3: Vector register values (e.g., "v5  = 0000001f0000001e...")
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
        self.mismatch_cnt = 0
        self.failed_instructions = []
    
    def _has_unknown_value(self, val_str):
        """
        Check if a hex string contains unknown values ('x' in the hex digit part).
        Valid: "0x00000000" -> no unknown (x only in prefix)
        Invalid: "0x12x4", "0xXXXXXXXX" -> contains unknown
        """
        s = val_str.replace(' ', '').lower()
        if not s.startswith('0x'):
            return 'x' in s
        
        # Only check the hex digit part (after '0x' prefix)
        hex_digits = s[2:]
        return 'x' in hex_digits
    
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
            self.total += 1
            
            # Print instruction header in trace mode (with cycle info)
            if self.args.trace:
                self._print_instruction_header(ideal, real, real_idx, idx)
            
            result = self.compare_inst(ideal, real, real_idx, idx)
            if not result:
                self.fail += 1
                self.failed_instructions.append({
                    'pc': ideal['pc'],
                    'instr': ideal['instr'],
                    'asm': ideal['asm'],
                    'real_idx': real_idx,
                    'ideal_idx': idx,
                    'cycle': real.get('cycle', None)
                })
            
            # One-line summary for non-trace mode
            if not self.args.trace:
                status = "PASS" if result else "FAIL"
                asm_short = ideal['asm'].split()[0] if ideal['asm'] else ideal['instr']
                cycle_info = f"Cycle={real['cycle']}" if 'cycle' in real else ""
                print(f"[{status}] {asm_short:12s} PC={ideal['pc']}  {cycle_info:15s} (Real #{real_idx} ↔ Spike #{idx})")
            
            real_idx += 1
        
        # Final report
        print("\n" + "="*70)
        print(f"TOTAL compared : {self.total}")
        print(f"PASS           : {self.total - self.fail}")
        print(f"FAIL           : {self.fail}")
        print(f"MISMATCHES     : {self.mismatch_cnt}")
        print("="*70)
        
        # Failed instructions summary
        if self.failed_instructions:
            print("\nFAILED INSTRUCTIONS:")
            print("-" * 70)
            for i, fail in enumerate(self.failed_instructions):
                cycle_info = f"Cycle={fail['cycle']}" if fail.get('cycle') is not None else "Cycle=N/A"
                print(f"  [{i}] {fail['asm']}")
                print(f"        PC={fail['pc']}, instr={fail['instr']}, {cycle_info}")
                print(f"        Real #{fail['real_idx']} ↔ Spike #{fail['ideal_idx']}")
            print("-" * 70)
        
        return self.fail == 0
    
    def _print_instruction_header(self, ide, rea, real_idx, ideal_idx):
        """Print instruction comparison header in trace mode with cycle info"""
        print("\n" + "="*70)
        print(f"Comparing instruction {ide['instr']} (PC={ide['pc']})")
        print(f"Assembly    : {ide['asm']}")
        
        # Add cycle information if available
        cycle_info = f"Cycle={rea['cycle']}" if 'cycle' in rea else "Cycle=N/A"
        print(f"Config      : VL={ide['vl']}, VSEW={ide['vsew']}  |  {cycle_info}  |  "
              f"Real #{real_idx} ↔ Spike #{ideal_idx}")
        print("="*70)
    
    def compare_inst(self, ide, rea, real_idx, ideal_idx):
        """Compare single instruction's vector register states"""
        inst_fail = False
        
        # First: print register values if trace-reg enabled (BEFORE comparison)
        if self.args.trace and self.args.trace_reg:
            for vname in sorted(set(ide["vregs"].keys()) | set(rea["vregs"].keys())):
                if vname in ide["vregs"] and vname in rea["vregs"]:
                    ideal_vals = ide["vregs"][vname]
                    real_vals = rea["vregs"][vname]
                    compare_len = min(ide["vl"], len(ideal_vals), len(real_vals))
                    print(f"\n  Register {vname} (first {compare_len} elements):")
                    print(f"    Ideal : {ideal_vals[:compare_len]}")
                    print(f"    Real  : {real_vals[:compare_len]}")
        
        # Second: perform element-by-element comparison
        for vname, real_vals in rea["vregs"].items():
            if vname not in ide["vregs"]:
                print(f"  [MISSING] {vname} not in ideal output")
                inst_fail = True
                continue
            
            ideal_vals = ide["vregs"][vname]
            compare_len = min(ide["vl"], len(ideal_vals), len(real_vals))
            
            for i in range(compare_len):
                # Clean strings: remove spaces and normalize case for comparison
                ideal_clean = ideal_vals[i].replace(' ', '').lower()
                real_clean = real_vals[i].replace(' ', '').lower()
                
                # CRITICAL FIX: Only check for 'x' in the HEX DIGIT PART (after '0x' prefix)
                if self._has_unknown_value(ideal_clean) or self._has_unknown_value(real_clean):
                    print(f"  MISMATCH {vname}[{i}]: ideal={ideal_vals[i]} vs real={real_vals[i]} (contains unknown 'x')")
                    self.mismatch_cnt += 1
                    inst_fail = True
                    continue
                
                # CRITICAL FIX: Only report mismatch when values actually differ
                if ideal_clean != real_clean:
                    print(f"  MISMATCH {vname}[{i}]: ideal={ideal_vals[i]} vs real={real_vals[i]}")
                    self.mismatch_cnt += 1
                    inst_fail = True
                # Else: values match - do nothing (no output for clean trace)
        
        # Third: print result in trace mode
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
    parser.add_argument("--log-file", help="Save complete output log to specified file (tee mode: console + file)")
    args = parser.parse_args()
    
    # Setup logging to file if requested
    original_stdout = sys.stdout
    log_file_handle = None
    tee_handler = None
    
    if args.log_file:
        try:
            log_file_handle = open(args.log_file, 'w', buffering=1)  # Line buffered
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
        # Restore original stdout and close log file
        if tee_handler:
            sys.stdout = original_stdout
            if log_file_handle:
                log_file_handle.close()
                print(f"\n[LOG] Full log saved to: {args.log_file}")


if __name__ == "__main__":
    import time
    sys.exit(main())
