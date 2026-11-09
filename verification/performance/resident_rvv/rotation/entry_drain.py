#!/usr/bin/env python3
"""Measure old VID lifetimes at accepted PV entry; not a new-RTL prediction."""
import argparse
import hashlib
import json
from pathlib import Path

import attribution


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def drain_at(instructions, cycle):
    # A done at this edge has no remaining whole cycle; no arbitrary drain delay.
    live = [dict(item) for item in instructions
            if item['alloc'] < cycle < item['done']]
    return dict(cycle=cycle, older_live=live,
                observed_remaining_cycles=max([x['done']-cycle for x in live], default=0))


def analyze(run, previous):
    receipt = json.loads(previous.read_text())
    raw = run/'result.json'
    if receipt['acceptance']['raw_receipt_sha256'] != sha(raw):
        raise ValueError('Accepted run identity changed')
    raw_data = json.loads(raw.read_text())
    vector = run/'work/vector_trace.csv'
    if raw_data['artifacts'].get(str(vector)) != sha(vector):
        raise ValueError('Unaccepted vector trace')
    for path, expected in receipt['artifacts'].items():
        if sha(Path(path)) != expected:
            raise ValueError('Attribution artifact drift: '+path)
    instructions = attribution.lifetimes(vector)
    samples = []
    for trial in receipt['trials']:
        for index, tile in enumerate(trial['pv_tiles']):
            first = tile['groups'][0][0]
            samples.append(dict(trial=trial['trial'], arm=trial['arm'], tile=index,
                                tokens=tile['rows'],
                                helper_entry=drain_at(instructions, tile['begin']),
                                first_replay_entry=drain_at(instructions, first['alloc'])))
    return dict(state='OBSERVED_ENTRY_LIFETIMES', samples=samples,
                limits='Old schedule only; VID completion is not proof that all operand '
                       'queues, registered native pulses or physical FPU outputs are empty. '
                       'New RTL must use explicit readiness/drain, not these cycle values.',
                artifacts={str(path): sha(path) for path in
                           (raw, vector, previous, Path(__file__), Path(attribution.__file__))})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--attribution', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.run.resolve(), args.attribution.resolve())
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    for row in result['samples']:
        print('trial={} arm={} tile={} T={} entry={} replay={}'.format(
            row['trial'], row['arm'], row['tile'], row['tokens'],
            row['helper_entry']['observed_remaining_cycles'],
            row['first_replay_entry']['observed_remaining_cycles']))
