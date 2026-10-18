#!/usr/bin/env python3
"""Collect concurrent ordered-adder demand from completed architectural tests.

No inference of final area, interconnect timing or alternate scheduling speed.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('regression', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.regression / 'manifest.json').read_text())
    names = [test['app'] for test in manifest['tests']]
    inputs = {path.name for path in (args.regression / 'inputs').iterdir() if path.is_file()}
    if not inputs or len(names) != len(set(names)) or set(names) != inputs:
        raise ValueError('Profile suite incomplete or contains duplicate tests')
    if 'expected_apps' in manifest and set(names) != set(manifest['expected_apps']):
        raise ValueError('Profile suite differs from declared expected apps')
    rows = []
    for test in manifest['tests']:
        elf = args.regression / 'inputs' / test['app']
        if hashlib.sha256(elf.read_bytes()).hexdigest() != test['elf_sha256']:
            raise ValueError('Frozen ELF hash mismatch: ' + test['app'])
        if not test['pass']:
            raise ValueError('Unsuccessful test: ' + test['app'])
        path = args.regression / test['app'] / 'stdout.log'
        text = path.read_text()
        summaries = re.findall(r'\[AREA_ORDERED_SUMMARY\] lane=(\d+) descriptor_bits=(\d+) requests=(\d+) accepted=(\d+) blocked=(\d+) responses=(\d+)', text)
        if len(summaries) != 4 or {int(s[0]) for s in summaries} != set(range(4)):
            raise ValueError('Missing four-lane observer summaries: ' + test['app'])
        requests = defaultdict(list)
        accepted = defaultdict(list)
        for cycle, lane, owner, fire in re.findall(r'\[AREA_ORDERED\] cycle=(\d+) lane=(\d+) id=(\d+) fire=(\d+)', text):
            requests[int(cycle)].append((int(lane), int(owner)))
            if int(fire):
                accepted[int(cycle)].append((int(lane), int(owner)))
        assert sum(len(v) for v in requests.values()) == sum(int(s[2]) for s in summaries)
        assert sum(len(v) for v in accepted.values()) == sum(int(s[3]) for s in summaries)
        assert all(len(v) == len({lane for lane, owner in v}) for v in requests.values())
        rows.append({
            'app': test['app'], 'elf_sha256': test['elf_sha256'],
            'log_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'requests_by_lane': [list(map(int, s)) for s in sorted(summaries)],
            'summary_columns': ['lane','descriptor_bits','requests','accepted','blocked','responses'],
            'request_concurrency_histogram': dict(sorted(Counter(map(len, requests.values())).items())),
            'accepted_concurrency_histogram': dict(sorted(Counter(map(len, accepted.values())).items())),
            'cycles_with_multiple_requests': sum(len(v) > 1 for v in requests.values()),
            'cycles_with_multiple_owners': sum(len({owner for lane, owner in v}) > 1 for v in requests.values()),
            'ordered_trace_available': bool(requests),
        })
    result = {'scope': 'whole-test accepted/request demand; not alternate-design performance or Fmax', 'tests': rows}
    with args.out.open('x') as output:
        json.dump(result, output, indent=2)
        output.write('\n')
    for row in rows:
        print(row['app'], row['request_concurrency_histogram'], row['cycles_with_multiple_owners'])


if __name__ == '__main__':
    main()
