#!/usr/bin/env python3
"""Independent whole-state and exact fault/retry oracle for the new pair."""
import json
from pathlib import Path
import re
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import sv39_adapter as base
require = base.require
GUARD = 0xe370697c
DONE = 0x6d647261696e0001
MASK = 0x8000031888
CHECKS = 914
SITES = dict(mt_recovery_load=0x0003f407,mt_successor_add=0x0080b457,
             mt_recovery_store=0x0003f427,mt_younger_store=0x0062b023,
             mt_repair_store=0x006e3023,mt_repair_sfence=0x120e0073,
             mt_retry_mret=0x30200073,mt_trap_vstart_read=0x00802373)


def data(p,i):
    return 0xa136570000000000 ^ (p<<48) ^ (i*37+11)


def seed(r,w):
    return 0x5b5b5b5b if 1<=r<=4 else 0x6c700000 ^ (r<<16) ^ w


def value(store,r,e,stage='final'):
    v=seed(r,2*e)|(seed(r,2*e+1)<<32)
    if not store and r==1 and e<9: v=data(1,0)
    if r==6 and e<9:
        if e%2==0: v=data(0,e)
        elif stage=='final': v+=1
    return v


def word(store,r,w):
    return (value(store,r,w//2)>>(32*(w%2)))&0xffffffff


def memword(store,p,i,phase):
    if phase=='final':
        if store and p==1 and i<9: return seed(1,2*i)|(seed(1,2*i+1)<<32)
        if p==0 and 16<=i<25 and i%2: return value(store,6,i-16)
    return data(p,i)


def mask(m,b):
    return (255,85,170)[m] if b==0 else int(b==1 and m!=2)


def host_check(text,store):
    gold=[f'R {r} {w} {seed(r,w):08x} {word(store,r,w):08x}' for r in range(7) for w in range(32)]
    gold += [f'D {p} {i} {data(p,i):016x} {memword(store,p,i,"final"):016x}' for p in range(2) for i in range(512)]
    gold += [f'M {m} {b} {mask(m,b):02x}' for m in range(3) for b in range(16)]
    require(text.splitlines()==gold,'Host C and independent Python oracle differ')
    return len(gold)


def expected(s,store,phase):
    out={}
    final=phase=='final'
    def add(a,v,n=8):
        for i,b in enumerate(v.to_bytes(n,'little')):
            require(a+i not in out,'Oracle overlap')
            out[a+i]=b
    pages=s['mt_pages']; repair=((pages+4096)>>12<<10)|0xc7
    satp=(8<<60)|((pages+8192)>>12)
    require(pages%4096==0 and s['mt_guard_lo']+64==pages and s['mt_guard_hi']==pages+20480,'Page layout')
    for p in range(2):
        for i in range(512): add(pages+p*4096+i*8,memword(store,p,i,phase))
    ptes={1025:((pages+12288)>>12<<10)|1,1026:0x200000cf,
          1536:((pages+16384)>>12<<10)|1,2048:(pages>>12<<10)|0xc7,
          2049:repair if final else 0}
    for i in range(1024,2560): add(pages+i*8,ptes.get(i,0))
    for name in ('mt_guard_lo','mt_guard_hi'):
        for i in range(16): add(s[name]+4*i,GUARD,4)
    for name in ('mt_seed','mt_fault','mt_result'):
        for off in (0,960):
            for w in range(16): add(s[name]+off+4*w,GUARD,4)
        for r in range(7):
            for w in range(32):
                v=word(store,r,w) if name=='mt_result' and final else GUARD if name=='mt_result' else seed(r,w)
                add(s[name]+64+r*128+w*4,v,4)
    for m in range(3):
        for b in range(16): add(s['mt_mask']+16*m+b,mask(m,b),1)
    for n in range(2):
        vals=[9 if n else 15 if store else 13,s['mt_ecall'] if n else s['mt_target'],
              0 if n else 0x40001000,None,satp,9,26,0,117,5,n,repair if n else 0]
        for j,v in enumerate(vals):
            if n and not final: v=(1<<64)-1
            if v is not None: add(s['mt_records']+96*n+8*j,v)
    for name in ('mt_post','mt_load_post','mt_after','mt_store_post'):
        for i,v in enumerate((9,26 if name=='mt_post' else 24,0,117,5)):
            add(s[name]+i*8,v if final else (1<<64)-1)
    for name,v,width in [('mt_trap_count',2 if final else 1,8),('mt_marker',int(final),8),
                         ('mt_repair_pte',repair,8),('mt_expected_satp',satp,8),
                         ('mt_unexpected',0,8),('mt_completed',DONE if final else 0,8),
                         ('mt_errors',0,4),('mt_checks',CHECKS if final else 3,4)]:
        add(s[name],v,width)
    return out


def compare(memory,s,store,phase):
    want=expected(s,store,phase)
    bad=[(hex(a),v,memory.get(a)) for a,v in want.items() if memory.get(a)!=v]
    require(not bad,'Whole memory '+phase+' mismatch: '+repr(bad[:8]))
    for n in range(2 if phase=='final' else 1):
        a=s['mt_records']+96*n+24
        require(all(a+i in memory for i in range(8)),'Missing trap mstatus')
        v=int.from_bytes(bytes(memory[a+i] for i in range(8)),'little')
        require(v&MASK==0x800,'Trap privilege/status differs')
    return len(want)


def negatives(s,store):
    tests=[]
    for phase in ('fault','final'):
        mem=expected(s,store,phase)
        for n in range(2 if phase=='final' else 1):
            for i,b in enumerate((0x800).to_bytes(8,'little')): mem[s['mt_records']+96*n+24+i]=b
        compare(mem,s,store,phase)
        for name,a in [('target_tail',s['mt_result']+64+128+127),
                       ('old_snapshot',s['mt_fault']+64+256),('guard',s['mt_result']),
                       ('page',s['mt_pages']+4096+2048),('pte',s['mt_pages']+16392),
                       ('vstart',s['mt_records']+56),('predicate',s['mt_mask']+16)]:
            bad=mem.copy();bad[a]^=1
            try: compare(bad,s,store,phase)
            except ValueError: tests.append(phase+':'+name);continue
            raise ValueError('Negative oracle accepted '+name)
    return tests


def validate(path,s,store):
    memory={};regs={0:0};actions=[];traps=[];htif=[];commits=0;partials=0;awaiting=False
    sites=dict(SITES,mt_target=0x00057c27 if store else 0x08757c07)
    bypc={s[n]:n for n in sites}; target_events=[];fault_bytes=None
    with Path(path).open() as f:
        for line in f:
            trap=re.search(r'exception\s+(\w+), epc 0x([0-9a-f]+)',line)
            if trap:traps.append((trap[1],int(trap[2],16)))
            m=re.match(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$',line)
            if not m:continue
            mode,pc,insn,tail=int(m[1]),int(m[2],16),int(m[3],16),m[4];commits+=1
            require(pc not in (s['trap_entry'],s['replay_mismatch']),'Default trap or firsterror executed')
            access=[(int(a,16),int(v,16) if v else None) for a,v in re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?',tail)]
            gprs={int(r):int(v,16) for r,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)}
            name=bypc.get(pc)
            if name:
                require(insn==sites[name],'Actual instruction differs: '+name)
                require(mode==(3 if name.startswith('mt_repair') or name in ('mt_retry_mret','mt_trap_vstart_read') else 1),'Wrong privilege: '+name)
            if name=='mt_target' and not target_events:
                require(not access and re.fullmatch(r'\s+e64 m4 l9 c8_vstart 0x0+\s*',tail),'Fault-attempt side effects or state differ')
                partials+=1;awaiting=True;actions.append('fault_partial');target_events.append(access);continue
            if awaiting and insn&127==0x73 and insn>>20==0x341:
                require((insn>>12)&7 in (2,3,6,7) and (insn>>15)&31==0,'MEPC changed before same-PC retry')
            if name:
                actions.append(name)
                if name=='mt_trap_vstart_read':require(gprs.get(6)==0,'Actual trap vstart read did not return zero')
                elif name=='mt_target':
                    gold=[(0x40001000+8*i,value(1,1,i)) for i in range(9)] if store else [(0x40001000,None)]*9
                    require(access==gold,'Target retry accesses differ');target_events.append(access)
                    require('e64 m4 l9' in tail,'Target vtype/VL')
                    if not store:
                        writes=re.findall(r'\bv24\s+0x([0-9a-f]+)',tail)
                        want=sum(value(store,1,i)<<(64*i) for i in range(16))
                        require(len(writes)==1 and int(writes[0],16)==want,'Full target register/tail differs')
                elif name=='mt_recovery_load':
                    require(access==[(0x40000000+8*i,None) for i in range(0,9,2)],'Successor load predicate/address')
                    writes=re.findall(r'\bv8\s+0x([0-9a-f]+)',tail)
                    want=sum(value(store,6,i,'load')<<(64*i) for i in range(16))
                    require(len(writes)==1 and int(writes[0],16)==want,'Whole successor load register differs')
                elif name=='mt_successor_add':
                    writes=re.findall(r'\bv8\s+0x([0-9a-f]+)',tail)
                    want=sum(value(store,6,i)<<(64*i) for i in range(16))
                    require(not access and len(writes)==1 and int(writes[0],16)==want,'Complementary mask add differs')
                elif name=='mt_recovery_store':
                    require(access==[(0x40000080+8*i,value(store,6,i)) for i in range(1,9,2)],'Successor store residue/predicate')
                elif name=='mt_repair_store':
                    fault_bytes=compare(memory,s,store,'fault')
                    require(access==[(s['mt_pages']+16392,((s['mt_pages']+4096)>>12<<10)|0xc7)],'PTE repair address/value')
                elif name=='mt_repair_sfence':require(regs.get(28)==0x40001000,'Addressed SFENCE differs')
                elif name=='mt_retry_mret':require(awaiting,'Unpaired MRET');awaiting=False
            for a,v in access:
                if v is None:continue
                if insn&3!=3:
                    d=base.compressed_memory(insn)
                    require(d and d['kind']=='write','Unknown compressed store')
                    width=d['size'];require(a==(regs.get(d['base'],-1)+d['offset'])&((1<<64)-1),'Compressed address')
                else:
                    require(insn&127 in (0x23,0x27),'Unknown store')
                    width=(1<<((insn>>12)&7)) if insn&127==0x23 else {0:1,5:2,6:4,7:8}[(insn>>12)&7]
                physical=s['mt_pages']+a-0x40000000 if 0x40000000<=a<0x40002000 else a
                for i,b in enumerate((v&((1<<(8*width))-1)).to_bytes(width,'little')):memory[physical+i]=b
                if a==s['tohost']:htif.append(v)
            regs.update(gprs)
    require(traps==[('trap_store_page_fault' if store else 'trap_load_page_fault',s['mt_target']),('trap_supervisor_ecall',s['mt_ecall'])],'Exact trap ledger differs '+repr(traps))
    gold=['fault_partial','mt_trap_vstart_read','mt_repair_store','mt_repair_sfence','mt_retry_mret',
          'mt_target','mt_recovery_load','mt_successor_add','mt_recovery_store','mt_younger_store','mt_trap_vstart_read']
    require(actions==gold and not awaiting and partials==1 and len(target_events)==2,'Exact phase/retry order differs '+repr(actions))
    require(htif==[1] and commits<500000,'Missing/nonzero HTIF or exceeded instruction bound')
    final_bytes=compare(memory,s,store,'final')
    marker=bytes(memory.get(s['replay_log']+i,0) for i in range(len('MASK_DRAIN_SV39_PASS\n')))
    require(marker==b'MASK_DRAIN_SV39_PASS\n','Actual runtime success marker missing')
    return dict(status='HOST_SPIKE_PASS_NOT_DUT',store=store,raw_commit_records=commits,
                retired_nonpartial=commits-partials,checks=CHECKS,actions=actions,traps=traps,
                fault_checkpoint_bytes=fault_bytes,final_checkpoint_bytes=final_bytes,
                htif=htif,target_attempts=len(target_events),full_target_bytes=512,
                full_neighbor_bytes=256,full_successor_bytes=128,csr_restore_checked=True)
