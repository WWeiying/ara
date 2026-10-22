#!/usr/bin/env python3
"""Classify completed smoke cases without relabeling expected RTL failures."""
import argparse
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('run', type=Path)
    args = cli.parse_args()
    out = args.run.resolve()
    if not out.is_relative_to(HERE):
        raise ValueError('owned output only')
    summary = json.loads((out / 'summary.json').read_text())
    points = json.loads((HERE / 'prepared_smoke/provenance.json').read_text())['points']
    rows = []
    for entry in summary:
        name = entry['name']
        log = (out / 'tests' / name / 'console.log').read_text()
        details = []
        for line in log.splitlines():
            if line.startswith('MATRIX_DETAIL '):
                details.append({k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', line)})
        ends = re.findall(r'SMOKE_(PASS|FAIL) sew=(\d+) cases=(\d+) errors=(\d+)', log)
        complete = len(ends) == 1 and int(ends[0][2]) == len(points)
        if complete:
            if int(ends[0][3]) != sum(d['data'] + d['setup'] + (d['vstart'] != 0) +
                                      (d['actual_flags'] != d['expected_flags']) for d in details):
                raise ValueError('detail/summary mismatch')
        cases = []
        for op, kind, side, mode in points:
            matches = [d for d in details if (d['op'], d['kind'], d['side'], d['mode']) == (op, kind, side, mode)]
            if len(matches) > 1:
                raise ValueError('duplicate detail')
            result = dict(op=op, kind=kind, side=side, mode=mode,
                          status='FAIL' if matches else 'PASS' if complete else 'UNPROVEN')
            if matches:
                result.update(matches[0])
                d = matches[0]
                result['classification'] = ('flags_only' if not (d['data'] or d['setup'] or d['vstart'])
                                            else 'data_or_setup_requires_review')
            cases.append(result)
        rows.append(dict(program=name, runner_status=entry['status'], complete=complete, cases=cases))
    (out / 'classified.json').write_text(json.dumps(rows, indent=2) + '\n')
    for row in rows:
        counts = {s: sum(c['status'] == s for c in row['cases']) for s in ('PASS', 'FAIL', 'UNPROVEN')}
        print(row['program'], counts)
        for case in row['cases']:
            if case['status'] == 'FAIL':
                print(json.dumps(case))


if __name__ == '__main__':
    main()
