#!/usr/bin/env python3
"""Single fullraw reference parser, e8 byte-width successor of mature fullraw observer."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import resource
import subprocess
import time
from context import *
generate,words=original.generate,bytes
from lifecycle import Lifecycle
from gates import Capacity,Comparator
HERE=Path(__file__).resolve().parent
LAST_CONTEXT={}

def width(code,write):
    if code&3!=3:
        quadrant,kind=code&3,(code>>13)&7
        if quadrant in (0,2) and kind in ((6,7) if write else (2,3)):
            return 4 if kind in (2,6) else 8
        return None
    if code&127==(35 if write else 3):return 1<<(((code>>12)&7)&3)
    return None

def require(ok,why):
    if not ok:raise ValueError(why)

def parse_record(line):
    match=re.match(r'core\s+0:\s+\d\s+(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\)(.*)',line)
    require(match is not None or not line.strip(),'Nonempty malformed commit record')
    return match

def audit(raw):
    global LAST_CONTEXT
    seeds,rows,dictionary,masks=generate()
    symbols,code,helpers,machine=artifacts();lookup={i['pc']:(op,j,i['insn']) for op in range(25)
        for j,i in enumerate(helpers[f'op_{op}'])}
    code={int(m[1],16):int(m[2],16) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',
        (SOFT/'spike/program.dis').read_text(),re.M)}
    regex=re.compile(r'core\s+0:\s+\d\s+(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\)(.*)')
    rd_regex=re.compile(r'\bx\s*(\d+)\s+(0x[0-9a-f]+)')
    mem_regex=re.compile(r'\bmem\s+(0x[0-9a-f]+)(?:\s+(0x[0-9a-f]+))?')
    vec_regex=re.compile(r'\bv\s*(\d+)\s+0x([0-9a-f]+)')
    csr_regex=re.compile(r'\bc\d+_(vstart|vl|vtype)\s+0x([0-9a-f]+)')
    regs={0:0};vectors={};csrs={};fresh=set();reads=set();terminal=None;park_rows=0
    ordinal=0;step=0;counts=[0]*13;retired=0;boot=0;capacity=0;row=None
    exit_entry=None;read_count=0;context=None
    a,b,out,mask=(symbols[n] for n in ('a','b','out','mask'))
    expected=None
    capgate=Capacity(helpers);cmpgate=Comparator(machine)
    load_counts={'actual_output':0,'gold':0,'IDs':0,'other_comparator':0}
    expected_cmp=read(SOFT/'LINKED_COST.json')['compiled']['spike']
    lifecycle=Lifecycle(symbols,code,[helpers[f'op_{i}'][0]['pc'] for i in range(25)])
    memory=lifecycle.memory;rom=initial_reader(ELF.read_bytes());profile=lifecycle.profile
    def group(first):
        require(all(n in vectors for n in range(first,first+8)),'Missing physical vector group')
        return b''.join(vectors[n].to_bytes(128,'little') for n in range(first,first+8))
    def finish_call():
        if row is not None:require(step==0 and reads==set(range(129)),f'call{ordinal}: incomplete13/full129 oracle reads')
    with raw.open() as stream:
        for lineno,line in enumerate(stream,1):
            require('trap_' not in line,f'Unexpected reference trap line{lineno}')
            match=parse_record(line)
            if not match:continue
            pc,insn,rest=int(match[1],16),int(match[2],16),match[3]
            if pc<0x80000000:
                require(terminal is None,'No late return to boot ROM')
                boot+=1;continue
            retired+=1
            LAST_CONTEXT=dict(line=lineno,retired=retired,call=ordinal,pc=f'{pc:08x}',insn=f'{insn:08x}')
            require(retired+boot<=4000000,'Hard reference instruction bound')
            require(code.get(pc)==insn,f'PC/code mismatch pc{pc:x}')
            if terminal is not None:
                park_gate(pc,insn,rest,profile)
                park_rows+=1;continue
            lifecycle.enter(pc)
            rd=rd_regex.search(rest);mem=mem_regex.findall(rest)
            context=dict(line=lineno,retired=retired,call=ordinal,pc=f'{pc:08x}',insn=f'{insn:08x}')
            if pc==symbols['replay_exit']:
                require(regs.get(10)==0,'Original software return nonzero');exit_entry=retired-1
            changes={name:int(v,16) for name,v in csr_regex.findall(rest)}
            capgate.observe(pc,insn,retired,regs,csrs,(int(rd[1]),int(rd[2],16)) if rd else None,changes,rest)
            cmpgate.observe(pc,insn,regs,ordinal)
            w=width(insn,True)
            if w:
                require(len(mem)==1 and mem[0][1],'Scalar store log schema')
                address,value=int(mem[0][0],16),int(mem[0][1],16)
                lifecycle.source_store(pc,insn,address,w,value,regs)
                if lifecycle.entered and out<=address<out+1026:
                    require(address+w<=out+1026,'Output setup writes beyond exact1026')
                    fresh.update(range(address-out,address-out+w))
            h=lookup.get(pc)
            if h is not None:
                op,j,want_insn=h
                require(j==step and insn==want_insn,'Original helper PC/order/machine code')
                if j==0:
                    finish_call();require(ordinal<4095,'Extra helper call')
                    row=rows[ordinal];ordinal+=1;reads=set()
                    require(op==row['op'],'Original helper order')
                    require([regs.get(n) for n in range(10,17)]==[a,b,out+1,row['vl'],1024,mask,row['start']],
                        'Actual helper arguments/source context')
                    for base,want in ((a,list(words(seeds[row['seed']]['a']))),(b,list(words(seeds[row['seed']]['b']))),
                        (out,list(words([91]*1026))),(mask,list(masks[row['mode']]))):
                        require([memory.get(base+k) for k in range(len(want))]==want,'Actual initialized bytes '+str(base))
                    require(fresh==set(range(1026)),'Every call fresh exact1026 setup');fresh=set()
                    expected=b''.join(dictionary[ix].to_bytes(64,'little') for ix in row['indices'])[:1026]
                else:require(row and op==row['op'],'Cross-helper replay')
                if j in (0,5,10):
                    require(rd and int(rd[1])==5 and int(rd[2],16)==(row['vl'] if j==5 else 1024),'vsetvl result')
                if j==8:
                    require((csrs.get('vl'),csrs.get('vtype'),csrs.get('vstart'))==(row['vl'],3,row['start']),
                        'Target CSR context')
                    require(group(8)==words(seeds[row['seed']]['a']) and group(16)==words(seeds[row['seed']]['b']) and
                        group(24)==words([91]*1024),'Actual physical inputs/old vd')
                    require(0 in vectors and vectors[0]==int.from_bytes(masks[row['mode']],'little'),
                        'Actual predicate used')
                    require(regs.get(28)==7,'Original immediate scalar t3')
                if j==9:require(rd and int(rd[1])==10 and int(rd[2],16)==0,'Returned vstart')
                if j==11:
                    require(group(24)==expected[1:1025] and csrs.get('vl')==1024,'Complete stored vector output')
                    actual=group(24)
                    for offset,value in enumerate(actual):memory[out+1+offset]=value
                counts[j]+=1;step=(step+1)%13
            for n,v in vec_regex.findall(rest):vectors[int(n)]=int(v,16)
            for name,v in csr_regex.findall(rest):csrs[name]=int(v,16)
            if h and h[1]==8:
                require(group(24)==expected[1:1025] and csrs.get('vstart')==0,'Target full bitwise output/reset')
            rwidth=width(insn,False)
            if rwidth and mem:
                require(len(mem)==1 and not mem[0][1],'Scalar read log schema')
                address=int(mem[0][0],16)
                desc=memory_op(insn)
                require(desc and desc['kind']=='read' and desc['base'] in regs and address==(regs[desc['base']]+desc['offset'])&MASK64,'Actual scalar read source address')
                require(rd and int(rd[1])==desc['register'],'Actual scalar read destination')
                actual_bytes=[memory[address+i] if address+i in memory else rom(address+i) for i in range(rwidth)]
                bits=int.from_bytes(bytes(actual_bytes),'little')
                if desc['signed'] and bits>>(8*rwidth-1):bits-=1<<(8*rwidth)
                require(int(rd[2],16)==bits&MASK64,'Actual shared shadow/ROM scalar loaded bits')
                if pc in cmpgate.code:
                    bank='actual_output' if out<=address<out+1026 else 'gold' if symbols['expected_dictionary']<=address<symbols['expected_dictionary']+3768*64 else 'IDs' if symbols['expected_indices']<=address<symbols['expected_indices']+4095*34 else 'other_comparator'
                    load_counts[bank]+=1
                if out<=address<out+1026:
                    require(row is not None and step==0 and rd,'Output read outside scalar oracle')
                    offset=address-out;chunk=offset//8
                    require(offset%8==0 and rwidth==(2 if offset==1024 else 8) and chunk not in reads,
                        'Oracle exact aligned128+tail2 reads')
                    require(int(rd[2],16)==int.from_bytes(expected[offset:offset+rwidth],'little'),
                        f'call{ordinal} full bitwise output/guard mismatch offset{offset} line{lineno}')
                    reads.add(chunk);read_count+=1
            if rd:
                n=int(rd[1]);regs[n]=int(rd[2],16) if n else 0
            if w and mem and int(mem[0][0],16)==symbols['tohost']:
                require(int(mem[0][1],16)==1 and exit_entry is not None,'Actual HTIF not success1')
                require(lifecycle.calls==4095 and lifecycle.stores==0,'Full setup lifecycle')
                finish_call();require(ordinal==4095 and counts==[4095]*13,'Incomplete full4095/helper coverage')
                lifecycle.finish();capgate.finish();cmpgate.finish(expected_cmp['comparator_PC_visits'])
                require(load_counts=={'actual_output':528255,'gold':109575,'IDs':69615,'other_comparator':0},'Actual complete comparator loads incl constant/IDs/gold')
                logbytes=[]
                for k in range(8192):
                    value=lifecycle.value(symbols['replay_log']+k,1)
                    if value==0:break
                    logbytes.append(value)
                console=bytes(logbytes).decode('ascii')
                marker='RVV_MATRIX_PASS sew=8 vlmax=1024 cases=4095 elements=4193280 errors=0 seeds=3 guard_tail_mask_vstart=checked'
                console_gate(console)
                terminal=dict(status='ACCEPTED_FULL4095_SPIKE_SOURCE_ONLY_NOT_DUT',calls=ordinal,results=4193280,
                    guards=8190,vstart_zero=4095,helper_instruction_counts=counts,helper_instructions=sum(counts),
                    packed_output_reads=read_count,per_call_fresh_output_bytes=1026,physical_mask_bytes=128,
                    firmware_to_exit=exit_entry,firmware_to_HTIF=retired,boot=boot,console=console,closed_raw_parses=1,
                    capacity_instruction_counts=capgate.counts,capacity_instructions=3,actual_comparator_loads=load_counts,
                    actual_comparator_instruction_visits=sum(cmpgate.visits.values()),
                    actual_comparator_PC_counts_match_linked_success_path=True,final_context=context)
    require(terminal is not None,'Reference EOF without fullsource exit: '+repr(context))
    require(park_rows>0,'Actual EOF purepark observed')
    terminal.update(EOF_checked=True,EOFPARK_rows=park_rows,full_raw_retired=retired,shared_shadow=True,
        original_RNG_stores=lifecycle.seed_cursor,mask_groups=1575,mask_stores=25200,actual_new_ELF_sha256=ELF_SHA,
        source_helper_memory_owners=20475,backend_DUT_owners_claimed=False)
    return terminal
