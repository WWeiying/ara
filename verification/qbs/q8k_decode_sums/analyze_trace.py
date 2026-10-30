#!/usr/bin/env python3
"""First K1536 ABBA instruction residence times for the pinned split-loop ELF."""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path

# Exact instruction sites from the reviewed bare-metal split build. Counts
# select the first two six-block invocations of each path, before K8960.
SITES={
    '3e883457':('original_slide',180),
    'c68100d7':('original_reduce',192),
    '3e3740d7':('split_slide',192),
    'c61100d7':('split_reduce',192),
    '9e8031d7':('split_copy_low',12),
    '9e9031d7':('split_copy_high',12),
}


def analyze(raw, sites=None):
    sites=SITES if sites is None else sites
    counts=Counter(); selected={}; rows=list(csv.DictReader(io.StringIO(raw.decode())))
    for row in rows:
        if row['event']!='alloc' or row['insn'] not in sites: continue
        seq=row['arch_seq']
        if seq in selected:
            if selected[seq]['insn']!=row['insn']: raise ValueError('Sequence identity drift')
            continue
        name,limit=sites[row['insn']]
        if counts[name]>=limit: continue
        selected[seq]=dict(name=name,insn=row['insn'],uops=[],bytes=0)
        counts[name]+=1
    for name,limit in sites.values():
        if counts[name]!=limit: raise ValueError('Incomplete K1536 window: '+name)
    active={}
    for row in rows:
        item=selected.get(row['arch_seq'])
        if item is None: continue
        if row['insn']!=item['insn']: raise ValueError('Instruction identity drift')
        key=(row['arch_seq'],row['vid'])
        if row['event']=='alloc':
            if key in active: raise ValueError('Allocation before completion')
            uop=dict(start=int(row['cycle']),vl=int(row['vl']),eew=int(row['eew']),done=None)
            item['uops'].append(uop); active[key]=uop
        elif row['event']=='done':
            if key not in active: raise ValueError('Completion without allocation')
            uop=active.pop(key); uop['done']=int(row['cycle'])
            if uop['done']<uop['start']: raise ValueError('Negative latency')
        elif row['event']=='write':
            item['bytes']+=bin(int(row['be'],16)).count('1')
    if active: raise ValueError('Incomplete instruction')
    groups={}
    for item in selected.values(): groups.setdefault(item['name'],[]).append(item)
    result={}
    for name,items in groups.items():
        spans=[max(u['done'] for u in item['uops'])-min(u['start'] for u in item['uops']) for item in items]
        uops=[u for item in items for u in item['uops']]
        durations=[u['done']-u['start'] for u in uops]
        result[name]=dict(architectural_count=len(items),backend_uops=len(uops),
            backend_vl_eew_histogram=dict(Counter(str((u['vl'],u['eew'])) for u in uops)),
            architectural_residence_mean=sum(spans)/len(items),
            uop_residence_min=min(durations),uop_residence_max=max(durations),
            uop_residence_sum=sum(durations),uop_residence_mean=sum(durations)/len(uops),
            enabled_write_bytes=sum(item['bytes'] for item in items))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    raw=args.trace.read_bytes()
    raw=raw[:raw.rfind(b'\n')+1]  # Discard an unfinished append, never edit the live trace.
    result=analyze(raw)
    out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    (out/'trace-prefix.csv').write_bytes(raw)
    report=dict(source=str(args.trace.resolve()),snapshot_sha256=hashlib.sha256(raw).hexdigest(),
                scope='First K1536 ABBA selected instructions; residence times overlap and are not additive stall cycles',
                groups=result)
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
