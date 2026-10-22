"""Immutable original integer oracle plus exact successor ELF context."""
import hashlib,importlib.util,json,re,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;A=HERE.parent
SOFT=A/'full_e8_m8_sentinel_mask_software01'
OLD=A/'full_e8_m8_block_unrolled01'
def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def save(p,v):
    with Path(p).open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m
original=load('sentinel_immutable_source_model',OLD/'model.py')
isa=load('sentinel_immutable_memory_decoder',A/'full_small2_vcs_m6_plan01/checker.py')
memory_op=isa.memory_op
MASK64=(1<<64)-1
ELF=SOFT/'spike/program.elf'
ELF_SHA='b1cd154e319211187f8e6e34f7e8f40398ebdc65f035e033ed7b8f8141d15c0c'
MARKER='RVV_MATRIX_PASS sew=8 vlmax=1024 cases=4095 elements=4193280 errors=0 seeds=3 guard_tail_mask_vstart=checked'
def console_gate(text):
    require(text.splitlines()==[MARKER] and not re.search(r'FAIL|TRAP|ERROR|UNSUPPORTED',text),'Exact fullsource marker/failure veto')
def park_gate(pc,insn,rest,profile):
    require(pc==profile['park_pc'] and insn==profile['park_insn'] and not re.search(r'\b(?:mem|x\s*\d+|v\s*\d+|c\d+_)',rest),'EOFPARK exact no late data/CSR/GPR effects')
def artifacts():
    require(sha(ELF)==ELF_SHA,'Exact actual new Spike ELF')
    symbols=read(SOFT/'spike/symbols.json')
    code={int(m[1],16):int(m[2],16) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',(SOFT/'spike/program.dis').read_text(),re.M)}
    cfg=load('sentinel_linked_profile_cfg',SOFT/'linked_cfg_cost.py');machine=cfg.Machine(SOFT/'spike')
    helpers={n:[dict(pc=x['pc'],insn=x['insn']) for x in machine.functions[n]] for n in ['capacity']+['op_'+str(i) for i in range(25)]}
    return symbols,code,helpers,machine
def initial_reader(raw):
    h=struct.unpack_from('<16sHHIQQQIHHHHHH',raw);segments=[]
    for i in range(h[10]):
        kind,flags,off,va,pa,fs,ms,align=struct.unpack_from('<IIQQQQQQ',raw,h[5]+i*h[9])
        if kind==1:segments.append((va,raw[off:off+fs],ms))
    def readbyte(address):
        for va,data,size in segments:
            if va<=address<va+size:return data[address-va] if address-va<len(data) else 0
        raise ValueError('Unknown mapped memory '+hex(address))
    return readbyte
