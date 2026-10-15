#!/usr/bin/env python3
"""Single fullraw reference parser, derived from mature dictionary observer."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import resource
import subprocess
import time
import prepare as p
from model import generate
from lifecycle import Lifecycle, full_group, scalar_width
from raw_boundary import RawBoundary
HERE=Path(__file__).resolve().parent

width=scalar_width

def require(ok,why):
    if not ok:raise ValueError(why)

def audit(raw):
    seeds,rows,masks=generate()
    symbols=json.loads((HERE/'spike/symbols.json').read_text())
    proof=json.loads((HERE/'proof.json').read_text())['backends']['spike']
    helpers=proof['helpers'];lookup={i['pc']:(op,j,i['insn']) for op in range(25)
        for j,i in enumerate(helpers[f'op_{op}'])}
    code={int(m[1],16):int(m[2],16) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',
        (HERE/'spike/program.dis').read_text(),re.M)}
    regex=re.compile(r'core\s+0:\s+\d\s+(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\)(.*)')
    rd_regex=re.compile(r'\bx\s*(\d+)\s+(0x[0-9a-f]+)')
    mem_regex=re.compile(r'\bmem\s+(0x[0-9a-f]+)(?:\s+(0x[0-9a-f]+))?')
    vec_regex=re.compile(r'\bv\s*(\d+)\s+0x([0-9a-f]+)')
    csr_regex=re.compile(r'\bc\d+_(vstart|vl|vtype)\s+0x([0-9a-f]+)')
    regs={0:0};memory={};vectors={};csrs={};fresh=set();reads=set()
    ordinal=0;step=0;counts=[0]*13;retired=0;boot=0;capacity=0;row=None
    capacity_counts=[0,0,0];capacity_lookup={x['pc']:i for i,x in enumerate(helpers['capacity'])}
    exit_entry=None;read_count=0;context=None
    a,b,out,mask=(symbols[n] for n in ('a','b','out','mask'))
    expected=None;report=None;boundary=RawBoundary()
    lifecycle=Lifecycle(symbols,code,[helpers[f'op_{i}'][0]['pc'] for i in range(25)],rows,masks)
    def group(first):return full_group(vectors,first)
    def finish_call():
        if row is not None:require(step==0 and reads==set(range(17)),f'call{ordinal}: incomplete13/full17 oracle reads')
    with raw.open() as stream:
        for lineno,line in enumerate(stream,1):
            require('trap_' not in line,f'Unexpected reference trap line{lineno}')
            match=regex.match(line)
            if not match:
                require(not line.strip(),f'Unparsed raw line{lineno}')
                continue
            pc,insn,rest=int(match[1],16),int(match[2],16),match[3]
            state=boundary.enter(pc,insn,rest)
            if state=='boot':
                boot+=1
                require(retired+boot+boundary.park<=4000000,'Hard whole raw instruction bound')
                continue
            if state=='park':
                require(retired+boot+boundary.park<=4000000,'Hard whole raw instruction bound')
                continue
            retired+=1
            require(retired+boot<=4000000,'Hard reference instruction bound')
            require(code.get(pc)==insn,f'PC/code mismatch pc{pc:x}')
            lifecycle.enter(pc)
            rd=rd_regex.search(rest);mem=mem_regex.findall(rest)
            context=dict(line=lineno,retired=retired,call=ordinal,pc=f'{pc:08x}',insn=f'{insn:08x}')
            if pc==symbols['replay_exit']:
                require(regs.get(10)==0,'Original software return nonzero');exit_entry=retired-1
            if pc in capacity_lookup:
                capacity_counts[capacity_lookup[pc]]+=1
            if pc==helpers['capacity'][1]['pc']:
                require(rd and int(rd[2],16)==64,'Capacity not64');capacity+=1
            w=width(insn,True)
            if w:
                require(len(mem)==1 and mem[0][1],'Scalar store log schema')
                address,value=int(mem[0][0],16),int(mem[0][1],16)
                lifecycle.store(pc,insn,address,w,value)
                for j in range(w):memory[address+j]=(value>>(8*j))&255
                if lifecycle.entered and out<=address<out+132:
                    require(address+w<=out+132,'Output setup writes beyond exact132')
                    fresh.update(range(address-out,address-out+w))
            h=lookup.get(pc)
            require(step==0 or h is not None,'Interrupted original helper window')
            if h is not None:
                op,j,want_insn=h
                require(j==step and insn==want_insn,'Original helper PC/order/machine code')
                if j==0:
                    finish_call();require(ordinal<4095,'Extra helper call')
                    row=rows[ordinal];ordinal+=1;reads=set()
                    require(op==row['op'],'Original helper order')
                    require([regs.get(n) for n in range(10,17)]==[a,b,out+2,row['vl'],64,mask,row['start']],
                        'Actual helper arguments/source context')
                    for base,want in ((a,list(b''.join(x.to_bytes(2,'little') for x in seeds[row['seed']]['a']))),
                        (b,list(b''.join(x.to_bytes(2,'little') for x in seeds[row['seed']]['b']))),
                        (out,list(bytes([91,0])*66)),(mask,list(masks[row['mode']]))):
                        require([memory.get(base+k) for k in range(len(want))]==want,'Actual initialized bytes '+str(base))
                    require(all(memory.get(a+i)==memory.get(b+i)==0 for i in range(128,2048)) and
                        all(memory.get(out+i)==0 for i in range(132,2052)), 'Unused original physical arrays remain BSS zero')
                    require(fresh==set(range(132)),'Every call fresh exact132 setup');fresh=set()
                    expected=b''.join(word.to_bytes(8,'little') for word in row['words'])[:132]
                else:require(row and op==row['op'],'Cross-helper replay')
                if j in (0,5,10):
                    require(rd and int(rd[1])==5 and int(rd[2],16)==(row['vl'] if j==5 else 64),'vsetvl result')
                if j==8:
                    require((csrs.get('vl'),csrs.get('vtype'),csrs.get('vstart'))==(row['vl'],8,row['start']),
                        'Target CSR context')
                    require(group(8)==b''.join(x.to_bytes(2,'little') for x in seeds[row['seed']]['a']) and
                        group(16)==b''.join(x.to_bytes(2,'little') for x in seeds[row['seed']]['b']) and
                        group(24)==bytes([91,0])*64,'Actual physical inputs/old vd')
                    require(0 in vectors and (vectors[0]&((1<<64)-1))==int.from_bytes(masks[row['mode']][:8],'little'),
                        'Actual predicate used')
                    require(regs.get(28)==7,'Original immediate scalar t3')
                if j==9:require(rd and int(rd[1])==10 and int(rd[2],16)==0,'Returned vstart')
                if j==11:require(group(24)==expected[2:130] and csrs.get('vl')==64,'Complete stored vector output')
                counts[j]+=1;step=(step+1)%13
            for n,v in vec_regex.findall(rest):vectors[int(n)]=int(v,16)
            for name,v in csr_regex.findall(rest):csrs[name]=int(v,16)
            if h and h[1]==8:
                require(group(24)==expected[2:130] and csrs.get('vstart')==0,'Target full bitwise output/reset')
            rwidth=width(insn,False)
            if rwidth and mem:
                require(len(mem)==1 and not mem[0][1],'Scalar read log schema')
                address=int(mem[0][0],16)
                lifecycle.read(pc,address,rwidth)
                if out<=address<out+132:
                    require(row is not None and step==0 and rd,'Output read outside scalar oracle')
                    offset=address-out;chunk=offset//8
                    require(offset%8==0 and rwidth==(4 if offset==128 else 8) and chunk not in reads,
                        'Oracle exact aligned8+tail4 reads')
                    require(int(rd[2],16)==int.from_bytes(expected[offset:offset+rwidth],'little'),
                        f'call{ordinal} full bitwise output/guard mismatch offset{offset} line{lineno}')
                    reads.add(chunk);read_count+=1
            if rd:
                n=int(rd[1]);regs[n]=int(rd[2],16) if n else 0
            if w and mem and int(mem[0][0],16)==symbols['tohost']:
                require(int(mem[0][1],16)==1 and exit_entry is not None,'Actual HTIF not success1')
                lifecycle.finish()
                require(read_count==69615 and capacity_counts==[1,1,1],'Full actual output reads/capacity window')
                finish_call();require(ordinal==4095 and counts==[4095]*13 and capacity==1,'Incomplete full4095/helper coverage')
                console=bytes(memory.get(symbols['replay_log']+k,0) for k in range(8192)).split(b'\0',1)[0].decode('ascii')
                marker='RVV_MATRIX_PASS sew=16 vlmax=64 cases=4095 elements=262080 errors=0 seeds=3 guard_tail_mask_vstart=checked'
                require(console.splitlines()==[marker] and not re.search('FAIL|TRAP|UNSUPPORTED',console),'Raw full original console veto')
                boundary.success(pc,insn,int(mem[0][1],16))
                require(report is None,'Duplicate architectural completion')
                report=dict(status='ACCEPTED_FULL4095_SPIKE_SOURCE_ONLY_NOT_DUT',calls=ordinal,results=262080,
                    guards=8190,vstart_zero=4095,helper_instruction_counts=counts,helper_instructions=sum(counts),
                    packed_output_reads=read_count,per_call_fresh_output_bytes=132,physical_mask_bytes=128,
                    firmware_to_exit=exit_entry,firmware_to_HTIF=retired,boot=boot,
                    capacity_instruction_counts=capacity_counts,mask_groups=lifecycle.mask_groups,
                    original_input_scalar_writes=lifecycle.input_cursor,
                    physical_registers_per_group=1,observed_register_bytes=128,physical_register_bytes=128,vlm_read_bytes=8,source_SEW=16,source_LMUL='m1',source_CAP=64,vtype=8,typed_sentinel='005b',tail_read_bytes=4,console=console,closed_raw_parses=1,
                    final_context=context)
    require(report is not None,'Reference ended without architectural full4095 exit: '+repr(context))
    boundary.finish()
    require(retired+boot+boundary.park<=4000000,'Hard whole raw instruction bound')
    report.update(post_HTIF_park_rows=boundary.park,whole_raw_rows=retired+boot+boundary.park,EOF_checked=True)
    return report
