#!/usr/bin/env python3
"""Strict group7 numerics/state/path/work check. Parent independently checks protocol/image."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
from contract import require,save,sha,verify
import elf as reader

FIELDS=set('id begin end initial_fcsr initial_vcsr initial_vstart fcsr vcsr vstart vl vtype op_vstart hash errors'.split())
CUSTOM=[0x00b5045b,0x00b5605b,0x0005345b,0x0605705b,0x0485705b,0x0000505b,
        0x00b5045b,0x00b5045b,0x00b5605b,0x0005345b,0x0000505b,
        0x00b5605b,0x0000505b,0x00b5045b]


def fields(text,expected=None,hexfields=()):
    pairs=[p.split('=') for p in text.split()]
    require(all(len(p)==2 for p in pairs) and len({p[0] for p in pairs})==len(pairs),'Record duplicate/malformed fields')
    require(expected is None or {p[0] for p in pairs}==expected,'Record schema')
    result={}
    for k,v in pairs:
        require(re.fullmatch('[0-9a-f]+' if k in hexfields else '[0-9]+',v),'Record number syntax')
        result[k]=int(v,16 if k in hexfields else 10)
    return result


def numerical(text,fixture):
    rows=[];data=[];done=[];caps=[];handoff=[]
    for line in text.splitlines():
        if not line.startswith('CO_'):continue
        if line.startswith('CO_CASE '):rows.append(fields(line[8:],FIELDS,('hash',)))
        elif line.startswith('CO_DATA '):data.append(fields(line[8:],{'bytes','hash'},('hash',)))
        elif line.startswith('CO_DONE '):done.append(fields(line[8:],{'cases','errors'}))
        elif line.startswith('CO_CAP '):caps.append(fields(line[7:],{'qbs','akv','resident'},('qbs','akv','resident')))
        elif line.startswith('CO_HANDOFF '):handoff.append(fields(line[11:],{'traps','input_unchanged','errors'}))
        else:raise ValueError('Unknown/rejected coexist record: '+line)
    require(len(rows)==len(fixture['cases']),'All case results required')
    last=0
    for i,(r,c) in enumerate(zip(rows,fixture['cases'])):
        expected=dict(id=i,initial_fcsr=c['initial_fcsr'],initial_vcsr=5,initial_vstart=0,
            fcsr=c['expected_fcsr'],vcsr=5,vstart=0,vl=c['expected_vl'],vtype=c['expected_vtype'],
            op_vstart=0,hash=c['output_hash'],errors=0)
        require(all(r[k]==v for k,v in expected.items()),'Numerics/guards/CSR/VL mismatch in case '+str(i))
        require(last<r['begin']<r['end'],'Full kernel cycle bounds/order');last=r['end']
    require(data==[dict(bytes=fixture['data_bytes'],hash=fixture['data_hash'])] and
            done==[dict(cases=len(rows),errors=0)],'Fixture integrity/unique terminal result')
    if fixture['kind']=='handoff':
        require(len(caps)==1 and caps[0]['qbs']>0 and caps[0]['akv']>0 and
                caps[0]['resident']==0x0000040000040301,'Enabled QBS/AKV/Resident capability required')
        require(handoff==[dict(traps=0,input_unchanged=1,errors=0)],'Archived handoff guards/traps/input mutation')
    else:require(not caps and not handoff,'Unexpected custom-path evidence in ordinary ISA ELF')
    return [dict(id=r['id'],cycles=r['end']-r['begin'],fcsr=r['fcsr']) for r in rows]


def activity(text,fixture):
    records=[]
    names=set('cycles native_requests native_fma_requests native_fma_elements qk_requests qk_elements pv_requests pv_elements native_blocked resident_blocked'.split())
    for line in text.splitlines():
        if 'OPERATOR_UNIT' not in line:continue
        m=re.fullmatch(r'OPERATOR_UNIT (\S*gen_lanes\[([0-3])\]\S*i_operator_unit_activity) (.+)',line)
        require(m is not None,'Activity owner/schema');records.append((int(m[2]),m[1],fields(m[3],names)))
    require(len(records)==4*len(fixture['cases']),'Four lane activity records per ROI required')
    results=[];owners=None
    for i,c in enumerate(fixture['cases']):
        block=records[4*i:4*i+4]
        require({lane for lane,_,_ in block}==set(range(4)),'Missing/duplicate activity lane')
        paths={p for _,p,_ in block}
        if owners is None:owners=paths
        require(paths==owners and len({r['cycles'] for _,_,r in block})==1,'Activity window identity')
        totals=Counter()
        for lane,_,r in block:
            require(r['cycles']>0 and r['native_requests']>=r['native_fma_requests'] and
                    r['native_fma_elements']<=4*r['native_fma_requests'] and
                    r['native_blocked']<=r['cycles'] and r['resident_blocked']<=r['cycles'],
                    'Accepted-work/request/cycle bounds')
            expected_qk=128 if c.get('qk_elements') and lane<3 else 0
            expected_pv=96 if c.get('pv_elements') else 0
            require(r['qk_elements']==expected_qk and r['pv_elements']==expected_pv,
                    'Resident accepted lane FMA work')
            require((r['qk_requests']==0)==(expected_qk==0) and
                    (r['pv_requests']==0)==(expected_pv==0) and
                    expected_qk<=2*r['qk_requests'] and expected_pv<=4*r['pv_requests'],
                    'Resident handshake/semantic masks')
            totals.update({k:v for k,v in r.items() if k!='cycles'})
        native=c.get('native_fma_elements',sum(1 for j in range(c.get('restart',0),c.get('vl',0))
            if not c.get('masked') or j%2) if c['op'].startswith('vf') else 0)
        require(totals['native_fma_elements']==native,'Exact ordinary FMA semantic work')
        results.append(dict(id=i,cycles=block[0][2]['cycles'],totals=dict(totals)))
    return results


def paths(commit,vector,program,fixture):
    symbols,word=reader.read(Path(program['elf']))
    expected={k:v['count'] for k,v in program['entries'].items()}
    targets={v['address']:(k,v['word']) for k,v in program['entries'].items()}
    for test in program['tested']:
        targets[test['address']]=('test_%d'%test['id'],test['word']);expected['test_%d'%test['id']]=1
    counts=Counter();custom=[];markers=0;previous=-1
    with Path(commit).open(newline='') as stream:
        r=csv.DictReader(stream);require({'cycle','event','pc','insn','trap'}<=set(r.fieldnames or []),'Commit schema')
        for row in r:
            require(None not in row and all(v is not None for v in row.values()),'Malformed commit row')
            cycle=int(row['cycle']);require(cycle>=previous,'Commit order');previous=cycle
            if row['event']!='retire':continue
            require(int(row['trap'])==0,'Architectural trap, never a skip')
            pc,insn=int(row['pc'],16),int(row['insn'],16)
            if insn==0xc0002073:markers+=1
            if insn&127==0x5b:custom.append(insn)
            if pc in targets:
                name,raw=targets[pc];require(insn==(raw if raw&3==3 else raw&65535),'Entry/test instruction not ELF-bound')
                counts[name]+=1
    # A kernel's first instruction can itself be the tested instruction only
    # in a degenerate future generator; reject it rather than hide one count.
    require(len(targets)==len(expected),'Aliased entry/test identity')
    require(dict(counts)==expected and markers==2*len(fixture['cases']),'Actual kernel/test entries/ROI markers')
    want_custom=[0x0005155b,0x0005455b,0x0005455b,*CUSTOM] if fixture['kind']=='handoff' else []
    require(custom==want_custom,'Retired custom path order/capability probes')
    allocations=[];tested=Counter();configuration=0;previous=-1
    wanted=Counter(t['word'] for t in program['tested'])
    with Path(vector).open(newline='') as stream:
        r=csv.DictReader(stream);require({'cycle','event','insn','nr_lanes','vlen_bits'}<=set(r.fieldnames or []),'Vector schema')
        for row in r:
            require(None not in row and all(v is not None for v in row.values()),'Malformed vector row')
            cycle=int(row['cycle']);require(cycle>=previous and row['nr_lanes']=='4' and
                row['vlen_bits']=='1024','Vector ordering/configuration');previous=cycle
            if row['event']=='config':configuration+=1;require(configuration==1 and cycle==0,'Vector config');continue
            require(configuration==1 and row['event'] in ('alloc','write','done'),'Vector event')
            if row['event']!='alloc':continue
            insn=int(row['insn'],16)
            if insn&127==0x5b:allocations.append(insn)
            if insn in wanted:tested[insn]+=1
    require(configuration==1 and allocations==(CUSTOM if fixture['kind']=='handoff' else []) and
            tested==wanted,'Actual vector custom/test allocation counts')
    return dict(entries=dict(counts),roi_markers=markers,custom_vector_allocations=allocations,
                tested_vector_allocations={format(k,'08x'):v for k,v in tested.items()})


def check(build,kind,log,vector,commit):
    m=json.loads((build/'build.json').read_text());require(m['state']=='BUILT_NOT_EXECUTED' and
        m['schema']=='coexist-firmware-v1' and m['dirty_asm_excluded'] and m['post_pins_match'], 'Firmware admission')
    require(sha(build/'source-pins.json')==m['source_pins_sha256'],'Inventory identity')
    verify(json.loads((build/'source-pins.json').read_text()));verify(m['artifacts'])
    program=m['programs'][kind];require(sha(program['elf'])==program['elf_sha256'],'ELF identity')
    fixture=json.loads(Path(program['fixture']).read_text());text=log.read_text()
    require('Core Test *** SUCCESS ***' in text and not re.search(r'Fatal:|Error:|Error-|\bFAILED\b|\bSKIP\b',text),
            'Firmware/simulator success, no skip')
    for line in text.splitlines():
        if re.match(r'\s*UVM_(ERROR|FATAL)\b',line):
            require(re.fullmatch(r'\s*UVM_(ERROR|FATAL)\s*:\s*0\s*',line),'UVM error/fatal')
    measured=numerical(text,fixture);work=activity(text,fixture)
    actual=paths(commit,vector,program,fixture)
    qbs=[fields(line[len('[QBS_PERF] '):]) for line in text.splitlines() if line.startswith('[QBS_PERF] ')]
    akv=[fields(line[len('[AKV_PERF] '):]) for line in text.splitlines() if line.startswith('[AKV_PERF] ')]
    require(len(qbs)==(4 if kind=='handoff' else 0) and len(akv)==(8 if kind=='handoff' else 0),
            'Enabled custom engine completion counts')
    for i,r in enumerate(qbs):
        require(r['seq']==i+1 and all(r[k]==v for k,v in dict(m=1,n=3,vlen=1024,lanes=4,
            success=1,fault=0,validation_fault=0,validation_error=0,read_fault=0,tiles=1,
            useful_pairs=768,weight_bytes=432,activation_bytes=292,payload_bytes=740).items()) and
            r['busy_cycles']>0,'QBS independent shape/work/payload')
    for i,(r,command) in enumerate(zip(akv,[4,2,3,4,2,3,4,3])):
        want=dict(seq=i+1,command=command,success=1,fault=0,validation_fault=0,
            validation_error=0,read_fault=0,v2_rejected=0,q_external_bytes=256 if command==4 else 0,
            kv_external_bytes=768 if command==4 else 0,replay_bytes=128 if command==2 else 0,
            read_payload_bytes=1088 if command==4 else 0)
        require(all(r[k]==v for k,v in want.items()) and r['busy_cycles']>0,'AKV work/payload/return')
    return dict(state='PASS',metrics=dict(kind=kind,trials=measured,unit_activity=work,actual_paths=actual,
        outputs_checked_on_target_outside_roi=True,guards_and_all_state_checked=True,
        integer_operations=len(fixture['cases']) if kind=='integer' else 0,
        independent_reference=m['host_reference']['integer' if kind=='integer' else 'floating'],
        qbs_commands=len(qbs),akv_commands=len(akv)),performance_acceptance=False,
        protocol_checked=False,image_checked=False,same_source_variant_binding_owned_by_parent=True,
        build_sha256=sha(build/'build.json'),evidence_sha256={str(p):sha(p) for p in (log,vector,commit)})


def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    for n in ('build','log','vector','commit','output'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--kind',choices=('integer','fma','handoff'),required=True);a=p.parse_args()
    try:r=check(a.build,a.kind,a.log,a.vector,a.commit)
    except Exception as exc:r=dict(state='FAIL',error=repr(exc),performance_acceptance=False)
    save(a.output,r);print(json.dumps({k:v for k,v in r.items() if k!='metrics'}),flush=True)
    return r['state']!='PASS'


if __name__=='__main__':raise SystemExit(main())
