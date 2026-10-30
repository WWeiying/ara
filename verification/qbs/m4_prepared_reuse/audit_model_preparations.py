#!/usr/bin/env python3
"""Reconcile actual M4 computations and hits with logical GGML preparations."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import digest,hashes


def fields(line):return dict(re.findall(r'(\w+)=(\S+)',line))


def analyze(text):
    active=None;begun=[];ended=[];classic=[];cached=[]
    records={m:{name:Counter() for name in ('logical','computed','cached_computed','hits')} for m in (0,1)}
    for line in text.splitlines():
        if line.startswith('Q8K_MODEL_BEGIN '):
            mode=int(fields(line)['enabled'])
            if active is not None or mode!=len(begun) or mode not in records:raise ValueError('Mode order')
            active=mode;begun.append(mode)
        elif line.startswith('Q8K_MODEL_END '):
            mode=int(fields(line)['enabled'])
            if active!=mode or classic or cached:raise ValueError('Incomplete mode')
            ended.append(mode);active=None
        elif line.startswith('GGML_RISCV_QBS_Q8K_M4_PREPARE '):
            if active is None:raise ValueError('Unscoped computation')
            f=fields(line)
            if f['enabled']!='1' or f['path'] not in ('rvv','generic'):raise ValueError('Producer mode')
            classic.append(int(f['k']))
        elif line.startswith('GGML_RISCV_QBS_M4_CACHE '):
            f=fields(line)
            if active!=1 or f['group']!='0' or f['event'] not in ('hit','compute_rvv','compute_generic'):
                raise ValueError('Cache scope/event')
            cached.append(f)
        elif line.startswith('GGML_RISCV_QBS_LIFETIME '):
            if active is None:raise ValueError('Unscoped lifetime')
            f=fields(line);m=int(f['m']);k=int(f['k'])
            if m!=4:
                if classic or cached:raise ValueError('Cache/compute event without M4 preparation')
                continue
            r=records[active];r['logical'][k]+=1
            if cached:
                if len(cached)!=1 or classic or int(cached[0]['epoch'])!=int(f['graph_epoch']) or not 0<k<=6144 or k%256:
                    raise ValueError('Cache/lifetime geometry mismatch')
                event=cached[0]['event'];r['hits' if event=='hit' else 'cached_computed'][k]+=1
            else:
                if classic!=[k]:raise ValueError('Missing/duplicate M4 computation')
                r['computed'][k]+=1
            classic.clear();cached.clear()
    if begun!=[0,1] or ended!=[0,1] or active is not None or classic or cached:raise ValueError('Incomplete trace')
    if records[0]['logical']!=records[1]['logical'] or not records[0]['logical']:
        raise ValueError('Different logical workload')
    rows={}
    for mode,r in records.items():
        actual=r['computed']+r['cached_computed']
        if actual+r['hits']!=r['logical']:raise ValueError('Unbalanced actual work')
        rows[str(mode)]=dict(logical_m4_invocations=sum(r['logical'].values()),
            executed_m4_computations=sum(actual.values()),cache_hits=sum(r['hits'].values()),
            cache_handled_computations=sum(r['cached_computed'].values()),
            uncached_computations=sum(r['computed'].values()),
            by_k={str(k):dict(logical=r['logical'][k],computed=actual[k],hits=r['hits'][k]) for k in sorted(r['logical'])})
    if rows['0']['cache_hits'] or rows['0']['cache_handled_computations'] or rows['1']['cache_hits']<=0:
        raise ValueError('Invalid OFF/ON cache activity')
    return dict(state='PASS',modes=rows,
                scope='Actual M4 producer invocations reconciled against logical preparations; not M1 activity or timing')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Fresh report required')
    result=json.loads((a.run/'result.json').read_text());pins=json.loads((a.run/'manifest.json').read_text())
    if result['state']!='PASS' or result['log_sha256']!=digest(a.run/'qemu.log') or hashes(map(Path,pins))!=pins:
        raise ValueError('Original model gate missing or drifted')
    report=analyze((a.run/'qemu.log').read_text());report.update(log_sha256=result['log_sha256'],performance_measured=False)
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
