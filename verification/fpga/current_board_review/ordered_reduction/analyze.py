#!/usr/bin/env python3
"""Check accepted trace transactions and compare frozen reduced-run evidence."""
import argparse
from collections import defaultdict, deque
import csv
import json
from pathlib import Path


def read_csv(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def inspect(path):
    suite = json.loads((path / 'cases.json').read_text())
    rows = read_csv(path / 'results.csv')
    assert [r['name'] for r in rows] == [c['name'] for c in suite]
    pending = defaultdict(deque)
    flags_pending = {}
    counts = defaultdict(int)
    witnesses = []
    transfers = defaultdict(int)
    for event in read_csv(path / 'trace.csv'):
        cid, cycle, lane = (int(event[k]) for k in ('case_id', 'cycle', 'lane'))
        case = suite[cid]
        key = cid, lane
        if event['in_valid'] == event['in_ready'] == '1':
            index = transfers[cid]
            assert lane == index % 4, ('wrong lane order', event, index)
            assert int(event['local_index']) == (index // 4) % (64 // case['width'])
            assert case['vm'] or case['mask'] >> (index % 32) & 1
            assert event['active'] == '1'
            if case['mode'] == 0:
                pos, neg = (0x7c00, 0xfc00) if case['width'] == 16 else (0x7f800000, 0xff800000)
                assert int(event['operand'], 16) == (neg if index % 2 else pos)
            pending[key].append(event)
            counts[cid] += 1
        if event['out_valid'] == event['out_ready'] == '1':
            assert pending[key], ('output without accepted input', event)
            issued = pending[key].popleft()
            assert issued['in_tag'] == event['out_tag'], ('tag corruption', issued, event)
            assert int(event['gated_status'], 16) == (
                int(event['collapsed_status'], 16) if int(event['out_tag'], 16) else 0)
            flags_pending[cid, lane, cycle+1] = event['gated_status']
            if int(event['raw_status'], 16) & 16:
                witnesses.append(dict(name=case['name'], lane=lane,
                    issue_cycle=int(issued['cycle']), output_cycle=cycle,
                    local_index=int(issued['local_index']), mask=issued['mask'],
                    accumulator=issued['accumulator'], operand=issued['operand'],
                    issue_be=issued['issue_be'], in_tag=issued['in_tag'],
                    out_tag=event['out_tag'], raw_status=event['raw_status'],
                    collapsed_status=event['collapsed_status'], gated_status=event['gated_status']))
        if event['flags_valid'] == '1':
            assert flags_pending.pop((cid, lane, cycle)) == event['flags']
        if event['slide_fire'] == '1':
            assert lane == transfers[cid] % 4
            transfers[cid] += 1
    assert not flags_pending and all(not q for q in pending.values())
    for cid, case in enumerate(suite):
        assert transfers[cid] == case['vl']
        assert counts[cid] == sum(bool(case['vm'] or case['mask'] >> (i % 32) & 1)
                                  for i in range(case['vl']))
    return dict(path=str(path), cases=len(rows),
                result_failures=[r['name'] for r in rows if r['result_match'] != '1'],
                flag_failures=[r['name'] for r in rows if r['flags_match'] != '1'],
                nv_witnesses=witnesses), rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--compare', type=Path)
    args = parser.parse_args()
    report, rows = inspect(args.run)
    if args.compare:
        other, other_rows = inspect(args.compare)
        indexed = {r['name']: r for r in other_rows}
        common = [r for r in rows if r['name'] in indexed]
        report['comparison'] = dict(path=str(args.compare), cases=len(common),
            result_changes=[r['name'] for r in common if r['result'] != indexed[r['name']]['result']],
            cycle_changes=[dict(name=r['name'], before=r['cycles'], after=indexed[r['name']]['cycles'])
                           for r in common if r['cycles'] != indexed[r['name']]['cycles']],
            flag_changes=[dict(name=r['name'], before=r['flags'], after=indexed[r['name']]['flags'])
                          for r in common if r['flags'] != indexed[r['name']]['flags']],
            other_flag_failures=other['flag_failures'], other_result_failures=other['result_failures'])
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
