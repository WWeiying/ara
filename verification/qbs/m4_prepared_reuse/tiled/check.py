import argparse
import csv
import json
from pathlib import Path
import re


def check(text):
    lines=text.splitlines();trials=[]
    if lines.count('M4_TILED_RESULT errors=0 trials=4 calls=12 m=4 k=1536')!=1:raise ValueError('Missing complete success')
    names=set('id tiled first second third total errors'.split())
    for line in lines:
        if not line.startswith('M4_TILED_TRIAL '):continue
        pairs=re.findall(r'(\w+)=(\d+)',line)
        if len(pairs)!=len(names) or {k for k,_ in pairs}!=names:raise ValueError('Trial schema')
        trials.append({k:int(v) for k,v in pairs})
    if len(trials)!=4:raise ValueError('Four ABBA trials required')
    for i,t in enumerate(trials):
        if t['id']!=i or t['tiled']!=(0,1,1,0)[i] or t['errors'] or \
           any(t[k]<=0 for k in ('first','second','third')) or t['total']!=sum(t[k] for k in ('first','second','third')):
            raise ValueError('Timing, order or numerical failure')
    baseline=trials[0]['total']+trials[3]['total'];candidate=trials[1]['total']+trials[2]['total']
    return dict(state='PASS',trials=trials,baseline_cycles=baseline,tiled_cycles=candidate,
                speedup=baseline/candidate,cycle_reduction=1-candidate/baseline,
                scope='Preparation only; no cache or complete projection/model speedup')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('build','log','trace','uvm'):parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args();result=check(a.log.read_text());uvm=json.loads(a.uvm.read_text())
    if uvm['status']!='PASS' or uvm.get('issues'):raise ValueError('Protocol failure')
    configured=False
    with a.trace.open(newline='') as stream:
        for row in csv.DictReader(stream):
            if row['event']=='config':
                if configured or (int(row['nr_lanes']),int(row['vlen_bits']))!=(4,1024):raise ValueError('Trace geometry')
                configured=True
            elif row['event']=='alloc' and int(row['insn'],16)&127 in (0x0b,0x2b,0x5b,0x7b):
                raise ValueError('Unexpected custom-instruction work')
    if not configured:raise ValueError('Missing actual vector trace')
    print(json.dumps(result,indent=2))
