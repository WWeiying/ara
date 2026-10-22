"""Mature actual ELF disassembly helper, no compilation or reference execution."""
import re
import subprocess
from pathlib import Path
from newscope import HERE
OBJDUMP=Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-objdump')
NM=OBJDUMP.with_name('riscv64-unknown-elf-nm')


def disassemble(elf):
    txt=subprocess.check_output([str(OBJDUMP),'-d',str(elf)],text=True)
    code={};functions={};current=None
    for line in txt.splitlines():
        m=re.match(r'^([0-9a-f]+) <([^>]+)>:',line)
        if m:current=m[2];functions[current]=[]
        m=re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+(.*)',line)
        if m:
            row=dict(pc=int(m[1],16),insn=m[2],text=m[3]);code[m[1]]=row
            if current:functions[current].append(row)
    nm=subprocess.check_output([str(NM),'-n',str(elf)],text=True)
    symbols={m[3]:int(m[1],16) for l in nm.splitlines() if (m:=re.match(r'^(\w+)\s+(\w)\s+(.+)$',l))}
    return dict(code=code,functions=functions,symbols=symbols),txt
