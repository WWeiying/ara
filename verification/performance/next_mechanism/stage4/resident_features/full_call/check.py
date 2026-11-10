#!/usr/bin/env python3
"""Frozen numerical/CSR, real branch-entry, work and VRF evidence; not protocol."""
import argparse
from collections import Counter
import csv
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('features_full_call_fixture',HERE/'fixture.py')
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)


def support(name):
    path=HERE/'support'/name
    if not path.exists():
        prefix=f.ROOT/'verification/performance'
        path={'geometry.py':prefix/'resident_rvv/qk_shared/geometry.py',
              'legacy/check.py':prefix/'akv_pair_eval/check.py'}[name]
    return f.load(path,'features_support_'+name.replace('/','_'))


def build_receipt(path):
    path=Path(path).resolve(strict=True);m=f.read(path/'build.json')
    f.require(m['state']=='BUILT_NOT_EXECUTED' and m['schema']=='stage4-features-full-call-v1' and
              m['sdk_revision']==f.SDK and m['scope']==f.SCOPE and m['target_executed'] is False and
              m['post_pins_match'] is True,'Wrong feature firmware identity/scope')
    f.require(f.sha(path/'source-pins.json')==m['source_pins_sha256'] and
              m['elf']==str(path/'attention_features.elf') and f.sha(m['elf'])==m['elf_sha256'],
              'Firmware inventory/ELF drift')
    f.verify(f.read(path/'source-pins.json'));f.verify(m['artifacts'])
    f.require({str(p):f.sha(p) for p in path.rglob('*') if p.is_file() and p!=path/'build.json'}==m['artifacts'],
              'Unexpected/missing build artifact')
    f.verify({path/'inputs'/n:h for n,h in m['checker_dependencies'].items()})
    fixture=f.read(path/'fixture.json')
    f.require(fixture['trials']==f.trials(m['kind']) and fixture['work']==f.commands(fixture['oracle'],fixture['trials']) and
              fixture['host_libm_used'] is False and fixture['query_conversion_outside_roi'] is True,
              'Fixture/work contract changed')
    f.require(f.sha(path/'inputs/target/oracle.json')==f.ANCHORS['oracle.json'] and
              fixture['oracle']==f.read(path/'inputs/target/oracle.json'),'Independent oracle replaced')
    return m


def parse(text,keys,hexes=()):
    result={}
    for token in text.split():
        f.require(token.count('=')==1,'Malformed field')
        k,v=token.split('=')
        f.require(k in keys and k not in result and re.fullmatch('[0-9a-fA-F]+' if k in hexes else '[0-9]+',v),
                  'Unknown/duplicate/invalid field')
        result[k]=int(v,16 if k in hexes else 10)
    f.require(set(result)==set(keys),'Missing fields');return result


SCHEMAS={
    'CALL':'trial case requested frm initial begin returned end fcsr vcsr vstart groups errors',
    'GROUP':'trial group first rows q k v out',
    'MEMORY':'trial query_hash guard_hash guard_bytes','OUT':'trial index bits',
    'DATA':'bytes hash','DONE':'calls errors'}


