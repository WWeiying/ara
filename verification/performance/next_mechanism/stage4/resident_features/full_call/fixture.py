"""Transport/layout contracts consuming the frozen target oracle, never host libm."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT=Path('/home/wangwy/openproject/ara_dsa')
OUT=ROOT.parent/'ara_dsa_signoff_integration/verification/out'
TARGET=OUT/'stage4_resident_features_target_20261110_02'
SDK='f50092f2d22238c6be4b6c159a1ad71a4ea68678'
DATA=OUT/'e2e_qwen3_f16_native_data_20261106_02'
ANCHORS={
    'result.json':'fda583a5ac2ee41b755e658b32b0f7638225b1f180939cfd06c8155d15c7f379',
    'oracle.json':'37f41a0744f7aee67c24271b555e142b8e085ae167022864cc2072d564d3a151',
    'target-libm.json':'b778db430da0579430716f318ceb6759d6f73a35a3a901a334df1fcadd095112',
    'build-contract.json':'3094ba6e04458f052fa973dba1e2e0c6ef8c815aba77fe7a3292f519d1d67efa',
    'source-pins.json':'f41ad4dda44ec1419af00f31ed8a069298b63462a2125c7d84d975b1ebb17889'}
SCOPE='Feature-bearing actual SDK complete calls; strong panel4 QK/rotating PV baseline; no GGML/default deployment acceptance'
LIBM_SHA='9a48df5756070cc13f710fff77fbff6d35e45c52e29303bd506756cf341e6f26'


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    def pairs(rows):
        d={}
        for k,v in rows:
            require(k not in d,'Duplicate JSON key');d[k]=v
        return d
    return json.loads(Path(path).read_text(),object_pairs_hook=pairs)


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def verify(pins):
    for p,h in pins.items():require(sha(p)==h,'Identity drift: '+str(p))


def fnv(raw):
    result=14695981039346656037
    for b in raw:result=((result^b)*1099511628211)&((1<<64)-1)
    return result


def target():
    anchors={str(TARGET/n):h for n,h in ANCHORS.items()};verify(anchors)
    r=read(TARGET/'result.json');pins=read(TARGET/'source-pins.json')
    require(r['state']=='ORACLE_PROBES_PASS_FIRMWARE_PENDING' and r['post_pins_match'] is True and
            r['libm_samples']==27 and r['cases']==9 and r['source_pins_sha256']==ANCHORS['source-pins.json'],
            'Not the reviewed target02 oracle')
    verify(pins);verify(r['artifacts'])
    require({str(p):sha(p) for p in TARGET.rglob('*') if p.is_file() and p.name!='result.json'}==r['artifacts'],
            'Target artifact membership changed')
    o=read(TARGET/'oracle.json');contract=read(TARGET/'build-contract.json')
    require(o['host_libm_used'] is False and o['query_conversion_outside_roi'] is True and
            o['initial_fflags_cases']==[0,8] and len(o['cases'])==9 and contract['sdk_revision']==SDK,
            'Oracle numerical/SDK contract changed')
    for item in o['cases']:
        expected=item['expected'];bits=expected['bits']
        require(len(bits)==item['case']['heads']*item['case']['dimension'] and
                hashlib.sha256(struct.pack('<'+'I'*len(bits),*bits)).hexdigest()==expected['output_sha256'],
                'Incomplete oracle output')
    return o,contract,pins|r['artifacts']|anchors


def trials(kind):
    require(kind in ('perf','functional'),'Invalid firmware kind')
    if kind=='perf':
        return [dict(case=0,requested=arm,initial_flags=seed,frm=0)
                for arm,seed in zip((0,1,1,0),(0,8,0,8))]
    return [dict(case=i,requested=arm,initial_flags=8*(i%2),frm=0)
            for i in range(1,9) for arm in (0,1)]+[
                dict(case=1,requested=arm,initial_flags=8,frm=1) for arm in (0,1)]


def commands(o,ts):
    legacy,resident,signatures=[],[],[]
    per_call=[]
    fields='command v2_full v2_refill v2_row_load v2_column_load v2_column_panel v2_logical_column full refill load release q_external_bytes kv_external_bytes replay_bytes'.split()
    def add(code,**values):
        row=dict.fromkeys(fields,0);row.update(command=code,**values);legacy.append(row)
    for trial,tr in enumerate(ts):
        c=o['cases'][tr['case']]['case'];d=c['dimension'];rows=c.get('rows',c['heads']);groups=c['heads']//rows
        count0=len(legacy);on=tr['requested'] and not tr['frm']
        for group in range(groups):
            for start in range(0,c['tokens'],64):
                t=min(64,c['tokens']-start)
                add(4 if start==0 else 5,v2_full=int(start==0),v2_refill=int(start!=0),
                    q_external_bytes=rows*d*2 if start==0 else 0,kv_external_bytes=t*d*4)
                if on:
                    for mode in ('QK','PV'):
                        for base in range(0,rows,2):
                            resident.append(dict(trial=trial,group=group,tile=start,mode=mode,
                                tokens=t,dimension=d,heads=min(2,rows-base),base=base))
                            signatures.append(0x0605705b if mode=='QK' else 0x0485705b)
                else:
                    for _ in range(rows//2):
                        for _ in range(d//4):
                            add(6,v2_column_load=1,v2_column_panel=1,v2_logical_column=4,replay_bytes=t*8)
                            signatures.append(0x0205745b)
                    if rows%2:
                        for _ in range(d):
                            add(6,v2_column_load=1,v2_logical_column=1,replay_bytes=t*2)
                            signatures.append(0x0005745b)
                    opcode={64:0x0005345b,96:0x0405345b,128:0x0205345b}[d]
                    for _ in range(rows//2):
                        for token in range(t):
                            add(2,v2_row_load=1,load=1,replay_bytes=d*2)
                            signatures.append(opcode+(0x100 if token%2 else 0))
                    if rows%2:
                        for _ in range(t):
                            add(2,v2_row_load=1,load=1,replay_bytes=d*2);signatures.append(opcode)
            add(3,release=1)
        per_call.append(len(legacy)-count0)
    return dict(legacy=legacy,resident=resident,signatures=signatures,per_call=per_call)


def local_flags(o,ts,c):
    case=o['cases'][ts[c['trial']]['case']];rows=case['case'].get('rows',case['case']['heads'])
    heads=range(c['group']*rows+c['base'],c['group']*rows+c['base']+c['heads'])
    flags=0
    for h in heads:
        matches=[x['fflags'] for x in case['expected']['phases'] if x['phase']==[c['mode'],h,c['tile']]]
        require(len(matches)==1,'Missing command-local hardware flags');flags|=matches[0]
    return flags


def generate(output,kind,o):
    output=Path(output);ts=trials(kind)
    capture={n:(DATA/('decode_'+n+'.bin')).read_bytes() for n in ('query_f16','key','value','mask')}
    payload=bytearray();offsets={}
    for name,raw in capture.items():
        offsets[name]=len(payload);payload.extend(raw*2 if name in ('key','value') else raw)
    masks=[]
    for item in o['cases']:
        raw=bytearray(capture['mask'])
        for token,bits in item['case']['mask_override']:struct.pack_into('<H',raw,token*2,bits)
        masks.append(len(payload));payload.extend(raw)
    (output/'data.bin').write_bytes(payload)
    (output/'data.S').write_text('.section .rodata.features,"a",@progbits\n.balign 64\n'
        '.global feature_data\nfeature_data:\n.incbin '+json.dumps(str(output/'data.bin'))+
        '\n.section .note.GNU-stack,"",@progbits\n')
    def fl(value):return struct.unpack('<f',struct.pack('<I',value))[0].hex()+'f'
    def features(v):
        return '{'+','.join('.'+k+'='+('{' + ','.join(fl(x) for x in val) + '}' if isinstance(val,list)
            else fl(val) if k=='softcap' else str(val)) for k,val in v.items())+'}'
    header=['#ifndef FEATURE_FIXTURE_H','#define FEATURE_FIXTURE_H',
        '#include "akv/akv_features.h"','extern const unsigned char feature_data[];',
        'typedef struct { unsigned d,heads,rows,tokens,mask_offset; unsigned query_rows[6]; akv_attention_features_t features[2]; } feature_case_t;',
        'typedef struct { unsigned index,requested,initial_flags,frm; } feature_trial_t;',
        '#define FEATURE_CALLS '+str(len(ts)),'#define FEATURE_DATA_BYTES '+str(len(payload)),
        '#define FEATURE_DATA_HASH UINT64_C(0x%x)'%fnv(payload)]
    for name,off in offsets.items():header.append('#define FEATURE_'+name.upper()+'_OFFSET '+str(off))
    header+=['static const feature_case_t feature_cases[] = {']
    for i,item in enumerate(o['cases']):
        c=item['case'];fs=c['features'] if isinstance(c['features'],list) else [c['features']]
        header.append('{%u,%u,%u,%u,%u,{%s},{%s}},'%(c['dimension'],c['heads'],c.get('rows',c['heads']),
            c['tokens'],masks[i],','.join(map(str,c.get('query_rows',[0,1]))),','.join(features(v) for v in fs)))
    header+=['};','static const feature_trial_t feature_trials[] = {']
    header+=['{%u,%u,%u,%u},'%(t['case'],t['requested'],t['initial_flags'],t['frm']) for t in ts]
    header+=['};','static const unsigned feature_flags[] = {'+
             ','.join(str(x['expected']['fflags']) for x in o['cases'])+'};','#endif']
    (output/'fixture.h').write_text('\n'.join(header)+'\n')
    work=commands(o,ts)
    return dict(kind=kind,trials=ts,oracle=o,data_bytes=len(payload),data_hash=fnv(payload),work=work,
                query_conversion_outside_roi=True,host_libm_used=False,scope=SCOPE)
