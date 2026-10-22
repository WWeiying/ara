"""Owned software-only batch utilities. No import of active reduction runners."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]
WORK = BASE.parents[2]
INTEGRATION = BASE / 'integration'
CAMPAIGN = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
CANONICAL = CAMPAIGN / 'rvv_verified_handoff03/rvv_small_redspecial02'
INVENTORY = HERE.parent / 'original11_inventory01/inventory.json'
CC = WORK / 'install/riscv-gcc/bin/riscv64-unknown-elf-gcc'
OBJDUMP = CC.with_name('riscv64-unknown-elf-objdump')
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
ISA = 'rv64gcv_zfh_zvfh_zvl1024b'
SHAPES = ['e16_mf2', 'e16_m1', 'e16_m2', 'e16_m4', 'e16_m8',
          'e32_mf2', 'e32_m2', 'e32_m4', 'e32_m8']
LIMITS = {'steps': 3000000, 'raw_bytes': 256 * 1024 * 1024, 'seconds': 120}


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def read(path):
    return json.loads(Path(path).read_text())


def config(shape):
    require(shape in SHAPES, 'exact remaining9 membership')
    row, = [r for r in read(INVENTORY)['records'] if r['reduced_name'] == 'rvv_small_fp_redspecial_' + shape]
    return {'shape': shape, 'sew': row['sew'], 'lmul': row['lmul'], 'cap': row['cap1024'],
            'vl': row['vl'], 'word_bytes': row['sew'] // 8,
            'identity': 'original_' + shape, 'source': str(CANONICAL / row['reduced_name']),
            'inventory_record': row,
            'nan': 0x7e00 if row['sew'] == 16 else 0x7fc00000,
            'inf': 0x7c00 if row['sew'] == 16 else 0x7f800000}


def marker(c):
    return f"RVV_FP_REDSPECIAL_PASS sew={c['sew']} cases=1 flags_seen=16 errors=0"


def checkpins(pins):
    for path, digest in pins.items():
        require(sha(path) == digest, 'pin drift: ' + path)


def execute(command, output):
    save(str(output) + '.command.json', list(map(str, command)))
    p = subprocess.run(list(map(str, command)), capture_output=True, timeout=60)
    Path(output).write_bytes(p.stdout + p.stderr)
    require(p.returncode == 0, f'compile/host failed: {output}, rc={p.returncode}')
    return p.stdout.decode()


def disassemble(elf):
    return subprocess.check_output([str(OBJDUMP), '-d', str(elf)], text=True)


def instructions(text):
    return [[int(m[1], 16), m[2].lower(), m[3]] for m in re.finditer(
        r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([^\n]+)', text, re.M)]


def symbols(elf):
    out = {}
    for line in subprocess.check_output([str(OBJDUMP), '-t', str(elf)], text=True).splitlines():
        p = line.split()
        if len(p) >= 5 and re.fullmatch('[0-9a-f]{16}', p[0]):
            out[p[-1]] = int(p[0], 16)
    return out


def fixtures(path):
    return [[int(a, 16), int(b)] for a, b in re.findall(
        r'\{UINT64_C\(0x([0-9a-fA-F]+)\),\s*(\d+)\}', Path(path).read_text())]


def load_adapter():
    p = INTEGRATION / 'prepare.py'
    require(sha(p) == 'c8852599c65e0a0812a7dc77dc365eb40398252867a29b226f34d758e5c56cf8', 'adapter identity')
    spec = importlib.util.spec_from_file_location('sealed_wrapper_only', p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
