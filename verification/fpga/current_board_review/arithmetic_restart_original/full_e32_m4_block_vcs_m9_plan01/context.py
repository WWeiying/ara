"""Pinned compiled artifacts; no compile, model generation or reference here."""
import functools
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent/'full_e32_m4_block_prepare01'
SOFT=ROOT/'software02'
A=HERE.parent
MODEL=A/'full_e32_m4_source_model01/generated01'
def require(ok,why):
    if not ok:raise ValueError(why)
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,value):
    with Path(p).open('x') as f:json.dump(value,f,indent=2);f.write('\n')
def emit(p,value):
    with Path(p).open('x') as f:f.write(value)
spec=importlib.util.spec_from_file_location('pinned_leaf_cfg',SOFT/'leaf_cfg.py')
leaf=importlib.util.module_from_spec(spec);spec.loader.exec_module(leaf)

def width(code,write):
    if code&3!=3:
        quadrant,kind=code&3,(code>>13)&7
        if quadrant in (0,2) and kind in ((6,7) if write else (2,3)):return 4 if kind in (2,6) else 8
        return None
    if code&127==(35 if write else 3):return 1<<(((code>>12)&7)&3)
    return None

@functools.lru_cache(maxsize=1)
def artifacts():
    require(sha(SOFT/'soc/program.elf')=='6adde60cb19b74d8aa1e1c44a2219042d2a482da18e824772ba2cdf47bd940bf','Exact authorized SoC ELF')
    f=read(SOFT/'soc/functions.json');s=read(SOFT/'soc/symbols.json');raw=(SOFT/'soc/program.elf').read_bytes()
    code={x['pc']:x['insn'] for v in f.values() for x in v}
    parsed={int(m[1],16):int(m[2],16) for m in re.finditer(r'^[ \t]*([0-9a-f]+):[ \t]+([0-9a-f]{4,8})[ \t]+\S+', (SOFT/'soc/program.dis').read_text(),re.M)}
    require(parsed==code,'Complete horizontal-whitespace disassembly coverage, not a partial PC whitelist')
    for pc,w in code.items():require(leaf.old.executable_bytes(raw,pc,4 if w&3==3 else 2)==w.to_bytes(4 if w&3==3 else 2,'little'),'ELF executable-byte crosscheck')
    helpers={n:f[n] for n in ['capacity']+[f'op_{i}' for i in range(35)]}
    source=read(MODEL/'calls.json');seeds=read(MODEL/'seed_inputs.json');gold=(MODEL/'gold_u32le.bin').read_bytes()
    fp=struct.unpack('<8I',(MODEL/'fp_inputs8_u32le.bin').read_bytes());rows=[]
    fpbanks={(seed,bank):[fp[((i if bank=='a' else 3*i)+seed)%8] for i in range(128)] for seed in range(3) for bank in ('a','b')}
    masks=[]
    for mode in range(3):
        mask=bytearray(128)
        for i in range(128):
            if mode==0 or (mode==1 and i%2) or (mode==2 and i%7==2):mask[i//8]|=1<<(i%8)
        masks.append(bytes(mask))
    for i,r in enumerate(source):
        row=dict(r,si=r['trial'],mask=masks[r['mode']],gold=gold[520*i:520*(i+1)])
        for bank in ('a','b'):row[bank]=fpbanks[(r['seed'],bank)] if r['op']>=25 else seeds[r['seed']][bank]
        rows.append(row)
    require(len(rows)==5985 and len(gold)==5985*520,'Complete original ledger/oracle')
    return s,code,helpers,rows

@functools.lru_cache(maxsize=1)
def linked():
    s,code,helpers,rows=artifacts();f=read(SOFT/'soc/functions.json')
    return f,leaf.Leaf(f,s,(SOFT/'soc/program.elf').read_bytes()),read(SOFT/'artifact01/soc.json')

MARKER='RVV_MATRIX_PASS sew=32 vlmax=128 cases=5985 elements=766080 errors=0 seeds=3 guard_tail_mask_vstart=checked'
def marker_decode(value):
    require(value==MARKER,'Exact original full-scope marker')
    return dict(sew=32,vlmax=128,cases=5985,elements=766080,errors=0,seeds=3)
def marker_encode(fields):
    require(fields==dict(sew=32,vlmax=128,cases=5985,elements=766080,errors=0,seeds=3),'Exact marker scope fields')
    return 'RVV_MATRIX_PASS sew={sew} vlmax={vlmax} cases={cases} elements={elements} errors={errors} seeds={seeds} guard_tail_mask_vstart=checked'.format(**fields)
