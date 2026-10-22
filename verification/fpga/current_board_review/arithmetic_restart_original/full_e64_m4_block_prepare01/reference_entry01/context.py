"""Exact e64/m4 software02 identity and original model; no compilation."""
import hashlib
import json
import os
from pathlib import Path
import struct
HERE=Path(__file__).resolve().parent
SOFT=HERE.parent/'software02'
A=HERE.parents[1]
MODEL=A/'full_e64_m4_source_model01/generated01'
def require(ok,why):
    if not ok:raise ValueError(why)
def read(p):return json.loads(Path(p).read_text())
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def save(p,obj):
    with Path(p).open('x') as f:json.dump(obj,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def emit(p,text):
    with Path(p).open('x') as f:f.write(text);f.flush();os.fsync(f.fileno())
def width(code,write):
    if code&3!=3:
        q,k=code&3,(code>>13)&7
        if q in (0,2) and k in ((6,7) if write else (2,3)):return 4 if k in (2,6) else 8
        return None
    if code&127==(35 if write else 3):return 1<<(((code>>12)&7)&3)
    return None
def definition(backend='spike'):return read(HERE/(backend+'_spec.json'))
def artifacts(backend='spike'):
    spec=definition(backend);source=read(MODEL/'calls.json');seeds=read(MODEL/'seed_inputs.json')
    inputs=struct.unpack('<8Q',(MODEL/'fp_inputs8_u64le.bin').read_bytes())
    dictionary=struct.unpack('<15888Q',(MODEL/'dictionary64.bin').read_bytes())
    rawgold=(MODEL/'gold_u64le.bin').read_bytes();rows=[]
    require(len(rawgold)==5985*528,'Whole source oracle, no partial scope')
    for i,r in enumerate(source):
        r=dict(r);seed=r['seed'];r['si']=r['trial']
        r['a']=[inputs[(j+seed)%8] for j in range(64)] if r['op']>=25 else seeds[seed]['a']
        r['b']=[inputs[(3*j+seed)%8] for j in range(64)] if r['op']>=25 else seeds[seed]['b']
        r['words']=[dictionary[8*r['ids'][j//8]+j%8] for j in range(66)]
        wordbytes=struct.pack('<66Q',*r['words'])
        require(wordbytes==rawgold[528*i:528*(i+1)] and hashlib.sha256(wordbytes).hexdigest()==r['output_sha256'],'Independent full528B model/dictionary agreement')
        mask=[0]*128
        for j in range(64):
            if r['mode']==0 or r['mode']==1 and j%2==1 or r['mode']==2 and j%7==2:mask[j//8]|=1<<(j%8)
        r['mask']=mask
        require(hashlib.sha256(struct.pack('<128Q',*(r['a']+r['b']))).hexdigest()==r['input_sha256'],'Exact original input/RNG words')
        rows.append(r)
    require(len(rows)==5985,'Exact all5985 source calls')
    return spec['symbols'],{int(p):v for p,v in spec['code'].items()},spec['helpers'],rows