def numerical(text,fixture,data):
    rows=[]
    for line in text.splitlines():
        if not line.startswith('FEATURE_'):continue
        tag,payload=line[len('FEATURE_'):].split(' ',1)
        f.require(tag in SCHEMAS,'Firmware failure/unknown record')
        rows.append((tag,parse(payload,SCHEMAS[tag].split(),
                              ('q','k','v','out','bits','query_hash','guard_hash','hash'))))
    cursor=0;outputs=[];calls=[];last=0
    def take(tag):
        nonlocal cursor
        f.require(cursor<len(rows) and rows[cursor][0]==tag,'Missing/duplicate/out-of-order '+tag)
        value=rows[cursor][1];cursor+=1;return value
    for t,tr in enumerate(fixture['trials']):
        c=fixture['oracle']['cases'][tr['case']]['case'];r=take('CALL');n=c['heads']*c['dimension']
        heads=c.get('rows',c['heads']);groups=c['heads']//heads
        want=dict(trial=t,case=tr['case'],requested=tr['requested'],frm=tr['frm'],
            initial=tr['frm']*32+tr['initial_flags'],vcsr=5,vstart=0,groups=groups,errors=0)
        f.require(all(r[k]==v for k,v in want.items()) and last<r['begin']<r['returned']<r['end'],
                  'Call/CSR/timing/terminal mismatch');last=r['end']
        expected=fixture['oracle']['cases'][tr['case']]['expected']
        if not tr['frm']:f.require(r['fcsr']==expected['fflags']|tr['initial_flags'],'Natural/sticky FCSR mismatch')
        else:f.require(r['fcsr']>>5==tr['frm'] and r['fcsr']&tr['initial_flags']==tr['initial_flags'],
                       'Non-RNE/sticky controls not preserved')
        previous=None
        for g in range(groups):
            group=take('GROUP')
            f.require({k:group[k] for k in ('trial','group','first','rows')}==
                      dict(trial=t,group=g,first=g*heads,rows=heads) and
                      all(group[k]>0 and group[k]%64==0 for k in ('q','k','v','out')),'Group-local layout')
            if previous:
                f.require(all(group[k]-previous[k]==delta for k,delta in
                    (('q',heads*256),('out',heads*512),('k',65536),('v',65536))),'Group offsets/bases')
            previous=group
        memory=take('MEMORY')
        q=bytearray(b'\xa5'*1536)
        for h,row in enumerate(c.get('query_rows',[0,1])):
            q[h*256:h*256+c['dimension']*2]=data[row*256:row*256+c['dimension']*2]
        guard_bytes=384+(768-n)*6+(2048-heads*c['dimension'])*2+(8-heads)*268+32
        f.require(memory==dict(trial=t,query_hash=f.fnv(q),guard_hash=f.fnv(b'\xa5'*guard_bytes),
                              guard_bytes=guard_bytes),'Memory/query/inactive guards changed')
        actual=[]
        for i in range(n):
            value=take('OUT');f.require(value['trial']==t and value['index']==i,'Output index/order')
            actual.append(value['bits'])
        if not tr['frm']:f.require(actual==expected['bits'],'Independent target-libm/SoftFloat output mismatch')
        if t and fixture['trials'][t-1]['case']==tr['case'] and fixture['trials'][t-1]['frm']==tr['frm']:
            f.require(actual==outputs[-1],'OFF/ON outputs differ')
        outputs.append(actual);calls.append(r)
    f.require(take('DATA')==dict(bytes=fixture['data_bytes'],hash=fixture['data_hash']) and
              take('DONE')==dict(calls=len(calls),errors=0) and cursor==len(rows),'Input data/terminal mismatch')
    if fixture['kind']=='functional':
        f.require(outputs[-1]==outputs[-2] and calls[-1]['fcsr']==calls[-2]['fcsr'],
                  'Non-RNE fallback differs from same-FRM OFF')
    elapsed=[r['end']-r['begin'] for r in calls]
    timing=dict(full_call_cycles=elapsed,issue_cycles=[r['returned']-r['begin'] for r in calls],
                final_drain_cycles=[r['end']-r['returned'] for r in calls])
    if fixture['kind']=='perf':
        a=(elapsed[0]+elapsed[3])/2;b=(elapsed[1]+elapsed[2])/2
        timing.update(strong_baseline_mean=a,resident_mean=b,full_call_speedup=a/b)
    return dict(calls=len(calls),output_values=sum(map(len,outputs)),bitexact=True,
                fcsr=[r['fcsr'] for r in calls],fflags_checked=True,vcsr_vstart_checked=True,
                non_rne_pair_checked=fixture['kind']=='functional',timing=timing)


