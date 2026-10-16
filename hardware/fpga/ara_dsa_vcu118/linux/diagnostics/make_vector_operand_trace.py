#!/usr/bin/env python3
"""Build bounded GDB operand tracing from an already captured QEMU TB window."""
import argparse
from pathlib import Path
import re

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("history", type=Path)
p.add_argument("output", type=Path)
args = p.parse_args()
log = (args.history / "gdb.log").read_text()
origin = int(re.search(r"FIRST_USER_PC ([0-9a-f]+)", log)[1], 16)
sites = {}
for line in (args.history / "tb.log").read_text().splitlines():
    match = re.match(r"0x([0-9a-f]+):\s+([0-9a-f]{8})\s+(v\S+)\s", line)
    if match:
        address, opcode, mnemonic = match.groups()
        address = int(address, 16)
        if address < (1 << 63):
            sites[address - origin] = (opcode, mnemonic)
if not sites or len(sites) > 128:
    raise SystemExit("Unexpected trace site count")
lines = ["set pagination off", "set confirm off", "set architecture riscv:rv64",
         "target remote 127.0.0.1:12347", "hbreak *0xffffffff80015e94", "continue",
         "set $origin = *(unsigned long *)$a0", "set $events = 0", "set $restores = 0",
         'printf "OPERAND_ORIGIN %lx\\n", $origin', "commands 1", "silent",
         "set $restores = $restores + 1",
         "if *(unsigned long *)($a0+136) == 63",
         'printf "READ_RESTORE events=%d restores=%d\\n", $events, $restores',
         "info registers pc a0 a3 a4 a5 vl vtype vstart", "detach", "quit", "end",
         "if $restores > 32", 'echo ERROR restore bound exceeded\\n', "quit 1", "end",
         "continue", "end"]
for offset, (opcode, mnemonic) in sorted(sites.items()):
    lines += [f"hbreak *($origin + ({offset}))", "commands", "silent",
              "set $events = $events + 1", "if $events > 1024",
              'echo ERROR operand bound exceeded\\n', "quit 1", "end",
              f'printf "VECTOR event=%d offset={offset} opcode={opcode} mnemonic={mnemonic} pc=%lx vl=%ld vtype=%lx vstart=%ld\\n", $events, $pc, $vl, $vtype, $vstart',
              "info registers ra sp t0 t1 t2 s0 s1 a0 a1 a2 a3 a4 a5 a6 a7 s2 s3 s4 s5 s6 s7 s8 s9 s10 s11 t3 t4 t5 t6",
              "continue", "end"]
lines += ["continue", "quit 1"]
with args.output.open("x") as output:
    output.write("\n".join(lines) + "\n")
print(f"TRACE_SITES {len(sites)} {args.output}")
