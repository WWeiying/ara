#!/usr/bin/env python3
"""Build short Sv39 permission cases and precheck with no-PMP Spike."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

import build_rvv_memory_gaps as build

NAMES = ['sv39_gap34_load', 'sv39_gap34_store', 'sv39_gap34_fetch']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        parser.error('new output directory required')
    build.cases = lambda: [(n,) for n in NAMES]
    sys.argv = [sys.argv[0], '--output', str(out)]
    build.main()
    root = build.ROOT
    llvm = root / 'install/riscv-llvm'
    cc = llvm / 'bin/clang'
    runtime = root / 'apps/riscv-tests/benchmarks/common'
    flags = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '--target=riscv64-unknown-elf',
             '-mcmodel=medany', '-mno-relax', '-O2', '-std=gnu99', '-fno-vectorize',
             '-fno-slp-vectorize', '-mno-implicit-float', '-fno-common', '-fno-builtin-printf',
             '-DNR_LANES=4', '-DVLEN=1024', '-D__SPIKE__=1', '-DPREALLOCATE=1']
    includes = [f'-I{root / p}' for p in ('apps/include', 'apps/common',
        'apps/riscv-tests/isa/macros/scalar', 'apps/riscv-tests/isa/macros/vector',
        'apps/riscv-tests/env', 'apps/riscv-tests/benchmarks/common')]
    commands = json.loads((out / 'build_commands.json').read_text())

    def command(argv):
        argv = list(map(str, argv)); commands.append(argv)
        (out / 'build_commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        subprocess.run(argv, cwd=root, check=True, timeout=60)

    objects = []
    for name in ('crt.S', 'syscalls.c'):
        obj = out / ('spike_' + name + '.o')
        command([cc, *flags, *includes, '-c', runtime / name, '-o', obj]); objects.append(obj)
    rows = []
    for name in NAMES:
        elf = out / (name + '.spike')
        command([cc, *flags, *includes, '-fuse-ld=lld', '-static', '-nostdlib',
                 f'-T{runtime / "test.ld"}', build.DEST / (name + '.c'), *objects, '-o', elf])
        argv = [str(root / 'install/riscv-isa-sim/bin/spike'), '--isa=rv64gcv_zfh',
                '--pmpregions=0', '--varch=vlen:1024,elen:64', str(elf)]
        started = time.monotonic()
        result = subprocess.run(argv, capture_output=True, timeout=30)
        log = result.stdout + result.stderr
        (out / (name + '.spike.log')).write_bytes(log)
        rows.append({'test': 'rvv:' + name, 'command': argv, 'returncode': result.returncode,
                     'seconds': round(time.monotonic() - started, 3)})
        (out / 'spike_results.json').write_text(json.dumps(rows, indent=2) + '\n')
        if result.returncode or b'PASSED:' not in log:
            raise RuntimeError(f'Spike prerequisite failed: {name}; inspect {out}')
        print('Spike PASS', name, flush=True)


if __name__ == '__main__':
    main()