def legacy_work(text,fixture):
    old=support('legacy/check.py');want=fixture['work']['legacy'];rows=[];summaries=[];totals=Counter()
    for line in text.splitlines():
        if line.startswith('[AKV_PERF] '):
            f.require(not summaries and len(rows)<len(want),'Extra/post-summary legacy work')
            r=old.parse_fields(line[11:],old.PERF_FIELDS);i=len(rows)
            f.require(r['seq']==i+1 and all(r[k]==v for k,v in want[i].items()) and r['success']==1 and
                      r['busy_cycles']>0 and all(r[k]==0 for k in
                        ('fault','validation_fault','validation_error','read_fault','v2_rejected')),'Legacy shape/order/fault')
            f.require(r['context_ready']==int(r['command']!=3) and r['read_payload_bytes']==
                      r['q_external_bytes']+r['kv_external_bytes']+64*r['v2_full'],'Lifecycle/payload mismatch')
            for k in old.SUMMARY_FIELDS-{'records','success_records','fault_records','validation_fault_records'}:
                totals[k]=max(totals[k],r[k]) if k=='read_outstanding_max' else totals[k]+r[k]
            rows.append(r)
        elif line.startswith('[AKV_PERF_SUMMARY] '):
            summaries.append(old.parse_fields(line[len('[AKV_PERF_SUMMARY] '):],old.SUMMARY_FIELDS))
        elif '[AKV_PERF' in line:raise ValueError('Malformed legacy probe')
    f.require(len(rows)==len(want) and summaries==[dict(totals,records=len(want),success_records=len(want),
              fault_records=0,validation_fault_records=0)],'Legacy work/summary incomplete')
    return dict(commands=len(rows),per_call=fixture['work']['per_call'],summary=summaries[0])


