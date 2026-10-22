#!/usr/bin/env python3
"""Reproduce RED32's unsealed old software trace with its sealed Spike and ELF."""
import argparse
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'verification'), str(ROOT / 'verification/coverage')]
from audit_probe_semantics_20261015 import read, require, save, sha
from ara_verify.spike_trace import parse_spike_commits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    old = ROOT / 'verification/out/gap76-old-image-20261006-01'
    work = old / 'results/vgap76_red32'
    book = read(old / 'source-pins.json')
    command = read(work / 'spike.command.json')['command']
    expected = ['--isa=rv64gcv_zfh_zvfh_zvl1024b', '--priv=msu', '--pmpregions=0', '-l', '--log-commits']
    require(command[1:-1] == expected and command[-1] == str(work / 'input.elf'), 'Exact original reference command required')
    pins = {str(old / 'source-pins.json'): sha(old / 'source-pins.json'),
            str(work / 'spike.command.json'): sha(work / 'spike.command.json')}
    for name in (command[0], command[-1]):
        require(sha(name) == book[name], 'Original independent binary/input pin changed')
        pins[name] = book[name]
    started = time.time()
    with (output / 'spike.stdout').open('x') as stdout, (output / 'spike.trace').open('x') as stderr:
        result = subprocess.run(command, cwd=output, stdout=stdout, stderr=stderr, timeout=120)
    receipt = dict(command=command, cwd=str(output), returncode=result.returncode,
                   started=started, finished=time.time(), input_pins=pins)
    save(output / 'execution.json', receipt)
    require(result.returncode == 0, 'Independent software reference did not complete successfully')
    original = parse_spike_commits(work / 'spike.trace')
    reproduced = parse_spike_commits(output / 'spike.trace')
    require(len(original) == len(reproduced) > 0, 'Reference commit population changed')
    for i, (a, b) in enumerate(zip(original, reproduced)):
        require(a == b, 'Independent regenerated reference differs at commit ' + str(i))
    for name, digest in pins.items():
        require(sha(name) == digest, 'Reference input changed during execution')
    save(output / 'audit.json', dict(status='PASS', commits=len(original),
        original_trace=str(work / 'spike.trace'), original_trace_sha256=sha(work / 'spike.trace'),
        reproduced_trace=str(output / 'spike.trace'), reproduced_trace_sha256=sha(output / 'spike.trace'),
        exact_all_parsed_commit_fields=True, input_pins=pins, receipt=receipt,
        RTL_simulation_started=False, historical_PASS_reused=False))
    print('PASS', len(original), 'independently reproduced reference commits', flush=True)


if __name__ == '__main__':
    main()
