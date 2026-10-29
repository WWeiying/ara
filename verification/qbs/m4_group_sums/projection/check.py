"""Strict full-N M4 Q/V/K slice checks, separate functional and timing receipts."""
import argparse
import csv
import json
from pathlib import Path
import re


def check_output(text,timed=True):
    marker='M4_SUMS_QKV_RESULT' if timed else 'M4_SUMS_QKV_FUNCTIONAL_RESULT'
    lines=text.splitlines()
    if lines.count(marker+' errors=0 trials=4 m=4 k=1536 outputs=8192 commands=256')!=1:
        raise ValueError('Missing complete guest success')
    if lines.count('M4_SUMS_QKV_SCOPE reuse_both=1 cold_producer_only=1')!=1:
        raise ValueError('Missing paired reuse scope')
    names=set('id candidate admit prep execute total hits misses stores fcsr vcsr errors'.split())
    trials=[]
    for line in lines:
        if not line.startswith('M4_SUMS_QKV_TRIAL '):continue
        pairs=re.findall(r'(\w+)=(\d+)',line)
        if len(pairs)!=len(names) or {p[0] for p in pairs}!=names:raise ValueError('Trial schema')
        trials.append({k:int(v) for k,v in pairs})
    if len(trials)!=4:raise ValueError('Missing/extra trials')
    for i,t in enumerate(trials):
        reuse=int(i in (1,2))
        if any(t[k]!=v for k,v in dict(id=i,candidate=reuse,hits=2,misses=1,stores=1,errors=0,vcsr=5).items()):
            raise ValueError('Cache/CSR accounting')
        if not 0<=t['fcsr']<=31 or t['fcsr']&17!=17 or t['fcsr']!=trials[0]['fcsr']:
            raise ValueError('Floating-point state')
        phases=sum(t[k] for k in ('admit','prep','execute'))
        if any(t[k]<=0 for k in ('admit','prep','execute')) or not 0<=t['total']-phases<=4096:
            raise ValueError('Cycle partition')
    result=dict(state='PASS',trials=trials,performance_measured=timed,
                scope='Full-output Q/V/K slice with SDK, excludes intervening graph operations and model execution')
    if timed:
        totals={name:sum(trials[i]['total'] for i in ids) for name,ids in (('baseline',(0,3)),('parallel',(1,2)))}
        result.update(totals=totals,speedup=totals['baseline']/totals['parallel'],
                      cycle_reduction=1-totals['parallel']/totals['baseline'])
    else:
        result['trials']=[{k:v for k,v in t.items() if k not in ('admit','prep','execute','total')} for t in trials]
    return result


def check_trace(path):
    alloc=set();written={};slots={};configured=False
    with Path(path).open(newline='') as f:
        for r in csv.DictReader(f):
            if r['event']=='config':
                if configured or alloc or (int(r['nr_lanes']),int(r['vlen_bits']))!=(4,1024):raise ValueError('Trace configuration')
                configured=True;continue
            if r['event'] not in ('alloc','write'):continue
            instruction=int(r['insn'],16)
            if instruction&127!=0x5b or instruction==0x0005155b:continue
            if instruction!=0x06b5045b:raise ValueError('Unexpected custom work')
            seq=int(r['arch_seq'])
            if not configured or int(r['vstart']) or (int(r['vl']),int(r['vd']),int(r['eew']))!=(128,8,2) or \
               (int(r['nr_lanes']),int(r['vlen_bits']))!=(4,1024):
                raise ValueError('M4 result geometry')
            if r['event']=='alloc':
                if seq in alloc:raise ValueError('Duplicate command allocation')
                alloc.add(seq)
            else:
                lane,address,mask=int(r['lane']),int(r['addr']),int(r['be'],16)
                if seq not in alloc or not 0<=lane<4 or not 32<=address<48 or not 0<mask<=255:
                    raise ValueError('Result byte addressing')
                seen=slots.setdefault(seq,set())
                for byte in range(8):
                    if mask&(1<<byte):
                        position=(lane,address,byte)
                        if position in seen:raise ValueError('Duplicate result byte')
                        seen.add(position)
                written[seq]=written.get(seq,0)+bin(mask).count('1')
    if not configured or len(alloc)!=256 or set(written)!=alloc or any(v!=512 for v in written.values()):
        raise ValueError('Incomplete/extra native matrix work')
    return dict(commands=256,result_bytes=sum(written.values()))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('build','log','trace','uvm'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();build=json.loads((a.build/'build.json').read_text())
    if build.get('group_sums_projection') is not True or build.get('reuse_both') is not True:raise ValueError('Wrong projection build')
    r=check_output(a.log.read_text());r['traffic']=check_trace(a.trace)
    uvm=json.loads(a.uvm.read_text())
    if uvm['status']!='PASS' or uvm.get('issues'):raise ValueError('Independent protocol check failed')
    print(json.dumps(r,indent=2))
