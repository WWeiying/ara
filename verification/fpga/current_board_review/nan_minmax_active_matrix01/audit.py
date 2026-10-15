#!/usr/bin/env python3
"""Offline public-stimulus/accepted-probe checks for this completed campaign."""
import collections
import csv
import json
from pathlib import Path
import run

P = Path(__file__).resolve().parent / 'run01'
suite = json.loads((P/'cases.json').read_text())
pins = json.loads((P/'pins.json').read_text())
for name, pin in pins.items():
    assert run.sha(P/'inputs'/name) == pin['sha256'], name
    if name.startswith('hardware/'):
        assert run.sha(run.ROOT/name) == pin['sha256'], name
status = json.loads((P/'status.json').read_text())
assert status['state'] == 'PASS_84_REAL_RTL_NAN_MINMAX'
answer = {'state': 'PASS_ACCEPTED_PROBES_AND_INPUTS', 'topologies': [], 'hashes': {}}
for lanes in (4, 1):
    work = P/f'lane{lanes}'
    events = collections.defaultdict(dict)
    fed = collections.Counter()
    ntr_checks = 0
    for r in csv.DictReader((work/'probe.csv').open()):
        cid, lane = int(r['case_id']), int(r['lane'])
        c = suite[cid]
        width = c['width']
        mask = (1 << width) - 1
        slots = 64 // width
        canon = {16: 0x7e00, 32: 0x7fc00000, 64: 0x7ff8000000000000}[width]
        ntr = sum(canon << (j * width) for j in range(slots))
        if r['seed_push'] == '1':
            assert int(r['seed_input'], 16) == c['seed']
        if r['source_push'] == '1':
            word = int(r['source_input'], 16)
            for element in range(slots):
                bits = (slots-1).bit_length()
                physical = int(f'{element:0{bits}b}'[::-1], 2) if bits else 0
                index = (fed[cid, lane] * slots + element) * lanes + lane
                expected = run.source(width, c['pattern'], index)
                assert (word >> (physical * width)) & mask == expected, (lanes, cid, lane, index)
            fed[cid, lane] += 1
        if r['source_fire'] == '1' or r['seed_fire'] == '1':
            assert int(r['ntr'], 16) == ntr, (lanes, cid, r)
            ntr_checks += 1
        if r['seed_fire'] == '1':
            observed = int(r['queue_seed'], 16)
            assert observed & mask == (c['seed'] if lane == 0 else canon)
        if r['wb_fire'] == '1':
            assert lane == 0
            assert int(r['epoch_active']) == int(any(c['active']))
            assert int(r['seed_q'], 16) & mask == c['seed']
            assert int(r['wb_data'], 16) & mask == c['expected']
            assert int(r['wb_be'], 16) == (1 << (width//8)) - 1
            assert 'write_cycle' not in events[cid]
            events[cid].update(name=c['name'], write_cycle=int(r['cycle']),
                               epoch=int(r['epoch_active']), wb_data=r['wb_data'],
                               seed=r['seed_q'], be=r['wb_be'])
    for c in suite:
        for lane in range(lanes):
            local = (c['vl'] + lanes - 1 - lane) // lanes
            slots = 64 // c['width']
            assert fed[c['id'], lane] == (local + slots - 1) // slots
    for r in csv.DictReader((work/'trace.csv').open()):
        cid = int(r['case_id'])
        e = events[cid]
        if r['out_valid'] == r['out_ready'] == '1' and int(r['gated_status'], 16) & 16:
            e.setdefault('first_raw_nv_cycle', int(r['cycle']))
        if r['flags_valid'] == '1':
            e.setdefault('flag_pulses', []).append([int(r['cycle']), int(r['lane']), r['flags']])
    assert len(events) == len(suite)
    for c in suite:
        pulses = events[c['id']]['flag_pulses']
        assert sorted(p[1] for p in pulses) == list(range(lanes))
        flags = 0
        for pulse in pulses:
            flags |= int(pulse[2], 16)
        assert flags == c['flags']
    answer['topologies'].append(dict(lanes=lanes, cases=len(events),
                                     accepted_ntr_checks=ntr_checks, events=dict(events)))
    for name in ('results.csv', 'run.console.log', 'probe.csv', 'trace.csv'):
        answer['hashes'][f'lane{lanes}/{name}'] = run.sha(work/name)
for name in ('status.json', 'cases.json', 'pins.json', 'inputs/test/reduction_tb.sv'):
    answer['hashes'][name] = run.sha(P/name)
dest = P/'probe_audit.json'
with dest.open('x') as stream:
    json.dump(answer, stream, indent=2)
    stream.write('\n')
for t in answer['topologies']:
    print('lane', t['lanes'], 'cases', t['cases'], 'accepted_ntr', t['accepted_ntr_checks'])
    for cid in (0, 3, 11, 21, 27, 39):
        print(t['events'][cid])
print('audit SHA', run.sha(dest))