def shape(c):
    t,h,d=c['tokens'],c['heads'],c['dimension']
    if c['mode']=='QK':
        lanes=support('geometry.py').layout(t,h)
        writes=[{w['address']:w['byte_enable'] for w in lane['writes']} for lane in lanes]
        fma=[len(w)*d for w in writes];elements=[lane['elements'] for lane in lanes]
        counts=dict(tokens=t,dimensions=d,heads=h,query_base=c['base'],source_words=0,
            seed_words=sum(map(len,writes)),coefficients=d*min(t,4),value_words=d*sum((n+3)//4 for n in elements),
            result_words=sum(map(len,writes)),final_acks=sum(map(len,writes)),query_reads=d//16*h,
            columns=d//4,active=(1<<min(t,4))-1)
        opcode,eew,vl=0x0605705b,2,128
    else:
        writes=[{8*head+word:255 for head in range(h) for word in range(d//16)} for _ in range(4)]
        fma=[d//16*h*t]*4;elements=[d//4]*4
        counts=dict(control=t-1|(h-1)<<6|{64:0,128:1,96:2}[d]<<7,tokens=t,words=d//16,heads=h,
            source_words=96,seed_words=4*d//16*h,coefficients=4*t,value_words=4*t*d//16,
            result_words=4*d//16*h,final_acks=4*d//16*h,row_reads=t*d//16)
        opcode,eew,vl=0x0485705b,1,256
    return dict(writes=writes,fma=fma,elements=elements,counts=counts,opcode=opcode,eew=eew,vl=vl)


def resident_work(text,fixture):
    want=fixture['work']['resident'];records=[];lanes={}
    for line in text.splitlines():
        if not line.startswith('[RESIDENT_'):continue
        m=re.fullmatch(r'\[RESIDENT_(QK|PV)_(LANE|PERF)\] (.+)',line)
        f.require(m and len(records)<len(want),'Unknown/extra resident probe')
        c=want[len(records)];s=shape(c);f.require(m[1]==c['mode'],'Resident stage order')
        keys=set('lane vid tokens elements heads issued returned writes flags error'.split())
        if m[2]=='LANE':
            if m[1]=='QK':keys.add('dimensions')
            r=parse(m[3],keys);lane=r['lane']
            f.require(lane in range(4) and lane not in lanes and s['writes'][lane],'Duplicate/inactive lane')
            expected=dict(tokens=c['tokens'],elements=s['elements'][lane],heads=c['heads'],
                issued=s['fma'][lane],returned=s['fma'][lane],writes=len(s['writes'][lane]),error=0)
            if m[1]=='QK':expected['dimensions']=c['dimension']
            f.require(all(r[k]==v for k,v in expected.items()) and r['vid'] in range(8) and r['flags'] in range(32),
                      'Lane FMA/write accounting');lanes[lane]=r
        else:
            # The monitor prints active as binary, all other fields decimal.
            fields=m[3].split();r=parse(m[3],set(s['counts'])|{'seq','vid','cycles','flags','error'})
            if c['mode']=='QK':r['active']=int(next(x.split('=')[1] for x in fields if x.startswith('active=')),2)
            f.require(all(r[k]==v for k,v in s['counts'].items()) and r['seq']==len(records)+1 and
                r['cycles']>0 and r['error']==0 and r['vid'] in range(8) and
                set(lanes)=={l for l in range(4) if s['writes'][l]},'Resident geometry/active lanes')
            flags=0
            for lane in lanes.values():f.require(lane['vid']==r['vid'],'Lane VID');flags|=lane['flags']
            f.require(flags==r['flags']==f.local_flags(fixture['oracle'],fixture['trials'],c),
                      'Hardware flags include prep/sticky or lack arithmetic flags')
            records.append(dict(command=c,terminal=r,lanes=lanes));lanes={}
    f.require(len(records)==len(want) and not lanes,'Incomplete resident work');return records


def vector_work(path,fixture):
    expected=fixture['work']['resident'];live={};done=[];seen=set();signatures=[];index=0;last=-1;config=0
    with Path(path).open(newline='') as stream:
        reader=csv.DictReader(stream)
        keys=set('cycle event arch_seq vid lane source insn use_vd vd eew vl vstart addr be wdata nr_lanes vlen_bits'.split())
        f.require(reader.fieldnames and len(reader.fieldnames)==len(set(reader.fieldnames)) and keys<=set(reader.fieldnames),
                  'Vector trace schema')
        for r in reader:
            f.require(None not in r and all(v is not None for v in r.values()),'Malformed vector record')
            cycle=int(r['cycle']);event=r['event']
            f.require(cycle>=last and (r['nr_lanes'],r['vlen_bits'])==('4','1024'),'Vector configuration/order');last=cycle
            if event=='config':
                f.require(config==0 and cycle==0 and not seen,'Unexpected reset/config');config=1;continue
            f.require(config==1 and event in ('alloc','write','done'),'Unknown vector event/reset')
            word=int(r['insn'],16)
            if event=='alloc' and word&0x707f in (0x305b,0x705b):signatures.append(word)
            if word not in (0x0605705b,0x0485705b):continue
            key=int(r['arch_seq']),int(r['vid'])
            if event=='alloc':
                f.require(not live and key not in seen and index<len(expected),'Duplicate/overlapping resident work')
                s=shape(expected[index]);index+=1;f.require(word==s['opcode'],'Resident opcode order')
                f.require(key[0]>0 and key[1] in range(8),'Invalid resident identity')
                live[key]=dict(shape=s,writes=set());seen.add(key)
            f.require(key in live,'Unowned resident event');entry=live[key];s=entry['shape']
            f.require(word==s['opcode'] and tuple(int(r[k]) for k in ('use_vd','vd','eew','vl','vstart'))==
                      (1,0,s['eew'],s['vl'],0),'Resident allocation metadata')
            if event=='write':
                lane,addr=int(r['lane']),int(r['addr'])
                f.require(lane in range(4) and addr in s['writes'][lane] and int(r['be'],16)==s['writes'][lane][addr] and
                          int(r['source'])==4 and re.fullmatch('[0-9a-fA-F]{16}',r['wdata']) and
                          (lane,addr) not in entry['writes'],'Resident write/byte-mask/duplicate')
                entry['writes'].add((lane,addr))
            elif event=='done':
                f.require(entry['writes']=={(l,a) for l in range(4) for a in s['writes'][l]},'Incomplete resident result')
                done.append(dict(vid=key[1],words=len(entry['writes'])));del live[key]
    f.require(config==1 and not live and index==len(expected) and signatures==fixture['work']['signatures'],
              'Actual native/resident opcode signatures/work mismatch')
    return dict(resident_commands=len(done),replay_resident_allocations=len(signatures),architectural_writes=done)


ENTRY_NAMES=('akv_decode_execute','akv_experimental_attention_execute_features_v2_native',
    'akv_experimental_qk_f16_pair_panel4','__wrap_akv_experimental_pv_f16_pair',
    'akv_experimental_resident_qk','akv_experimental_resident_pv','akv_experimental_resident_pv_prepare')


def expected_entries(fixture,tr):
    c=fixture['oracle']['cases'][tr['case']]['case'];rows=c.get('rows',c['heads']);groups=c['heads']//rows
    tiles=(c['tokens']+63)//64;on=tr['requested'] and not tr['frm']
    pairs=groups*tiles*(rows//2);resident=groups*tiles*((rows+1)//2) if on else 0
    return dict(zip((*ENTRY_NAMES,'rotation_body'),(2,groups,0 if on else pairs,0 if on else pairs,
                     resident,resident,resident,0 if on else pairs)))


def actual_entries(path,fixture,binding):
    points={v['pc']:(name,v['insn']) for name,v in binding.items()};records=[];active=None;last=-1
    with Path(path).open(newline='') as stream:
        reader=csv.DictReader(stream)
        f.require(reader.fieldnames and {'cycle','event','pc','insn','trap'}<=set(reader.fieldnames),'Commit schema')
        for r in reader:
            f.require(None not in r and all(v is not None for v in r.values()),'Malformed retirement record')
            cycle=int(r['cycle']);f.require(cycle>=last,'Retire order');last=cycle
            if r['event']!='retire':continue
            f.require(int(r['trap'])==0,'Unexpected retired trap');pc=int(r['pc'],16)
            if pc not in points:continue
            name,word=points[pc];f.require(int(r['insn'],16)==word,'ELF PC/instruction binding mismatch')
            if name=='feature_full_call':
                f.require(active is None and len(records)<len(fixture['trials']),'Overlapping/extra SDK call')
                active=Counter(dict.fromkeys((*ENTRY_NAMES,'rotation_body'),0))
            elif name=='feature_terminal_marker':
                f.require(active is not None and dict(active)==expected_entries(fixture,fixture['trials'][len(records)]),
                          'Wrong actual SDK/rotation-body/candidate-bypass entries')
                records.append(dict(active));active=None
            else:
                f.require(active is not None,'Arithmetic/SDK entry outside full call');active[name]+=1
    f.require(active is None and len(records)==len(fixture['trials']),'Incomplete retired SDK calls')
    return dict(calls=len(records),per_call=records,rotation_branch_body_checked=True)


def check(build,log,vector,commit):
    m=build_receipt(build);fixture=f.read(Path(build)/'fixture.json');text=Path(log).read_text()
    support('legacy/check.py').classify_simulator(text)
    numbers=numerical(text,fixture,(Path(build)/'data.bin').read_bytes())
    legacy=legacy_work(text,fixture);resident=resident_work(text,fixture);vectors=vector_work(vector,fixture)
    f.require(all(r['terminal']['vid']==v['vid'] and r['terminal']['result_words']==v['words']
                  for r,v in zip(resident,vectors['architectural_writes'])),'Probe/actual write identity mismatch')
    return dict(state='SDK_FEATURES_CHECKED',scope=m['scope'],numerical=numbers,legacy_work=legacy,
        resident_work=resident,vector_work=vectors,actual_entries=actual_entries(commit,fixture,m['elf_contract']['entries']),
        protocol_checked=False,post_image_checked=False,performance_acceptance=False,whole_model=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    for n in ('build','log','vector','commit'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();print(json.dumps(check(a.build,a.log,a.vector,a.commit),indent=2))
