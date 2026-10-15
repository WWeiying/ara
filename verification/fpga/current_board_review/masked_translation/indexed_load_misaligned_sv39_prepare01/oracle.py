#!/usr/bin/env python3
"""Whole-memory independent oracle for indexed prefix alignment recovery."""
import re
from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import sv39_adapter as base
require=base.require
GUARD=0xe370697c
DONE=0x6d647261696e0001
POISON=0xbad0123456789abc
MASK=0x8000031888
CHECKS=962
SITES=dict(mt_target=0x0d057c07,mt_initial_vstart_write=0x00831073,mt_prefix_checkpoint=0x00000013,
           mt_prefix_poison=0x006e3023,mt_repair_index=0x020e7807,
           mt_restart_vstart_write=0x00831073,mt_retry_mret=0x30200073,
           mt_successor_indexed_store=0x0d43f427,mt_recovery_load=0x0003f407,
           mt_successor_add=0x0080b457,mt_younger_store=0x0062b023,
           mt_trap_vstart_read=0x00802373)


def data(p,i):return 0xa136570000000000^(p<<48)^(i*37+11)
def index(r,i,fixed=False):
    if i>=3:return 128+8*i
    return ((32,8,16 if fixed else 17) if r==0 else (24,0,16))[i]
def source(r,i):
    return index(r,i) if r in (0,4) else 0x6c70000012340000^(r<<48)^(i*37+19)
