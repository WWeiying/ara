#!/usr/bin/env python3
"""Compose the reviewed timeout successors without editing earlier evidence."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    delivery = OUT / 'gap36-timeout-successors-20261004-03'
    successors = delivery / 'selection-draft.json'
    retry = OUT / 'gap36-timeout-analysis-20261004-01/selection.pending.json'
    for filename in ('input-hashes.json', 'artifact-hashes.json'):
        for path, expected in read(delivery / filename).items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
                raise ValueError('Delivery changed: ' + path)
    selected, qbs = read(successors), read(retry)
    if any(selected[k] != qbs[k] for k in ('baseline', 'baseline_bits')):
        raise ValueError('Different coverage baselines')
    if read(delivery / 'checked-prechecks.json')['status'] != 'PASS':
        raise ValueError('Incomplete successor precheck')
    selected['cases'] += qbs['cases']
    if len(selected['cases']) != 8 or len({c['name'] for c in selected['cases']}) != 8:
        raise ValueError('Wrong or duplicate case set')
    if any(not 0 < c['timeout_s'] <= 600 for c in selected['cases']):
        raise ValueError('Unbounded case')
    selected['composition'] = dict(successors=str(successors), retry=str(retry),
        rtl_changes=False, failed_vdb_reuse=False,
        contract='Original carry checks and AKV mutations preserved; QBS identical ELF')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(selected, stream, indent=2)
        stream.write('\n')
    print(args.output)


if __name__ == '__main__':
    main()
