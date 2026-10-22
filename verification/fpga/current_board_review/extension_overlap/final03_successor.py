#!/usr/bin/env python3
"""Independent same-image replay service; no source edits or build commands."""
import argparse
import csv
import json
from pathlib import Path
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from adapter import HERE, BASE, IMAGE, inside, prepare

CAMPAIGN = IMAGE.parent
COMPARISON = HERE.parent / 'comparison/soc_matrix'
TASKS = [
    ('flags-sequence', Path('/tmp/current-board-flags-sequence02/soc'), 'flags_sequence'),
    ('reduction-epoch', HERE.parent / 'reduction_epoch/measurement01/soc', 'all'),
    ('matrix-e32', COMPARISON, 'matrix_e32'),
    ('matrix-e16', COMPARISON, 'matrix_e16'),
]


def progress(sew):
    name = f'matrix_e{sew}'
    original = CAMPAIGN / 'comparison-matrix/tests' / name
    dis = COMPARISON / (name + '.dis')
    entry = int(re.search(r'([0-9a-f]+) <run>:', dis.read_text())[1], 16)
    regs = {i: 0 for i in range(32)}
    trials, count, last = [], 0, None
    with (original / 'commit_trace.csv').open() as stream:
        for row in csv.DictReader(stream):
            if row['event'] != 'retire' or not row.get('trap'):
                continue
            if int(row['pc'], 16) == entry:
                trials.append(dict(cycle=int(row['cycle']), op=regs[10],
                    kind=regs[11], side=regs[12], mode=regs[13]))
            if row['rd'] != '0':
                regs[int(row['rd'])] = int(row['rd_wdata'], 16)
            count += 1
            last = row
    log = (original / 'console.log').read_text()
    return dict(original=str(original), run_entry=hex(entry),
        started_trials=len(trials), total_trials=102 if sew == 16 else 100,
        last_trials=trials[-5:], retirements=count, last_retire=last,
        error_detail_seen='MATRIX_DETAIL' in log or 'MATRIX_FAIL' in log,
        trace_sha256=prepare.sha(original / 'commit_trace.csv'),
        disassembly_sha256=prepare.sha(dis), console_sha256=prepare.sha(original / 'console.log'))


def plan(out):
    out.mkdir(parents=True, exist_ok=False)
    evidence = {str(sew): progress(sew) for sew in (16, 32, 64)}
    if evidence['16']['started_trials'] < 54 or evidence['32']['started_trials'] < 81:
        raise ValueError('expected progress evidence absent; no blind timeout increase')
    if any(evidence[str(s)]['error_detail_seen'] for s in (16, 32)):
        raise ValueError('architectural error requires investigation, not longer runtime')
    pins = {str(IMAGE / 'image.json'): prepare.sha(IMAGE / 'image.json'),
            str(BASE / 'run.py'): prepare.sha(BASE / 'run.py'),
            str(BASE / 'prepare.py'): prepare.sha(BASE / 'prepare.py')}
    tasks = []
    for label, programs, name in TASKS:
        manifest_path = programs / 'programs.json'
        data = json.loads(manifest_path.read_text())
        entry = data['programs'][name]
        elf = Path(entry['path'])
        if prepare.sha(elf) != entry['sha256']:
            raise ValueError('ELF drift: ' + name)
        if name.startswith('matrix_'):
            old = CAMPAIGN / 'comparison-matrix/tests' / name / 'input.elf'
            if prepare.sha(old) != entry['sha256']:
                raise ValueError('successor ELF is not the previous input')
        pins[str(manifest_path)] = prepare.sha(manifest_path)
        pins[str(elf)] = entry['sha256']
        cmd = [sys.executable, '-B', str(BASE / 'run.py'), 'run',
            '--image', str(IMAGE), '--programs', str(programs),
            '--out', str(out / label), '--jobs', '1', '--timeout', '600',
            '--execute', '--case', name]
        tasks.append(dict(name=label, case=name, argv=cmd, elf_sha256=entry['sha256'],
                          status='NOT_RUN'))
    prepare.save(out / 'progress_evidence.json', evidence)
    prepare.save(out / 'plan.json', dict(tasks=tasks, inputs_sha256=pins,
        original_status_preserved=True, new_build=False, rtl_edits=False,
        rationale='ongoing scalar setup; e32 trial81/100, e16 trial54/102; e64 PASS at285s',
        original_campaign_status_sha256=prepare.sha(CAMPAIGN / 'status.json')))
    print(out / 'plan.json')


def work(out):
    data = json.loads((out / 'plan.json').read_text())
    began = time.time()
    for task in data['tasks']:
        for path, digest in data['inputs_sha256'].items():
            if prepare.sha(Path(path)) != digest:
                raise ValueError('input drift: ' + path)
        task['status'] = 'RUNNING'
        prepare.save(out / 'status.json', dict(started=began, tasks=data['tasks']))
        with (out / (task['name'] + '.log')).open('w') as log:
            result = subprocess.run(task['argv'], stdout=log, stderr=subprocess.STDOUT)
        task['returncode'] = result.returncode
        summary = out / task['name'] / 'summary.json'
        task['results'] = json.loads(summary.read_text()) if summary.is_file() else []
        task['status'] = 'PASS' if result.returncode == 0 and task['results'] and all(
            r['status'] == 'PASS' for r in task['results']) else 'FAIL'
        prepare.save(out / 'status.json', dict(started=began, tasks=data['tasks']))
    final = dict(started=began, finished=time.time(), tasks=data['tasks'],
        status='PASS' if all(t['status'] == 'PASS' for t in data['tasks']) else 'FAIL',
        no_build=True, original_status_preserved=True)
    prepare.save(out / 'status.json', final)
    print(json.dumps(final, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['plan', 'work'])
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    (plan if args.command == 'plan' else work)(inside(args.out))
