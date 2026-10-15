"""Resolve fatal paths from the pinned, actually linked ELF; never invent a PC."""
import hashlib
import re
import subprocess
from pathlib import Path

BIN = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin')
NM = BIN / 'riscv64-unknown-elf-nm'
OBJDUMP = BIN / 'riscv64-unknown-elf-objdump'

def require(ok, message):
    if not ok:
        raise ValueError(message)

def inspect(spec):
    elf = Path(spec['elf'])
    require(hashlib.sha256(elf.read_bytes()).hexdigest() == spec['elf_sha256'], 'Actual ELF hash mismatch')
    nm = subprocess.run([str(NM), '-S', '-n', '--defined-only', str(elf)],
                        check=True, capture_output=True, text=True, timeout=30).stdout
    dis = subprocess.run([str(OBJDUMP), '-d', str(elf)],
                         check=True, capture_output=True, text=True, timeout=30).stdout
    symbols, sizes = {}, {}
    for line in nm.splitlines():
        fields = line.split()
        require(len(fields) in (3, 4), 'Unexpected actual nm schema')
        symbols[fields[-1]] = int(fields[0], 16)
        sizes[fields[-1]] = int(fields[1], 16) if len(fields) == 4 else 0
    code = {int(a, 16): int(v, 16) for a, v in
            re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s', dis, re.M)}
    return dict(symbols=symbols, sizes=sizes, code=code, nm=nm, disassembly=dis)

def validate(spec, facts=None):
    facts = inspect(spec) if facts is None else facts
    symbols = facts['symbols']
    require(spec['symbols'] == symbols, 'Spec symbols differ from actual ELF')
    require({int(p): v for p, v in spec['code'].items()} == facts['code'], 'Spec code differs from actual ELF')
    for name in ('trap_entry', 'replay_trap', 'replay_exit'):
        require(name in symbols and symbols[name] in facts['code'], 'Missing mandatory fatal/exit symbol ' + name)
    require(symbols['trap_entry'] < symbols['replay_exit'], 'Fatal startup boundary')
    ranges = [(symbols['trap_entry'], symbols['replay_exit'])]
    for name in ('replay_trap', 'replay_mismatch'):
        if name not in symbols:
            continue
        require(facts['sizes'][name] > 0, 'Missing actual fatal function size ' + name)
        ranges.append((symbols[name], symbols[name] + facts['sizes'][name]))
    fatal = {pc for pc in facts['code'] if any(lo <= pc < hi for lo, hi in ranges)}
    require(symbols['replay_exit'] not in fatal, 'Fatal path overlaps valid exit')
    return fatal
