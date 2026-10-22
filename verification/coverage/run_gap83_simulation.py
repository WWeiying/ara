#!/usr/bin/env python3
"""Run one frozen-image simulation; completion is not PASS admission."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
ELF_SHA = '302adc8bc67502a9c4a94d52ef07afb89c914a2e4b26d7e11bf9a3e14d414c9f'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve(strict=True)
    if output.parent != ROOT / 'verification/out' or any(output.iterdir()):
        raise ValueError('Existing empty independent output directory required')
    planfile = ROOT / 'verification/out/closure90-current-20261005-01/plan.json'
    plan = json.loads(planfile.read_bytes())
    elf = ROOT / 'verification/out/gap83-midmant-preflight-20261006-01/input.elf'
    if digest(elf) != ELF_SHA:
        raise ValueError('Preflight ELF changed')
    pins = dict(plan['image'])
    for path in [elf, planfile, Path(__file__), ROOT / 'apps/riscv-tests/isa/rv64uv/vgap83_midmant16.c',
                 ROOT / 'verification/out/gap83-midmant-preflight-20261006-01/spike.trace']:
        pins[str(path)] = digest(path)
    def check():
        for name, expected in pins.items():
            if digest(Path(name)) != expected:
                raise ValueError('Input or frozen image changed: ' + name)
    check()
    command = [plan['simv'], '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
               '+PRELOAD=' + str(elf), '+TESTCASE=vgap83_midmant16', '+COMMIT_TOHOST=80001000',
               '+COMMIT_TRACE=' + str(output / 'commit_trace.csv'),
               '+VECTOR_TRACE=' + str(output / 'vector_trace.csv'), '-cm',
               'line+cond+fsm+tgl+branch', '-cm_dir', str(output / 'code.vdb'),
               '-cm_name', 'vgap83_midmant16']
    save(output / 'manifest.json', dict(pins=pins, command=command, timeout_s=600,
         coverage_admitted=False, rtl_changed=False))
    try:
        with (output / 'console.log').open('x') as log:
            result = subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=600, check=True)
        check()
        save(output / 'simulation-status.json', dict(status='SIMULATION_EXITED_NOT_ADMITTED',
             returncode=result.returncode, coverage_admitted=False))
    except Exception as error:
        save(output / 'simulation-status.json', dict(status='SIMULATION_NOT_ADMITTED',
             reason=f'{type(error).__name__}: {error}', coverage_admitted=False))
        raise


if __name__ == '__main__':
    main()
