#!/usr/bin/env python3
"""Compare preserved runs and pair accepted FP operations with their raw flags."""
import argparse
from collections import defaultdict, deque
import csv
import json
from pathlib import Path


def read_rows(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def inspect(directory):
    results = read_rows(directory / 'results.csv')
    names = {row['id']: row['name'] for row in results}
    pending = defaultdict(deque)
    invalid_bus = []
    nv = []
    publish = []
    for row in read_rows(directory / 'trace.csv'):
        key = row['case_id'], row['lane']
        if row['flags_valid'] == '0' and int(row['flags'], 16):
            invalid_bus.append(row)
        if row['flags_valid'] == '1' and int(row['flags'], 16):
            publish.append({k: row[k] for k in ('case_id', 'cycle', 'lane', 'flags', 'done')})
        if row['out_valid'] == row['out_ready'] == '1':
            issued = pending[key].popleft()
            slots = int(row.get('raw_slots', row['raw_status']), 16)
            if any((slots >> (5 * slot)) & 16 for slot in range(4)):
                nv.append(dict(name=names[row['case_id']],
                    issue={k: issued[k] for k in ('cycle', 'lane', 'state', 'source_enable',
                        'source_count', 'issue_count', 'mask', 'a', 'b', 'c', 'issue_be',
                        'in_tag', 'in_control')},
                    output={k: row[k] for k in ('cycle', 'out_tag', 'raw_status',
                        'collapsed_status', 'gated_status')}, raw_slots=f'{slots:05x}'))
        if row['in_valid'] == row['in_ready'] == '1':
            pending[key].append(row)
    assert not any(pending.values()), 'Unconsumed accepted FP operation'
    return dict(cases=len(results), failures=[r for r in results if
                r['result_match'] != '1' or r['flags_match'] != '1'],
                invalid_flag_bus_samples=len(invalid_bus), nv_events=nv, publish=publish)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    before, after = inspect(args.before), inspect(args.after)
    b = {r['name']: r for r in read_rows(args.before / 'results.csv')}
    a = {r['name']: r for r in read_rows(args.after / 'results.csv')}
    assert a.keys() == b.keys(), 'Different case sets'
    report = dict(before=before, after=after,
        result_changes=[name for name in a if a[name]['result'] != b[name]['result']],
        cycle_changes=[name for name in a if a[name]['cycles'] != b[name]['cycles']],
        before_path=str(args.before.resolve()), after_path=str(args.after.resolve()))
    if args.out:
        args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('before', 'after')} |
        dict(before_cases=before['cases'], before_failures=len(before['failures']),
             after_cases=after['cases'], after_failures=len(after['failures']),
             invalid_flag_bus_samples=after['invalid_flag_bus_samples']), indent=2))
    return int(bool(after['failures'] or after['invalid_flag_bus_samples'] or
                    report['result_changes'] or report['cycle_changes']))


if __name__ == '__main__':
    raise SystemExit(main())
