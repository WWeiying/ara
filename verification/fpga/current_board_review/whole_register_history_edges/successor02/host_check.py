#!/usr/bin/env python3
"""Replay existing59 Spike commit logs into the exact CSV oracle, no new simulation."""
from concurrent.futures import ProcessPoolExecutor
import copy
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
import driver as d


def rejected(checker, row, label):
    try:
        checker.row(row)
    except ValueError:
        return label
    raise ValueError('Negative not rejected: ' + label)


def run_case(case):
    k = d.checker(case, True)
    path = Path(case['elf']).with_name('spike.log')
    digest = d.sha(path)
    negatives = []
    for row in d.csv_adapter.spike_rows(path, k):
        if case['pair'] == 0:
            address = int(row['mem_addr'], 16)
            offset = address-k.s['output']
            n = len(k.calls)-1
            if row['mem_rmask'] != '0' and n == 1 and offset in (0, 32, 159, 1087):
                bad = dict(row, rd_wdata=f"{int(row['rd_wdata'],16)^1:x}")
                negatives.append(rejected(copy.deepcopy(k), bad, f'output_byte_{offset}'))
            pc = int(row['pc'], 16)
            if pc == k.s['op_1']:
                bad = copy.deepcopy(k)
                bad.vtype = 0
                negatives.append(rejected(bad, row, 'lost_predecessor_vtype'))
            if pc == k.targets['1']['pc']:
                bad = dict(row, insn=f"{int(row['insn'],16)^0x1000:08x}")
                negatives.append(rejected(copy.deepcopy(k), bad, 'changed_target'))
            if pc == k.targets['1']['pc']+4:
                bad = dict(row, rd_wdata='1')
                negatives.append(rejected(copy.deepcopy(k), bad, 'nonzero_final_vstart'))
        k.row(row)
    result = k.finish()
    if case['pair'] == 0:
        for label in ('skip_count', 'truncated_oracle', 'missing_exit'):
            bad = copy.deepcopy(k)
            if label == 'skip_count':
                bad.numbers[1] += 1
            elif label == 'truncated_oracle':
                bad.reads[1] -= 1
            else:
                bad.control = []
            try:
                bad.finish()
            except ValueError:
                negatives.append(label)
            else:
                raise ValueError('Negative not rejected: ' + label)
        d.require(len(negatives) == 10 and len(set(negatives)) == 10, 'Missing focused negatives')
    d.require(d.sha(path) == digest, 'Trace changed during host replay')
    return dict(pair=case['pair'], status='HOST_REFERENCE_CSV_PASS_NOT_DUT', analysis=result,
                negative_rejections=negatives, source_trace_sha256=digest)


def main():
    out = d.HERE/'host01'
    out.mkdir()
    plan = d.read(d.PREDECESSOR)
    d.require(d.sha(d.PREDECESSOR) == d.PREDECESSOR_SHA, 'Sealed plan changed')
    d.base.verify_pins(plan['pins'])
    results = []
    with ProcessPoolExecutor(max_workers=4) as pool:
        for result in pool.map(run_case, plan['cases']):
            results.append(result)
            d.save(out / f"pair{result['pair']:02d}.json", result)
            print('HOST_CSV_PAIR_PASS', result['pair'], flush=True)
    with (out/'tests.log').open('x') as log:
        subprocess.run(['/usr/bin/python3', '-B', str(d.HERE/'test_adapter.py')],
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
    d.base.verify_pins(plan['pins'])
    paths = [Path(__file__), d.HERE/'driver.py', d.HERE/'csv_adapter.py', d.HERE/'test_adapter.py',
             out/'tests.log', d.PREDECESSOR]
    paths += sorted(out.glob('pair??.json'))
    for c in plan['cases']:
        paths += [Path(c['elf']).with_name(n) for n in ('spike.dis', 'soc.dis')]
    pins = {**plan['pins'], **{str(p): d.sha(p) for p in paths}}
    d.save(out/'complete.json', dict(status='HOST_ALL59_CSV_AND_NEGATIVES_PASS_NOT_DUT',
         pairs=[r['pair'] for r in results], executed_calls=118,
         output_byte_checks=sum(sum(r['analysis']['output_byte_checks']) for r in results),
         negative_rejections=sum(len(r['negative_rejections']) for r in results),
         scope='Existing accepted Spike reference logs; no DUT/new Spike execution', pins=pins))
    print('HOST_ALL59_CSV_AND_NEGATIVES_PASS_NOT_DUT', flush=True)


if __name__ == '__main__':
    main()
