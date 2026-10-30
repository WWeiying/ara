#!/usr/bin/env python3
"""Attribute an already accepted four-trial projection log, without rerunning RTL."""
import argparse
import hashlib
import json
from pathlib import Path

PHASES = ['setup', 'activation', 'weight', 'compute', 'overlap', 'drain',
          'scheduler', 'commit', 'fault', 'terminal']
COUNTERS = ['busy_cycles', 'activation_bytes', 'weight_bytes', 'dot_active_cycles',
            'useful_pairs', 'pair_capacity', 'fp_uop_issue', 'fp_table_full_cycles',
            'probe_fp_busy_cycles', 'probe_fp_no_schedulable_uop_cycles']
COUNTERS += ['phase_'+name+'_cycles' for name in PHASES]


def require(ok, why):
    if not ok:
        raise ValueError(why)


def fields(text):
    pairs = [item.partition('=') for item in text.split()]
    require(all(sep and value for _, sep, value in pairs), 'Malformed record')
    result = {key: value for key, _, value in pairs}
    require(len(result) == len(pairs), 'Duplicate field')
    return result


def analyze(text):
    pending, trials = [], []
    sequence = 0
    for line in text.splitlines():
        if line.startswith('[QBS_PERF] '):
            values = fields(line[len('[QBS_PERF] '):])
            row = {key: int(value) for key, value in values.items()}
            sequence += 1
            require(row['seq'] == sequence and row['success'] == 1 and row['fault'] == 0,
                    'Nonsequential or unsuccessful command')
            require((row['m'], row['n'], row['vlen'], row['lanes']) == (4, 32, 1024, 4),
                    'Wrong command shape')
            require(all(row[key] >= 0 for key in COUNTERS), 'Negative counter')
            require(sum(row['phase_'+p+'_cycles'] for p in PHASES) == row['busy_cycles'],
                    'Exclusive phases do not partition busy time')
            pending.append(row)
        elif line.startswith('Q8K_CURRENT_TRIAL '):
            trial = fields(line[len('Q8K_CURRENT_TRIAL '):])
            require(int(trial['id']) == len(trials) and int(trial['commands']) == len(pending) == 48
                    and trial['errors'] == '0', 'Trial/command association failed')
            row = dict(id=len(trials), path=trial['path'], commands=len(pending))
            row.update({key: int(trial[key]) for key in ('admit', 'prep', 'execute', 'total')})
            row.update({key: sum(command[key] for command in pending) for key in COUNTERS})
            require(row['total'] == row['admit']+row['prep']+row['execute'], 'Timer partition')
            require(row['execute'] >= row['busy_cycles'], 'Busy interval exceeds execution timer')
            row['execute_outside_engine'] = row['execute']-row['busy_cycles']
            trials.append(row)
            pending = []
    require(not pending and len(trials) == 4 and sequence == 192, 'Incomplete ABBA')
    require(trials[0]['path'] == trials[3]['path'] and trials[1]['path'] == trials[2]['path'] and
            trials[0]['path'] != trials[1]['path'], 'Not paired ABBA')
    sums = {}
    for path in dict.fromkeys(row['path'] for row in trials):
        keys = set(trials[0])-{'id', 'path'}
        row = {key: sum(t[key] for t in trials if t['path'] == path) for key in keys}
        row['busy_fraction_execute'] = row['busy_cycles']/row['execute']
        row['prep_fraction_total'] = row['prep']/row['total']
        row['outside_engine_fraction_total'] = row['execute_outside_engine']/row['total']
        sums[path] = row
    return dict(trials=trials, sums=sums,
                scope='Accepted projection slice, not whole model or physical compute utilization',
                outside_engine='Residual includes SDK, instruction issue/retirement, output stores and probes; not pure software',
                overlap='Compute phase while read engine is busy or weight range is valid; not proven useful bandwidth overlap',
                pair_capacity='Capacity on dot issue cycles only; not all-cycle compute utilization')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    receipt = json.loads(args.receipt.read_text())
    data = args.log.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    require(receipt['state'] == 'PASS' and receipt['log_sha256'] == sha, 'Unaccepted source log')
    result = analyze(data.decode())
    require([row['total'] for row in result['trials']] == receipt['total_cycles'], 'Receipt totals differ')
    result.update(log_sha256=sha, acceptance_receipt=str(args.receipt.resolve()))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
