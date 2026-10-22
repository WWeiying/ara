#!/usr/bin/env python3
"""Wait independently for the campaign, then compare same-ELF task cycles."""
import csv
import json
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out/main-aligned-600-20260930-01'
OLD = ROOT / 'verification/out/full-recollection-20260928-02'
BUILD = ROOT / 'verification/out/main-aligned-build-20260930-01'
SERVICE = 'ara-full-recollection-' + OUT.name + '.service'


def read(path):
    return json.loads(path.read_text())


def task_cycles(directory):
    candidates = [directory / 'work/console.log', directory / 'console.log']
    for path in candidates:
        if not path.is_file():
            continue
        values = re.findall(r'^\[PERF\] total_cycles\s*:\s*(\d+)\s*$',
                            path.read_text(errors='replace'), re.M)
        if len(values) == 1 and int(values[0]) > 0:
            return int(values[0])
    return None


def main():
    while True:
        result = subprocess.run(['systemctl', '--user', 'show', SERVICE,
                                 '--property=ActiveState', '--value'],
                                check=True, capture_output=True, text=True, timeout=10)
        if result.stdout.strip() not in ('active', 'activating'):
            break
        time.sleep(60)
    checkpoint = read(OUT / 'checkpoint.json') if (OUT / 'checkpoint.json').exists() else {}
    rows = []
    for path in sorted((OUT / 'outcomes').glob('*.json')):
        previous = OLD / 'outcomes' / path.name
        if not previous.is_file():
            continue
        new, old = read(path), read(previous)
        if new.get('elf_sha256') != old.get('elf_sha256'):
            raise RuntimeError('Different ELFs: ' + path.name)
        name = new['name']
        before = task_cycles(OLD / 'results' / name)
        after = task_cycles(OUT / 'results' / name)
        comparable = old['status'] == new['status'] == 'PASS' and before is not None and after is not None
        rows.append({'name': name, 'old_status': old['status'], 'new_status': new['status'],
                     'old_cycles': before, 'new_cycles': after,
                     'delta_cycles': after - before if comparable else None,
                     'ratio': after / before if comparable else None})
    target = BUILD / 'cycle-comparison.csv'
    with target.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['name', 'old_status', 'new_status',
                                'old_cycles', 'new_cycles', 'delta_cycles', 'ratio'])
        writer.writeheader()
        writer.writerows(rows)
    report = {'campaign_status': checkpoint.get('status', 'NOT_DISPATCHED'),
              'completed': checkpoint.get('completed', 0), 'comparison_rows': len(rows),
              'task_cycle_comparisons': sum(r['ratio'] is not None for r in rows),
              'slower_cases': [r for r in rows if r['ratio'] is not None and r['ratio'] > 1],
              'mvp_qualification': 'FAIL_NOT_USED_BY_THMULTI',
              'scope': 'Functional and task-cycle evidence; no synthesis/PPA qualification'}
    (BUILD / 'evaluation.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if checkpoint.get('status') == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
