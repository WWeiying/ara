#!/usr/bin/env python3
"""Exact fixed-point schedule/flags and original model tolerance, actual segmented work."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
from contract import require,save,sha,verify
import elf

CUSTOM=[0x00b5605b]+[0x0205745b]*64+[0x00b5605b]+[0x0205345b]*34+[0x0000505b]


def fields(text,hexes=()):
    pairs=[x.split('=') for x in text.split()]
    require(all(len(p)==2 for p in pairs) and len({p[0] for p in pairs})==len(pairs),'Malformed/duplicate fields')
    require(all(re.fullmatch('[0-9a-f]+' if k in hexes else '[0-9]+',v) for k,v in pairs),'Integer field syntax')
    return {k:int(v,16 if k in hexes else 10) for k,v in pairs}


def numerical(text,m):
    records=[];hexes={'hash','query_hash','q','qh','k','kh','v','vh','bits'}
    for line in text.splitlines():
        if not line.startswith('D256_'):continue
        tag,data=line.split(' ',1);records.append((tag,fields(data,hexes)))
    index=0
    def take(tag):
        nonlocal index
        require(index<len(records) and records[index][0]==tag,'Missing/out-of-order '+tag)
        r=records[index][1];index+=1;return r
    ref=m['reference']['result'];last=0;measured=[]
    for t in range(2):
        r=take('D256_CALL');expected=dict(trial=t,groups=1,status=0,initial_fcsr=8,initial_vcsr=5,
            initial_vstart=0,fcsr=ref['expected_fcsr'],vcsr=5,vstart=0,errors=0,model_errors=0,
            hash=ref['output_hash'],query_hash=m['memory']['query_hash'],guards=0)
        require(set(r)==set(expected)|{'begin','end'} and all(r[k]==v for k,v in expected.items()),
                'All-output exact/model/guard/state mismatch')
        require(last<r['begin']<r['end'],'ROI ordering');last=r['end']
        measured.append(dict(trial=t,mode=m['modes'][t],cycles=r['end']-r['begin']))
        p=take('D256_PLAN');want=dict(trial=t,segments=2,logical=256,physical=128,offset=0,count=128,
            rows=4,tokens=17,qs=512,ks=512,vs=512)
        require(set(p)==set(want)|{'q','qh','k','kh','v','vh'} and all(p[k]==v for k,v in want.items()),
                'Actual D256 segmented plan shape/strides')
        require(all(p[k]>0 and p[k]%64==0 for k in ('q','qh','k','kh','v','vh')) and
            p['qh']==p['q']+256 and p['kh']==p['k']+256 and p['vh']==p['v']+256 and
            len({p['q'],p['k'],p['v']})==3,'D256 low/high stream mapping')
        for i,bits in enumerate(ref['bits'][:64]):
            require(take('D256_OUT')==dict(trial=t,index=i,bits=bits),'Independent output diagnostic bits')
    require(take('D256_DATA')==dict(bytes=m['memory']['data_bytes'],hash=m['memory']['data_hash']),
            'All immutable data/gold fingerprint')
    require(take('D256_DONE')==dict(calls=2,errors=0) and index==len(records),'Unique complete terminal result')
    return measured


def activity(text):
    rows=[];schema=set('cycles native_requests native_fma_requests native_fma_elements qk_requests qk_elements pv_requests pv_elements native_blocked resident_blocked'.split())
    for line in text.splitlines():
        if 'OPERATOR_UNIT' not in line:continue
        match=re.fullmatch(r'OPERATOR_UNIT (\S*gen_lanes\[([0-3])\]\S*i_operator_unit_activity) (.+)',line)
        require(match is not None,'Activity owner/schema');r=fields(match[3]);require(set(r)==schema,'Activity fields')
        rows.append((int(match[2]),match[1],r))
    require(len(rows)==8,'Four lane records for both calls required')
    reports=[];owners=None
    for t in range(2):
        block=rows[4*t:4*t+4];paths={p for _,p,_ in block}
        if owners is None:owners=paths
        require({lane for lane,_,_ in block}==set(range(4)) and paths==owners and
            len({r['cycles'] for _,_,r in block})==1,'Activity lane/window identity')
        for lane,_,r in block:
            require(r['cycles']>0 and r['native_requests']>=r['native_fma_requests'] and
                r['native_fma_elements']==(9632 if lane==0 else 8576) and
                r['native_fma_elements']<=2*r['native_fma_requests'] and
                r['native_blocked']<=r['cycles'] and r['resident_blocked']<=r['cycles'] and
                all(r[k]==0 for k in ('qk_requests','qk_elements','pv_requests','pv_elements')),
                'Exact F32 QK/PV/vector-exp work and zero Resident required')
        reports.append(dict(trial=t,native_fma_elements=sum(r['native_fma_elements'] for _,_,r in block),
            monitor_cycles=block[0][2]['cycles'],lanes={str(lane):r for lane,_,r in block}))
    return reports


def legacy(text):
    rows=[fields(line[len('[AKV_PERF] '):]) for line in text.splitlines() if line.startswith('[AKV_PERF] ')]
    summaries=[fields(line[len('[AKV_PERF_SUMMARY] '):]) for line in text.splitlines() if line.startswith('[AKV_PERF_SUMMARY] ')]
    commands=[4]+[6]*64+[4]+[2]*34+[3]
    require(len(rows)==101 and len(summaries)==1,'All segmented legacy command completions required')
    for i,(r,c) in enumerate(zip(rows,commands)):
        want=dict(seq=i+1,command=c,success=1,fault=0,validation_fault=0,validation_error=0,read_fault=0,
            v2_rejected=0,context_ready=int(c!=3),v2_full=int(c==4),v2_refill=0,
            v2_row_load=int(c==2),v2_column_load=int(c==6),v2_column_panel=int(c==6),
            v2_logical_column=4 if c==6 else 0,q_external_bytes=1024 if c==4 else 0,
            kv_external_bytes=8704 if c==4 else 0,replay_bytes=136 if c==6 else 256 if c==2 else 0,
            read_payload_bytes=9792 if c==4 else 0)
        require(all(r[k]==v for k,v in want.items()) and r['busy_cycles']>0,'D256 command/payload/accounting')
    want=dict(records=101,success_records=101,fault_records=0,validation_fault_records=0,
        v2_full=2,v2_refill=0,v2_column_load=64,v2_column_panel=64,v2_logical_column=256,
        v2_row_load=34,release=1,q_external_bytes=2048,kv_external_bytes=17408,replay_bytes=17408)
    require(all(summaries[0][k]==v for k,v in want.items()),'Segmented command summary')
    return dict(commands=101,summary=summaries[0])


def paths(commit,vector,m):
    counts=Counter();markers=0;previous=-1;_,memory=elf.read(Path(m['elf']))
    starts={e['address']:(name,e) for name,e in m['entries'].items()}
    require(len(starts)==len(m['entries']),'Distinct function entry identity')
    with commit.open(newline='') as stream:
        r=csv.DictReader(stream);require({'cycle','event','pc','insn','trap'}<=set(r.fieldnames or []),'Commit schema')
        for row in r:
            require(None not in row and all(x is not None for x in row.values()),'Malformed commit record')
            cycle=int(row['cycle']);require(cycle>=previous,'Commit ordering');previous=cycle
            if row['event']!='retire':continue
            require(int(row['trap'])==0,'Architectural trap')
            insn=int(row['insn'],16);pc=int(row['pc'],16)
            if insn==0xc0002073:markers+=1
            if pc in starts:
                name,e=starts[pc];word=e['word']
                require(insn==(word if word&3==3 else word&65535),'Entry instruction not ELF-bound')
                counts[name]+=1
    require(dict(counts)=={k:v['count'] for k,v in m['entries'].items()} and markers==4,'Actual SDK/segmented/memory entries')
    custom=[];configuration=0;previous=-1
    with vector.open(newline='') as stream:
        r=csv.DictReader(stream);require({'cycle','event','insn','nr_lanes','vlen_bits'}<=set(r.fieldnames or []),'Vector schema')
        for row in r:
            require(None not in row and all(x is not None for x in row.values()),'Malformed vector record')
            cycle=int(row['cycle']);require(cycle>=previous and row['nr_lanes']=='4' and row['vlen_bits']=='1024','Vector config/order');previous=cycle
            if row['event']=='config':configuration+=1;require(configuration==1 and cycle==0,'Vector configuration');continue
            require(configuration==1 and row['event'] in ('alloc','write','done'),'Vector event kind')
            insn=int(row['insn'],16)
            if row['event']=='alloc' and insn&127==0x5b:custom.append(insn)
    require(configuration==1 and custom==CUSTOM,'Exact native panel4/segment loads; no Resident or QBS')
    return dict(entries=dict(counts),monitor_markers=markers,custom_allocations=custom)


def check(build,log,vector,commit):
    m=json.loads((build/'build.json').read_text())
    require(m['schema']=='real-d256-firmware-v1' and m['state']=='BUILT_NOT_EXECUTED' and
        m['post_pins_match'] and m['dirty_asm_excluded'] and not m['old_rtl_pass_reused'],'D256 firmware identity')
    require(sha(build/'source-pins.json')==m['source_pins_sha256'] and sha(m['elf'])==m['elf_sha256'],'Pinned inventory/ELF')
    verify(json.loads((build/'source-pins.json').read_text()));verify(m['artifacts'])
    text=log.read_text()
    require('Core Test *** SUCCESS ***' in text and not re.search(r'Fatal:|Error:|Error-|\bFAILED\b|\bSKIP\b',text),'Successful target, no skip')
    for line in text.splitlines():
        if re.match(r'\s*UVM_(ERROR|FATAL)\b',line):require(re.fullmatch(r'\s*UVM_(ERROR|FATAL)\s*:\s*0\s*',line),'UVM error/fatal')
    measured=numerical(text,m);units=activity(text);work=legacy(text);actual=paths(commit,vector,m)
    return dict(state='PASS',metrics=dict(trials=measured,activity=units,legacy=work,actual_paths=actual,
        model_comparison=m['reference']['result']['model_comparison'],dimension=256,heads=4,tokens=17,capacity=256,
        scale_bits=0x3f800000,expected_fcsr=m['reference']['result']['expected_fcsr'],
        exact_outputs_checked_on_target=2048,primary_speedup_eligible=False),
        protocol_checked=False,image_checked=False,performance_acceptance=False,old_rtl_pass_reused=False,
        scope=m['scope'],build_sha256=sha(build/'build.json'),evidence_sha256={str(p):sha(p) for p in (log,vector,commit)})


def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    for n in ('build','log','vector','commit','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args()
    try:r=check(a.build,a.log,a.vector,a.commit)
    except Exception as exc:r=dict(state='FAIL',error=repr(exc),performance_acceptance=False)
    save(a.output,r);print(json.dumps({k:v for k,v in r.items() if k!='metrics'}),flush=True)
    return r['state']!='PASS'


if __name__=='__main__':raise SystemExit(main())
