"""Read frozen software02 only. No generation, compilation or execution."""
import hashlib
import json
import os
from pathlib import Path
import re
HERE=Path(__file__).resolve().parent
SOFT=HERE.parent/'full_e64_m2_block_software02'
def require(b,s):
    if not b:raise ValueError(s)
def read(p):return json.loads(Path(p).read_text())
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def save(p,v):
    with Path(p).open('x') as f:json.dump(v,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def emit(p,s):
    with Path(p).open('x') as f:f.write(s);f.flush();os.fsync(f.fileno())
def artifacts():
    code={int(m[1],16):int(m[2],16) for m in re.finditer(r'^[ \t]*([0-9a-f]+):[ \t]+([0-9a-f]{4,8})[ \t]',(SOFT/'spike/program.dis').read_text(),re.M)}
    info=read(SOFT/'audit_artifacts02/RESULT.json')['compiled']['spike']
    source=read(SOFT/'sequence.json');seeds=read(SOFT/'seed_inputs.json')
    header=(SOFT/'original/operations.h').read_text();inputs=[int(x,16) for x in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)',header.split('fp_inputs[8]')[1].split('};')[0])]
    table=(SOFT/'dictionary.h').read_text().split('expected_indices')[0]
    words=[int(x,16) for x in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)',table)]
    rows=[]
    for row in source:
        row=dict(row);seed=row['seed'];isfp=row['op']>=25
        row['a']=[inputs[(i+seed)%8] for i in range(32)] if isfp else seeds[seed]['a']
        row['b']=[inputs[(3*i+seed)%8] for i in range(32)] if isfp else seeds[seed]['b']
        row['words']=[words[8*row['indices'][i//8]+i%8] for i in range(34)]
        row['expected']=row['words'][1:33]
        mask=[0]*128
        for i in range(32):
            if row['mode']==0 or row['mode']==1 and i%2==1 or row['mode']==2 and i%7==2:mask[i//8]|=1<<(i%8)
        row['mask']=mask;rows.append(row)
    require(len(rows)==5985 and len(inputs)==8 and len(words)==1282*8,'Exact source/model dimensions')
    return read(SOFT/'spike/symbols.json'),code,info['helper_windows'],rows
def width(code,write):
    if code&3!=3:
        q,k=code&3,(code>>13)&7
        if q in (0,2) and k in ((6,7) if write else (2,3)):return 4 if k in (2,6) else 8
        return None
    if code&127==(35 if write else 3):return 1<<(((code>>12)&7)&3)
    return None
