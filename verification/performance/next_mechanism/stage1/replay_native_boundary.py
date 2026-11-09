#!/usr/bin/env python3
"""Partition an accepted old SoC trace; no new simulation or performance claim."""
import argparse
import csv
import json
from pathlib import Path
import re
import subprocess

from audit import read, require, sha

NM=Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin/riscv64-linux-nm')
BUILD=Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/chain_q6_build_20261107_integrity02')


def engine_boundaries(text):
    raw=[]
    inflight=None
    previous=-1
    pattern=re.compile(r'^\[CHAIN_BOUNDARY\] cycle=(\d+) insn=([0-9a-f]{8}) '
                       r'qbs_fire=([01]) qbs_terminal=([01]) akv_fire=0 akv_terminal=0$')
    for line in text.splitlines():
        if not line.startswith('[CHAIN_BOUNDARY]'):
            continue
        m=pattern.fullmatch(line)
        require(m is not None, 'Unexpected or malformed Q6 boundary')
        cycle,fire,terminal=int(m[1]),int(m[3]),int(m[4])
        require(cycle>previous and not (fire and terminal), 'Ambiguous boundary order')
        previous=cycle
        if fire:
            require(inflight is None, 'Overlapping old commands')
            inflight=cycle
        if terminal:
            require(inflight is not None, 'Unmatched terminal')
            raw.append(dict(fire=inflight,terminal=cycle,cycles=cycle-inflight))
            inflight=None
    require(inflight is None and raw, 'Incomplete full boundary log')
    return raw


def native_spans(rows, start, end, stop):
    spans=[]
    active=[]
    previous_cycle=-1
    for row in rows:
        cycle=int(row['cycle'])
        require(cycle>=previous_cycle, 'Cycle order changed')
        previous_cycle=cycle
        if cycle>stop:
            break
        if row['event']!='retire':
            continue
        pc=int(row['pc'],16)
        inside=start<=pc<end
        if inside:
            require(row['trap']=='0', 'Native retirement trapped')
            if not active:
                require(pc==start, 'Partial native entry')
            active.append(row)
        elif active:
            require(int(active[-1]['insn'],16) in (0x8082,0x8067),
                    'Native span left via non-return; cannot treat a callee as completion')
            spans.append(dict(entry=int(active[0]['cycle']),exit=cycle,
                              cycles=cycle-int(active[0]['cycle']),retired=len(active)))
            active=[]
    require(not active, 'Missing native return')
    return spans


def partition(t2, t3, spans, boundaries):
    require(len(spans)==len(boundaries)==2, 'Expected two old N32 commands')
    require(t2<=spans[0]['entry']<spans[0]['exit']<=spans[1]['entry']<spans[1]['exit']<=t3,
            'Native calls outside ROI')
    for span,b in zip(spans,boundaries):
        require(span['entry']<=b['fire']<b['terminal']<=span['exit'] and
                b['terminal']-b['fire']==b['cycles'], 'Engine interval outside native call')
    prefix=spans[0]['entry']-t2
    gap=spans[1]['entry']-spans[0]['exit']
    suffix=t3-spans[1]['exit']
    helper=sum(s['cycles'] for s in spans)
    busy=sum(b['cycles'] for b in boundaries)
    require(prefix+gap+suffix+helper==t3-t2, 'Nonexclusive execution partition')
    return dict(execute=t3-t2,sdk_prefix=prefix,between_callbacks=gap,sdk_suffix=suffix,
                native_spans=spans,native_total=helper,engine_busy=busy,
                native_outside_engine=helper-busy,
                sdk_outside_native=prefix+gap+suffix,
                execute_outside_engine=t3-t2-busy)


def review(root):
    accepted=read(root/'result.json')
    require(accepted['state']=='CURRENT_RUNS_RECONCILED' and not accepted['whole_model'],
            'Wrong source evidence')
    run=Path(accepted['selected_runs']['q6'])
    commit,boundary,log=[run/'work'/name for name in ('commit.csv','boundary.csv','run.vcs.log')]
    pins=read(root/'evidence-pins.json')
    for path in (commit,boundary,log,run/'work/uvm_result.json'):
        require(sha(path)==pins[str(path)], 'Original evidence drift: '+str(path))
    uvm=read(run/'work/uvm_result.json')
    require(uvm['status']=='PASS' and not uvm['issues'], 'Independent protocol receipt not PASS')
    elf=BUILD/'q6_decode.elf'
    require(sha(elf)==uvm['elf_sha256']==read(BUILD/'build.json')['artifacts'][str(elf)], 'ELF drift')
    symbols=subprocess.check_output([str(NM),'-S','--defined-only',str(elf)],text=True)
    native=[line.split() for line in symbols.splitlines() if line.endswith(' qbs_native_execute_command')]
    require(len(native)==1 and len(native[0])==4, 'Missing sized native symbol')
    begin,size=int(native[0][0],16),int(native[0][1],16)
    # boundary.csv is only the first bounded signal window. The complete
    # fire/terminal series is in the independently pinned console log.
    text=log.read_text()
    raw=engine_boundaries(text)
    require(raw==accepted['boundaries']['q6']['qbs'], 'Boundary record mismatch')
    rois=[]
    for line in text.splitlines():
        if line.startswith('Q6_DECODE_TRIAL '):
            fields=dict(v.split('=',1) for v in line.split()[1:])
            rois.append({k:int(v) for k,v in fields.items()})
    require(len(rois)==2 and [r['trial'] for r in rois]==[0,1], 'Missing trials')
    with commit.open() as f:
        spans=native_spans(csv.DictReader(f),begin,begin+size,rois[-1]['t3'])
    require(len(spans)==4, 'Missing/duplicate native call')
    results=[]
    for i,roi in enumerate(rois):
        p=partition(roi['t2'],roi['t3'],spans[2*i:2*i+2],raw[2*i:2*i+2])
        old=accepted['q6']['trials'][i]['complete_call_partition']
        require(p['engine_busy']==old['native_engine_busy'] and
                p['execute_outside_engine']==old['sdk_execute_outside_engine'], 'Old partition mismatch')
        results.append(p)
    mean={k:sum(r[k] for r in results)/2 for k in
          ('execute','sdk_prefix','between_callbacks','sdk_suffix','native_total','engine_busy',
           'native_outside_engine','sdk_outside_native','execute_outside_engine')}
    return dict(state='OLD_SOC_RETIREMENT_PARTITION_RECONCILED',trials=results,mean=mean,
                scope=accepted['q6']['scope'],symbol=dict(start=begin,size=size),
                native_nonbusy_mean_per_command=mean['native_outside_engine']/2,
                new_simulation=False,board_cycle_budget_established=False,
                interpretation='SDK prefix is once per SDK execution, not once per N32. Native spans include actual return, not only instruction count. No per-instruction causal stall attribution.',
                source_pins={str(p):sha(p) for p in (root/'result.json',root/'evidence-pins.json',
                    commit,boundary,log,run/'work/uvm_result.json',elf,BUILD/'build.json')})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reconciled',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    sources={name:(Path(__file__).parent/name).read_bytes() for name in ('audit.py',Path(__file__).name)}
    result=review(args.reconciled)
    require(all((Path(__file__).parent/n).read_bytes()==v for n,v in sources.items()), 'Analyzer source drift')
    args.output.mkdir(parents=True,exist_ok=False)
    for name,data in sources.items():
        dest=args.output/name
        dest.write_bytes(data)
        result['source_pins'][str(dest.resolve())]=sha(dest)
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('state','mean','native_nonbusy_mean_per_command')},indent=2))


if __name__=='__main__':
    main()
