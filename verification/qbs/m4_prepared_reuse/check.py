#!/usr/bin/env python3
"""Strict full-cost preparation comparison, never a model speedup claim."""
import argparse
import json
from pathlib import Path
import re


def check(log):
    lines=log.splitlines()
    marker='M4_CACHE_SOC_RESULT errors=0 trials=4 calls=12 m=4 k=1536'
    if lines.count(marker)!=1:raise ValueError('Missing complete guest success')
    trials=[]
    for line in lines:
        if line.startswith('M4_CACHE_SOC_TRIAL '):
            fields=dict(re.findall(r'(\w+)=(\d+)',line))
            trials.append({k:int(v) for k,v in fields.items()})
    if len(trials)!=4:raise ValueError('Expected four trials')
    for i,t in enumerate(trials):
        reuse=int(i in (1,2))
        required=dict(id=i,reuse=reuse,hits=2*reuse,misses=reuse,stores=reuse,
                      compare_requested=49152*reuse,copied=45600*reuse,errors=0)
        if any(t.get(k)!=v for k,v in required.items()):raise ValueError('Invalid trial accounting')
        if any(t.get(k,0)<=0 for k in ('first','second','third')) or t['total']!=sum(t[k] for k in ('first','second','third')):
            raise ValueError('Invalid measured phases')
    baseline=sum(trials[i]['total'] for i in (0,3))
    candidate=sum(trials[i]['total'] for i in (1,2))
    return dict(state='PASS',trials=trials,baseline_cycles=baseline,cache_cycles=candidate,
                speedup=baseline/candidate,cycle_reduction=1-candidate/baseline,
                scope='Preparation-only three-call sequence; cold allocation included, cache destruction excluded')


def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True)
    p.add_argument('--log',type=Path,required=True);p.add_argument('--trace',type=Path,required=True)
    p.add_argument('--uvm',type=Path,required=True);a=p.parse_args()
    # Protocol validation is performed independently by the pinned worker before this checker.
    if not a.uvm.is_file() or not a.trace.is_file() or not (a.build/'build.json').is_file():
        raise ValueError('Missing protocol/build evidence')
    print(json.dumps(check(a.log.read_text()),indent=2))


if __name__=='__main__':main()
