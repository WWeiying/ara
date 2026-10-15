#!/usr/bin/env python3
"""Isolate measured extended trial 9 without modifying accepted test inputs."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'integration'
sys.path.insert(0, str(BASE))
import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent', type=Path,
                        default=Path('/tmp/current-board-integration-fast01/prepared'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out = args.out.resolve()
    original = prepare.check(args.parent)
    args.out.mkdir(parents=True, exist_ok=False)
    target = args.out / 'prepared'
    shutil.copytree(args.parent, target, copy_function=shutil.copyfile)
    source = target / 'extensions.c'
    before = source.read_text()
    loop = 'for (unsigned op = 0; op < 2; ++op) for (unsigned trial = 0; trial < 5; ++trial)'
    old_checks = '''        if (status >> 32 != flags) return replay_mismatch(5 * op + trial, ~1UL, flags, status >> 32);
        if (output[1] != expected) return replay_mismatch(5 * op + trial, 1, expected, output[1]);'''
    new_checks = '''        if (output[1] != expected) return replay_mismatch(5 * op + trial, 1, expected, output[1]);
        if (status >> 32 != flags) return replay_mismatch(5 * op + trial, ~1UL, flags, status >> 32);'''
    for text in (loop, old_checks, 'm8widen_nonzero cases=10'):
        if before.count(text) != 1:
            raise ValueError('unexpected parent source')
    source.write_text(before.replace(loop,
        'for (unsigned op = 1; op < 2; ++op) for (unsigned trial = 4; trial < 5; ++trial)')
        .replace(old_checks, new_checks).replace('m8widen_nonzero cases=10', 'm8widen_nonzero cases=1'))
    provenance = dict(original)
    provenance['isolated_trial'] = dict(
        parent_sha256=prepare.sha(args.parent / 'provenance.json'),
        original_trial=9, op='vfwredusum', vl=65, active_indices=[1, 33],
        scope='isolated supplement; retain original ten-trial regression',
        changed='loop bounds, truthful case count, data checked before flags; no checks removed')
    provenance['files'] = {str(p.relative_to(target)): prepare.sha(p)
                           for p in target.rglob('*') if p.is_file() and p.name != 'provenance.json'}
    prepare.save(target / 'provenance.json', provenance)
    compiler = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
    for backend in ('soc', 'spike'):
        directory = args.out / backend
        prepare.compile_programs(target, directory, compiler, spike_reference=backend == 'spike')
        ledger = json.loads((directory / 'programs.json').read_text())
        entry = ledger['programs']['m8widen_nonzero']
        entry['pass_markers'] = [m.replace('cases=10', 'cases=1') for m in entry['pass_markers']]
        ledger['programs'] = {'m8widen_nonzero': entry}
        prepare.save(directory / 'programs.json', ledger)
    subprocess.run([sys.executable, str(BASE / 'reference.py'), '--programs',
                    str(args.out / 'spike'), '--out', str(args.out / 'reference')], check=True)
    print('ISOLATED_TRIAL_PREPARED', args.out)


if __name__ == '__main__':
    main()
