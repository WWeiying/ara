#!/usr/bin/env python3
"""Plan and run exactly three original matrix ELFs against sealed final04."""
import argparse
import csv
import json
from pathlib import Path
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from adapter import HERE, BASE, SPIKE, prepare, inside

IMAGE = Path('/home/wangwy/fpga_runs/current_board_integration_final04/campaign/image')
OLD = IMAGE.parent / 'extension-matrix'
MATRIX = HERE / 'matrix01'
NAMES = ['extension_e32_m4_vf4', 'extension_e64_m4_vf4', 'extension_e64_m8_vf8']


def plan(out):
    out.mkdir(parents=True, exist_ok=False)
    manifest = MATRIX / 'soc/programs.json'
    programs = json.loads(manifest.read_text())['programs']
    original = {r['name']: r for r in json.loads((OLD / 'summary.json').read_text())}
    pins = {str(p): prepare.sha(p) for p in (manifest, IMAGE / 'image.json',
            Path(json.loads((IMAGE / 'image.json').read_text())['simv']),
            BASE / 'run.py', BASE / 'prepare.py', Path(__file__))}
    estimates = []
    for name in NAMES:
        elf = Path(programs[name]['path'])
        assert prepare.sha(elf) == prepare.sha(OLD / 'tests' / name / 'input.elf') == programs[name]['sha256']
        pins[str(elf)] = prepare.sha(elf)
        with (OLD / 'tests' / name / 'commit_trace.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        retired = [r for r in rows if r['event'] == 'retire']
        stores = [r for r in retired if r['insn'] in ('62858c27', 'e2858c27')]
        log = (OLD / 'tests' / name / 'console.log').read_text()
        trials = list(map(int, re.findall(r'EXTENSION_TRIAL (\d+)', log)))
        assert not any(m in log for m in ('EXTENSION_MATRIX_FAIL', 'REPLAY_MISMATCH'))
        refcmd = (MATRIX / (name + '.cmd')).read_text().replace('reg 0 a0\n', 'reg 0 minstret\nreg 0 a0\n')
        cmdfile = out / (name + '.cmd')
        cmdfile.write_text(refcmd)
        command = [str(SPIKE), '-d', '--debug-cmd=' + str(cmdfile),
                   '--isa=rv64gcv_zvl1024b', '-m2', str(MATRIX / 'spike' / (name + '.elf'))]
        with (out / (name + '.spike.log')).open('w') as logstream:
            rc = subprocess.run(command, stdout=logstream, stderr=subprocess.STDOUT, timeout=30).returncode
        ref = (out / (name + '.spike.log')).read_text()
        numbers = re.findall(r'^0x([0-9a-f]+)$', ref, re.M)
        assert rc == 0 and 'EXTENSION_MATRIX_PASS' in ref and len(numbers) >= 2
        instret = int(numbers[0], 16)
        elapsed = original[name]['elapsed_s']
        projected = elapsed * 24 / len(stores)
        estimates.append(dict(name=name, old_status=original[name]['status'],
            old_elapsed_s=elapsed, last_trace_cycle=int(rows[-1]['cycle']),
            retired_instructions=len(retired), retired_readback_stores=len(stores),
            last_console_trial=trials[-1], reference_total_minstret=instret,
            reference_scope='Spike runtime sibling, not UART SoC instruction count',
            reference_command=command, linear_store_progress_projection_s=projected,
            cycle_projection_from_retired_stores=int(int(rows[-1]['cycle'])*24/len(stores)),
            timeout_s=1200, original_elf_sha256=pins[str(elf)]))
    command = [sys.executable, '-B', str(BASE / 'run.py'), 'run', '--image', str(IMAGE),
        '--programs', str(MATRIX / 'soc'), '--out', str(out / 'replay'), '--jobs', '3',
        '--timeout', '1200', '--execute']
    for name in NAMES:
        command += ['--case', name]
    prepare.save(out / 'plan.json', dict(command=command, pins=pins, estimates=estimates,
        no_build=True, same_three_elves=True, jobs=3, timeout_s=1200,
        bound='24/retired-store extrapolation plus UART/host-load margin; largest ~971s, choose1200 not900',
        limitations='progress estimate not deadlock proof; no retries or automatic extensions; single is not whole PASS'))
    print(json.dumps(estimates, indent=2))


def work(out):
    data = json.loads((out / 'plan.json').read_text())
    for name, sha in data['pins'].items():
        assert prepare.sha(Path(name)) == sha, name
    began = time.time()
    prepare.save(out / 'status.json', dict(status='RUNNING', started=began, command=data['command']))
    with (out / 'replay.log').open('w') as log:
        rc = subprocess.run(data['command'], stdout=log, stderr=subprocess.STDOUT).returncode
    summary = out / 'replay/summary.json'
    rows = json.loads(summary.read_text()) if summary.exists() else []
    unchanged = all(prepare.sha(Path(name)) == sha for name, sha in data['pins'].items())
    prepare.save(out / 'status.json', dict(status='PASS' if rc == 0 and len(rows) == 3
        and all(r['status'] == 'PASS' for r in rows) and unchanged else 'FAIL',
        started=began, ended=time.time(), returncode=rc, results=rows,
        pins_unchanged=unchanged, no_build=True, original_results_preserved=True))


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=['plan', 'work'])
    cli.add_argument('--out', type=Path, required=True)
    args = cli.parse_args()
    (plan if args.mode == 'plan' else work)(inside(args.out))
