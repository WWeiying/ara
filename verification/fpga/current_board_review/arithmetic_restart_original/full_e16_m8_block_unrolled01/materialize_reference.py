"""Explicit scoped observer successor; preserve the immutable e8 predecessor."""
import ast
import difflib
import json
from pathlib import Path
import re
import prepare as p
HERE=p.HERE
PARENT=HERE.parent
profile={}
proof=json.loads((HERE/'proof.json').read_text())
for backend in ('soc','spike'):
    info=proof['backends'][backend];symbols=info['symbols'];code={int(pc):i for pc,i in info['code'].items()}
    dis=(HERE/backend/'program.dis').read_text()
    functions={name:int(address,16) for address,name in re.findall(r'^([0-9a-f]+) <([^>]+)>:',dis,re.M)}
    start=symbols['arithmetic_main'];end=min(v for v in functions.values() if v>start)
    bss,=[pc for pc,i in code.items() if pc<symbols['trap_entry'] and i==0x0002b023]
    init=[]
    for pc,i in sorted(code.items()):
        if not (start<=pc<end and i&127==35):continue
        base,source,f=(i>>15)&31,(i>>20)&31,(i>>12)&7
        offset=((i>>25)<<5)|((i>>7)&31);offset-=4096 if offset&2048 else 0
        if base==8 and ((source==18 and f==3 and 0<=offset<1024) or (source==15 and f==2 and offset==1024)):
            init.append(dict(pc=pc,insn=i,size=1<<f,offset=offset))
    p.old.require(len(init)==129 and sorted(row['offset'] for row in init)==list(range(0,1024,8))+[1024],
        'Actual sole128SD+SW lowering; no alternate compilation')
    p.old.require(sum(row['size'] for row in init)==1028,'Actual exact initialized bytes')
    profile[backend]=dict(elf_sha256=info['sha256'],initializer=init,bss_store=bss,
        business_start=start,business_end=end,total_store_bytes=1028,SD_count=128,SW_count=1)
p.save(HERE/'lowering.json',profile)

original=PARENT/'full_e8_m8_block_unrolled01/reference_check.py'
text=original.read_text();before=text
replacements=[
    ('from model import generate','from model import generate, words'),
    ("int(rd[2],16)==1024,'Capacity not1024'","int(rd[2],16)==512,'Capacity not512'"),
    ('out+1026','out+1028'),
    ("[a,b,out+1,row['vl'],1024,mask,row['start']]","[a,b,out+2,row['vl'],512,mask,row['start']]"),
    ("((a,seeds[row['seed']]['a']),(b,seeds[row['seed']]['b']),\n                        (out,[91]*1026),(mask,list(masks[row['mode']])))",
     "((a,list(words(seeds[row['seed']]['a'])+bytes(1024))),(b,list(words(seeds[row['seed']]['b'])+bytes(1024))),\n                        (out,list(words([91]*514))),(mask,list(masks[row['mode']])))"),
    ('fresh==set(range(1026))','fresh==set(range(1028))'),
    ("for ix in row['indices'])[:1026]","for ix in row['indices'])[:1028]"),
    ("row['vl'] if j==5 else 1024","row['vl'] if j==5 else 512"),
    ("(row['vl'],3,row['start'])","(row['vl'],11,row['start'])"),
    ("bytes(seeds[row['seed']]['a'])","words(seeds[row['seed']]['a'])"),
    ("bytes(seeds[row['seed']]['b'])","words(seeds[row['seed']]['b'])"),
    ('bytes([91]*1024)','words([91]*512)'),
    ('((1<<1024)-1)','((1<<512)-1)'),
    ("masks[row['mode']][:128]","masks[row['mode']][:64]"),
    ('expected[1:1025]','expected[2:1026]'),
    ("csrs.get('vl')==1024","csrs.get('vl')==512"),
    ('rwidth==(2 if offset==1024 else 8)','rwidth==(4 if offset==1024 else 8)'),
    ('sew=8 vlmax=1024','sew=16 vlmax=512'),
    ('elements=4193280','elements=2096640'),
    ('results=4193280','results=2096640'),
    ('per_call_fresh_output_bytes=1026','per_call_fresh_output_bytes=1028'),
    ('tail2','tail4'),('exact1026','exact1028')]
counts=[]
for old,new in replacements:
    count=text.count(old);p.old.require(count>0,'Explicit reference adaptation anchor missing '+old)
    text=text.replace(old,new);counts.append(dict(before=old,after=new,count=count))
text=text.replace('derived from mature dictionary observer','typed16 successor of mature fullraw observer')
ast.parse(text);p.emit(HERE/'reference_check.py',text)
p.emit(HERE/'reference_delta.diff',''.join(difflib.unified_diff(before.splitlines(True),text.splitlines(True),fromfile='sealed_e8_m8',tofile='explicit_e16_m8')))
p.save(HERE/'reference_adaptation.json',dict(parent=str(original),parent_sha256=p.sha(original),replacements=counts,
    group_regs=8,CAP=512,SEW=16,physical_input_bytes=2048,physical_output_bytes=2052,checked_bytes=1028,vtype=11,tail_bytes=4))
print('ACTUAL_ELF129_STORES_AND_TYPED16_REFERENCE_ADAPTER_READY')
