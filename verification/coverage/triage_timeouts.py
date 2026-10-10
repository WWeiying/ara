#!/usr/bin/env python3
"""Read archived outcomes; summarize trace progress without rerunning RTL.

Unique PCs and retirement counts are observations, not a deadlock verdict.
Timeouts are not promoted to PASS by this report.
"""
import argparse
from collections import Counter, deque
import csv
import json
from pathlib import Path
import re


def analyze(outcome):
    files = outcome.get('files', {})
    traces = [Path(p) for p in files if p.endswith('/commit_trace.csv')]
    consoles = [Path(p) for p in files if p.endswith('/console.log')]
    result = {'name': outcome['name'], 'status': outcome['status'],
              'retirements': 0, 'traps': 0, 'trace': None}
    if len(traces) == 1:
        trace = traces[0]
        tail = deque(maxlen=1024)
        events = Counter()
        with trace.open() as stream:
            for row in csv.DictReader(stream):
                events[row['event']] += 1
                if row['event'] == 'retire':
                    if not result['retirements']:
                        result['first_cycle'] = int(row['cycle'])
                    result['retirements'] += 1
                    result['traps'] += int(row['trap'] != '0')
                    tail.append(row)
        result['trace'] = str(trace)
        result['events'] = dict(events)
        if tail:
            result.update(last_cycle=int(tail[-1]['cycle']), last_pc=tail[-1]['pc'],
                          tail_cycle_span=int(tail[-1]['cycle']) - int(tail[0]['cycle']),
                          tail_unique_pcs=len({r['pc'] for r in tail}),
                          tail_top_pcs=Counter(r['pc'] for r in tail).most_common(6))
    if len(consoles) == 1:
        lines = consoles[0].read_text(errors='replace').splitlines()
        result['console'] = str(consoles[0])
        result['console_tail'] = lines[-8:]
        result['failure_markers'] = [line for line in lines if re.search(
            r'\bFAIL(?:ED)?\b|\bFailure\s+#|\bUVM_FATAL\b(?!\s*:\s*0\b)', line)]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for path in sorted((args.campaign / 'outcomes').glob('*.json')):
        record = json.loads(path.read_text())
        if record['status'] != 'PASS':
            rows.append(analyze(record))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump({'campaign': str(args.campaign.resolve()), 'cases': rows}, stream, indent=2)
    for row in rows:
        print(row['name'], row['status'], 'retirements=', row['retirements'],
              'last_cycle=', row.get('last_cycle'), 'last_pc=', row.get('last_pc'),
              'tail_pcs=', row.get('tail_unique_pcs'),
              'failure_markers=', len(row.get('failure_markers', [])))


if __name__ == '__main__':
    main()
