#!/usr/bin/env python3
"""Summarize observed boundaries; never infer safety from unobserved cycles."""
import argparse
import json
from pathlib import Path
import re


def analyze(text):
    if re.search(r'Fatal:|Error:|UVM_ERROR|UVM_FATAL',text):
        raise ValueError('Failed simulator')
    if text.splitlines().count('QBS engine PASS: 36 functional cases')!=1:
        raise ValueError('Incomplete numerical suite')
    cases=re.findall(r'^QBS end-to-end case (\d+) PASS ',text,re.M)
    if list(map(int,cases))!=list(range(36)):raise ValueError('Missing cases')
    windows={}
    for line in text.splitlines():
        if not line.startswith('QBS_TILE_BOUNDARY '):continue
        row={k:int(v) for k,v in (field.split('=') for field in line.split()[1:])}
        rows=windows.setdefault(row['window'],[])
        if rows and row['cycle']!=rows[-1]['cycle']+1:raise ValueError('Discontinuous window')
        rows.append(row)
    if not windows:raise ValueError('No actual probe data')
    found=[]
    for number,rows in windows.items():
        starts=[r for r in rows if r['start']]
        if not starts:continue
        start=starts[0];before=[r for r in rows if r['cycle']<start['cycle']]
        reads=[r for r in before if r['read']]
        dones=[r for r in before if r['done']]
        after=[r for r in rows if r['cycle']>start['cycle'] and r['read']]
        if not reads or not dones or not after:raise ValueError('Truncated observed boundary')
        last=reads[-1];done=dones[-1];new=after[0]
        if not last['cycle']<done['cycle']<start['cycle']<new['cycle']:
            raise ValueError('Invalid observed event order')
        if done['meta'] or done['dot'] or done['compute'] or done['issue'] or done['s0']:
            raise ValueError('Done with integer work pending')
        if last['k']+(8 if last['m']==1 else 4 if last['m']==2 else 2)!=last['block']:
            raise ValueError('Not final input read')
        found.append(dict(window=number,m=last['m'],last_read=last['cycle'],
            done_delta=done['cycle']-last['cycle'],start_delta=start['cycle']-last['cycle'],
            next_read_delta=new['cycle']-last['cycle'],
            old_context_live_at_start=bool(start['live']&(1<<last['ctx'])),
            correction_empty_at_start=bool(start['correction_empty']),
            bank_changed=last['bank']!=new['bank']))
    if not found or not {1,4}.issubset({r['m'] for r in found}):
        raise ValueError('Missing M1/M4 boundary evidence')
    return dict(state='OBSERVATIONS_ACCEPTED',functional_cases=36,boundaries=found,
        narrow_tail_coverage_proven=False,early_overlap_safety_proven=False,
        note='Bounded local trace, no optimized RTL or performance gain established.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('log',type=Path)
    print(json.dumps(analyze(p.parse_args().log.read_text()),indent=2))