def seed(r,w):return (source(r,w//2)>>(32*(w%2)))&0xffffffff
def value(r,i,phase='final'):
    if r==0 and i==2:return 16
    if r==1 and i in (1,2,4):return data(0,20 if i==4 else i)
    if r==5 and i==0:return data(0,32)
    return source(r,i)+(1 if r==5 and i==1 and phase=='final' else 0)
def word(store,r,w):return (value(r,w//2)>>(32*(w%2)))&0xffffffff
def fault_defined(r,w):return not (r==1 and w//2 in (2,4))
def fault_word(r,w):return ((data(0,1) if r==1 and w//2==1 else source(r,w//2))>>(32*(w%2)))&0xffffffff
def memword(p,i,phase):
    if p==0:
        if i==1 and phase=='final':return POISON
        if phase=='final' and i in (34,35):return {34:source(5,2),35:source(5,0)}[i]
    return data(p,i)
def mask(m,b):return (23,5,2)[m] if b==0 else 0


def host_check(text,store):
    g=[f'R {r} {w} {seed(r,w):08x} {word(store,r,w):08x}' for r in range(7) for w in range(32)]
    g += [f'D {p} {i} {data(p,i):016x} {memword(p,i,"final"):016x}' for p in range(2) for i in range(512)]
    g += [f'M {m} {b} {mask(m,b):02x}' for m in range(3) for b in range(16)]
    g += [f'F {p} {i} {memword(p,i,"fault"):016x}' for p in range(2) for i in range(512)]
    g += [f'P {r} {w} {fault_word(r,w):08x} {int(fault_defined(r,w))}' for r in range(7) for w in range(32)]
    require(text.splitlines()==g,'Host oracle differs')
    return len(g)


def expected(s,store,phase):
    out={};final=phase=='final'
    def add(a,v,n=8):
        for i,b in enumerate(v.to_bytes(n,'little')):
            require(a+i not in out,'Oracle overlap');out[a+i]=b
    pages=s['mt_pages'];pte=((pages+4096)>>12<<10)|0xc7
    for p in range(2):
        for i in range(512):
            add(pages+p*4096+i*8,memword(p,i,phase))
            add(s['mt_prefix']+64+(p*512+i)*8,memword(p,i,'fault'))
    table={1025:((pages+12288)>>12<<10)|1,1026:0x200000cf,
           1536:((pages+16384)>>12<<10)|1,2048:(pages>>12<<10)|0xc7,2049:pte}
    for i in range(1024,2560):add(pages+i*8,table.get(i,0))
    for name,offsets in [('mt_guard_lo',[0]),('mt_guard_hi',[0]),('mt_prefix',[0,8256])]:
        for off in offsets:
            for i in range(16):add(s[name]+off+4*i,GUARD,4)
    for name in ('mt_seed','mt_fault','mt_result'):
        for off in (0,960):
            for i in range(16):add(s[name]+off+4*i,GUARD,4)
        for r in range(7):
            for w in range(32):
                if name=='mt_fault' and not fault_defined(r,w):continue
                add(s[name]+64+r*128+w*4,word(store,r,w) if name=='mt_result' and final else
                    GUARD if name=='mt_result' else fault_word(r,w) if name=='mt_fault' else seed(r,w),4)
    for i in range(16):add(s['mt_fix_index']+8*i,index(0,i,True))
    for i,v in enumerate((5,24,2)):add(s['mt_restart']+8*i,v if final else 0)
    for m in range(3):
        for b in range(16):add(s['mt_mask']+16*m+b,mask(m,b),1)
    for n in range(2):
        vals=[9 if n else 4,s['mt_ecall'] if n else s['mt_target'],0 if n else 0x40000011,
              None,(8<<60)|((pages+8192)>>12),5,24,0 if n else 2,117,5,n,pte]
        for j,v in enumerate(vals):
            if n and not final:v=(1<<64)-1
            if v is not None:add(s['mt_records']+96*n+8*j,v)
    for name in ('mt_post','mt_load_post','mt_after','mt_store_post'):
        for i,v in enumerate((5,24,0,117,5)):add(s[name]+8*i,v if final else (1<<64)-1)
    for name,v,n in [('mt_trap_count',2 if final else 1,8),('mt_marker',int(final),8),
                     ('mt_repair_pte',pte,8),('mt_expected_satp',(8<<60)|((pages+8192)>>12),8),
                     ('mt_unexpected',0,8),('mt_completed',DONE if final else 0,8),
                     ('mt_errors',0,4),('mt_checks',CHECKS if final else 3,4)]:add(s[name],v,n)
    return out


def compare(mem,s,store,phase):
    want=expected(s,store,phase)
    bad=[(hex(a),v,mem.get(a)) for a,v in want.items() if mem.get(a)!=v]
    require(not bad,'Full '+phase+' mismatch '+repr(bad[:8]))
    for n in range(2 if phase=='final' else 1):
        a=s['mt_records']+96*n+24
        require(all(a+i in mem for i in range(8)),'Missing status')
        require(int.from_bytes(bytes(mem[a+i] for i in range(8)),'little')&MASK==0x800,'Trap privilege')
    return len(want)


def negatives(s,store):
    results=[]
    for phase in ('fault','final'):
        mem=expected(s,store,phase)
        for n in range(2 if phase=='final' else 1):
            for i,b in enumerate((0x800).to_bytes(8,'little')):mem[s['mt_records']+96*n+24+i]=b
        compare(mem,s,store,phase)
        for name,a in [('prefix',s['mt_pages']+8),('faultbyte',s['mt_pages']+17),
                       ('skip',s['mt_pages']+32),('snapshot',s['mt_prefix']+64+8),
                       ('tail',s['mt_result']+64+127),('vstart',s['mt_records']+56),
                       ('cause',s['mt_records']),('indexfix',s['mt_fix_index']+16),
                       ('destprefix',s['mt_fault']+64+128+8),('prestart',s['mt_fault']+64+128),
                       ('inactive',s['mt_fault']+64+128+24),('desttail',s['mt_fault']+64+128+40),
                       ('guard',s['mt_prefix']),('pte',s['mt_pages']+16384)]:
            bad=mem.copy();bad[a]^=1
            try:compare(bad,s,store,phase)
            except ValueError:results.append(phase+':'+name);continue
            raise ValueError('Negative accepted '+name)
        for elem in (2,4):
            permissive=mem.copy()
            for byte in range(8):permissive[s['mt_fault']+64+128+elem*8+byte]=0xa5^byte
            compare(permissive,s,store,phase)
            results.append(phase+':allows_undefined_fault_active_'+str(elem))
        if phase=='final':
            for elem in (2,4):
                bad=mem.copy();bad[s['mt_result']+64+128+elem*8]^=1
                try:compare(bad,s,store,phase)
                except ValueError:results.append('final:reject_retry_active_'+str(elem));continue
                raise ValueError('Final active result corruption accepted')
    return results


def validate(path,s,store):
    mem={};regs={0:0};actions=[];traps=[];htif=[];commits=0;attempts=0;awaiting=False;fault_bytes=None
    bypc={s[n]:n for n in SITES}
    with Path(path).open() as f:
        for line in f:
            t=re.search(r'exception\s+(\w+), epc 0x([0-9a-f]+)',line)
            if t:traps.append((t[1],int(t[2],16)))
            m=re.match(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$',line)
            if not m:continue
            mode,pc,insn,tail=int(m[1]),int(m[2],16),int(m[3],16),m[4];commits+=1
            require(pc not in (s['trap_entry'],s['replay_mismatch'],s['mt_bad_trap']),'First-error/default trap')
            accesses=[(int(a,16),int(v,16) if v else None) for a,v in re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?',tail)]
            gprs={int(r):int(v,16) for r,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)}
            name=bypc.get(pc)
            if awaiting and insn&127==0x73 and insn>>20==0x341:
                require((insn>>12)&7 in (2,3,6,7) and (insn>>15)&31==0,'MEPC changed on retry')
            if name:
                require(insn==SITES[name],'Site opcode '+name)
                machine=name.startswith(('mt_prefix','mt_repair','mt_restart','mt_retry','mt_trap'))
                require(mode==(3 if machine else 1),'Wrong mode '+name)
                if name=='mt_target':
                    attempts+=1
                    gold=[(0x40000008,None)] if attempts==1 else [(0x40000010,None),(0x400000a0,None)]
                    require(accesses==gold and 'e64 m1 l5' in tail,'Exact target prefix/retry access')
                    if attempts==1:
                        require('c8_vstart 0x0000000000000002' in tail,'Fault vstart2 missing')
                        awaiting=True;actions.append('fault_partial')
                    else:require(attempts==2 and not awaiting,'Retry count');actions.append(name)
                else:actions.append(name)
                if name=='mt_initial_vstart_write':require(regs.get(6)==1,'Initial vstart1 required')
                elif name=='mt_trap_vstart_read':require(gprs.get(6)==(2 if len(traps)==1 else 0),'Actual vstart read')
                elif name=='mt_prefix_checkpoint':fault_bytes=compare(mem,s,store,'fault')
                elif name=='mt_prefix_poison':require(accesses==[(s['mt_pages']+8,POISON)],'Wrong poison')
                elif name=='mt_repair_index':
                    require(accesses==[(s['mt_fix_index']+8*i,None) for i in range(16)],'Index reload accesses')
                    w=re.findall(r'\bv16\s+0x([0-9a-f]+)',tail)
                    require(len(w)==1 and int(w[0],16)==sum(index(0,i,True)<<(64*i) for i in range(16)),'Full index repair')
                elif name=='mt_restart_vstart_write':require(regs.get(6)==2,'Saved vstart not restored')
                elif name=='mt_retry_mret':require(awaiting,'Unpaired retry');awaiting=False
                elif name=='mt_successor_indexed_store':require(accesses==[(0x40000118,source(5,0)),(0x40000110,source(5,2))],'Successor indexed operands')
                elif name in ('mt_recovery_load','mt_successor_add'):
                    require(accesses==([(0x40000100,None),(0x40000110,None)] if name=='mt_recovery_load' else []),'Successor mask addresses')
                    w=re.findall(r'\bv8\s+0x([0-9a-f]+)',tail)
                    require(len(w)==1 and int(w[0],16)==sum(value(5,i,'load' if name=='mt_recovery_load' else 'final')<<(64*i) for i in range(16)),'Successor whole register')
            for a,v in accesses:
                if v is None:continue
                if insn&3!=3:
                    d=base.compressed_memory(insn);require(d and d['kind']=='write','Compressed write');width=d['size']
                    require(a==(regs.get(d['base'],-1)+d['offset'])&((1<<64)-1),'Compressed write address')
                else:
                    require(insn&127 in (0x23,0x27),'Unknown store')
                    width=(1<<((insn>>12)&7)) if insn&127==0x23 else {0:1,5:2,6:4,7:8}[(insn>>12)&7]
                physical=s['mt_pages']+a-0x40000000 if 0x40000000<=a<0x40002000 else a
                for i,b in enumerate((v&((1<<(8*width))-1)).to_bytes(width,'little')):mem[physical+i]=b
                if a==s['tohost']:htif.append(v)
            regs.update(gprs)
    require(traps==[('trap_load_address_misaligned',s['mt_target']),('trap_supervisor_ecall',s['mt_ecall'])],'Exact cause4/ecall ledger '+repr(traps))
    require(actions==['mt_initial_vstart_write','fault_partial','mt_trap_vstart_read','mt_prefix_checkpoint','mt_prefix_poison','mt_repair_index',
                      'mt_restart_vstart_write','mt_retry_mret','mt_target','mt_successor_indexed_store',
                      'mt_recovery_load','mt_successor_add','mt_younger_store','mt_trap_vstart_read'],'Exact action sequence '+repr(actions))
    require(htif==[1] and not awaiting and attempts==2 and commits<500000,'Incomplete reference')
    final_bytes=compare(mem,s,store,'final')
    msg=b'INDEXED_LOAD_SV39_PASS\n'
    require(bytes(mem.get(s['replay_log']+i,0) for i in range(len(msg)))==msg,'Actual success marker')
    return dict(status='HOST_SPIKE_PASS_NOT_DUT',checks=CHECKS,raw_commit_records=commits,retired_nonpartial=commits-1,
                traps=traps,actions=actions,fault_checkpoint_bytes=fault_bytes,final_checkpoint_bytes=final_bytes,
                htif=htif,target_attempts=attempts,csr_restore_checked=True,prefix_poison=True)
