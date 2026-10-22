#!/usr/bin/env python3
"""Build directed ELFs and replay the sealed final02 image, never build RTL."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'integration'
sys.path.insert(0, str(BASE))
import prepare
import run as checked

IMAGE = Path('/home/wangwy/fpga_runs/current_board_integration_final02/campaign/image')
PARENT = Path('/tmp/current-board-integration-fast01/prepared')
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
NAMES = ['first_only', 'same_vl', 'changed_vl']


def inside(path):
    path = path.resolve()
    if not path.is_relative_to(HERE):
        raise ValueError('all outputs must stay under reduction_epoch/')
    return path


def build(out):
    parent = prepare.check(PARENT)
    out.mkdir(parents=True, exist_ok=False)
    prepared = out / 'prepared'
    prepared.mkdir()
    for name in ('startup.S', 'runtime.c', 'replay.ld'):
        shutil.copyfile(PARENT / name, prepared / name)
    cases = []
    for variant, name in enumerate(NAMES):
        original = prepared / name / 'original'
        original.mkdir(parents=True)
        shutil.copyfile(HERE / 'epoch.S', original / 'epoch.S')
        shutil.copyfile(HERE / 'epoch.c', original.parent / 'case.c')
        cases.append(dict(id=name, assembly='epoch.S', include_combined=True,
                          defines=[f'VARIANT={variant}', f'CASE_MAIN={name}_main']))
    provenance = dict(schema_version=1, cases=cases, vlen=1024, nr_lanes=4,
                      scope='directed reduction activity epoch discriminator',
                      parent_provenance_sha256=prepare.sha(PARENT / 'provenance.json'),
                      parent_runtime_sha256={n: parent['files'][n]
                                             for n in ('startup.S', 'runtime.c', 'replay.ld')},
                      helper_sha256={n: prepare.sha(BASE / n) for n in ('prepare.py', 'run.py')})
    provenance['files'] = {str(p.relative_to(prepared)): prepare.sha(p)
                           for p in prepared.rglob('*') if p.is_file()}
    prepare.save(prepared / 'provenance.json', provenance)
    # Configure only the imported helper's in-memory case list, not its source.
    prepare.EXTENSIONS = NAMES
    prepare.ORACLE_MARKERS.update({n: 'EPOCH_PASS' for n in NAMES})
    for backend in ('soc', 'spike'):
        prepare.compile_programs(prepared, out / backend, CC, backend == 'spike')
    reference = out / 'reference'
    reference.mkdir()
    results = []
    for name in NAMES:
        command = [str(SPIKE), '--isa=rv64gcv_zvfh_zvl1024b', '-m2',
                   str(out / 'spike' / (name + '.elf'))]
        with (reference / (name + '.log')).open('w') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=90)
        results.append(dict(name=name, command=command, returncode=result.returncode,
                            status='PASS' if result.returncode == 0 else 'FAIL'))
    prepare.save(reference / 'results.json', dict(spike_sha256=prepare.sha(SPIKE), results=results))
    if any(r['returncode'] for r in results):
        raise RuntimeError('Spike Zvfh reference failed; do not launch SoC')
    print(json.dumps(results, indent=2))


def replay(build_dir, out):
    reference = json.loads((build_dir / 'reference/results.json').read_text())
    if any(r['status'] != 'PASS' for r in reference['results']):
        raise ValueError('Spike reference not passing')
    return checked.run_programs(SimpleNamespace(image=IMAGE, programs=build_dir / 'soc',
        case=['all'], jobs=1, timeout=90, execute=True, out=out))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'replay'])
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--build', type=Path)
    args = parser.parse_args()
    out = inside(args.out)
    if args.command == 'build':
        build(out)
        return 0
    return replay(inside(args.build), out)


if __name__ == '__main__':
    raise SystemExit(main())
