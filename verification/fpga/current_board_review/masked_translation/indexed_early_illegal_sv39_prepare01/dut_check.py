#!/usr/bin/env python3
"""One-pass scalar RVFI evidence; pinned on-device checks cover vector memory."""
import csv
import sys
sys.dont_write_bytecode = True
import oracle as ref
require = ref.require
FIELDS = 'cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap'.split(',')
CSR = {0x342:0,0x341:1,0x343:2,0x300:3,0x180:4,0xc20:5,0xc21:6,8:7,3:8,15:9}
RESTORE = [0x180,0x305,0x341,0x342,0x343,0x302,0x303,0x304,0xc20,0xc21,8,15,3,0x300]


def gold_checks(s,store):
    g=[128,0,0,0,2]
    for n in range(2):
        g += [9 if n else 6,s['mt_ecall'] if n else s['mt_target'],
              0 if n else 0x40000011,0x800,(8<<60)|((s['mt_pages']+8192)>>12),
              3,24,0 if n else 2,117,5,n,((s['mt_pages']+4096)>>12<<10)|0xc7]
    for i in range(5):
        g += [(3,24,0,117,5)[i]]*4
    g += [1]+[ref.mask(m,b) for m in range(3) for b in range(16)]
    for b in range(3):
        g += [ref.GUARD]*32
        g += [ref.word(store,r,w) if b==2 else ref.seed(r,w) for r in range(7) for w in range(32)]
    g += [3,24,2]+[ref.index(0,i,True) for i in range(16)]+[ref.GUARD]*32+[0]
    g += [0,0]+[ref.GUARD]*32
    require(len(g)==952,'Independent oracle call count')
    return g


def scalar_store(r,regs):
    insn,a,m,v=(int(r[k],16) for k in ('insn','mem_addr','mem_wmask','mem_wdata'))
    if not m: return None
    if insn&3!=3:
        d=ref.base.compressed_memory(insn)
        require(d is not None and d['kind']=='write','Compressed store encoding')
        width,source,addr=d['size'],d['register'],regs[d['base']]+d['offset']
    else:
        require(insn&127==0x23,'Unexpected nonscalar RVFI write')
        width,source=1<<((insn>>12)&7),(insn>>20)&31
        imm=((insn>>25)<<5)|((insn>>7)&31)
        if imm&2048: imm-=4096
        addr=regs[(insn>>15)&31]+imm
    require(width in (1,2,4,8) and a%8+width<=8 and a==addr&((1<<64)-1),'Store address/width')
    require(m==((1<<width)-1)<<(a%8),'Store byte enables')
    bits=(1<<(width*8))-1
    require(v&bits==regs[source]&bits,'Store source operand')
    return a,v&bits,width


class Checker:
    def __init__(self,s,store):
        self.s=s;self.store=store;self.gold=gold_checks(s,store)
        self.regs=[0]*32;self.mem={};self.saved={};self.traps=[];self.actions=[]
        self.calls=0;self.rows=0;self.order=-1;self.cycle=-1;self.exits=[]
        self.retry=False;self.capture=None;self.sites={s[k]:k for k in ref.SITES}
        self.sites[s['mt_target']]='mt_target'

    def u(self,name,n=8,index=0):
        a=self.s[name]+index*n
        require(all(a+i in self.mem for i in range(n)),'Missing scalar state '+name)
        return int.from_bytes(bytes(self.mem[a+i] for i in range(n)),'little')

    def row(self,r):
        require(set(r)==set(FIELDS) and None not in r.values(),'CSV schema/truncation')
        self.rows+=1;cycle=int(r['cycle']);require(cycle>=self.cycle,'Cycle order');self.cycle=cycle
        if r['event']!='retire': return
        order=int(r['order']);require(order==self.order+1,'Retire gap');self.order=order
        pc,insn,v=(int(r[k],16) for k in ('pc','insn','rd_wdata'))
        rd,trap=int(r['rd']),int(r['trap'])
        require(pc not in [self.s[k] for k in ('trap_entry','replay_mismatch','mt_bad_trap')],'First-error/default trap')
        if pc==self.s['check']:
            require(self.calls<966,'Extra check')
            if self.calls<952: gold=self.gold[self.calls]
            else:
                csr=RESTORE[self.calls-952]
                require(csr in self.saved,'Missing actual saved CSR')
                gold=self.saved[csr]&~8 if csr==0x300 else self.saved[csr]
            require(self.regs[10]==self.regs[11]==gold,f'Check {self.calls+1}: got={self.regs[10]:x} want={self.regs[11]:x} gold={gold:x}')
            self.calls+=1
        if pc==self.s['mt_handler']:
            require(len(self.traps)<2,'Extra trap');self.capture={};self.traps.append(self.capture)
            self.actions.append(dict(name='handler',cycle=cycle));self.retry=len(self.traps)==1
        if insn&127==0x73:
            f,src,csr=(insn>>12)&7,(insn>>15)&31,insn>>20
            pure=f in (2,3) and src==0 and rd and not trap
            if pure and self.s['main']<=pc<self.s['mt_handler'] and csr in RESTORE:
                self.saved.setdefault(csr,v)
            if pure and self.s['mt_handler']<=pc<self.s['mt_trap_vstart_read']+24 and csr in CSR:
                require(self.capture is not None and CSR[csr] not in self.capture,'Duplicate/missing trap capture')
                self.capture[CSR[csr]]=v
            if self.retry and csr==0x341 and f in (1,2,3,5,6,7) and (f in (1,5) or src):
                raise ValueError('Fault mepc overwritten before retry')
        if pc in self.sites and not trap:
            name=self.sites[pc]
            require(insn==ref.SITES[name], 'Site opcode '+name)
            if name=='mt_trap_vstart_read':
                require(rd==6 and v==(2 if len(self.traps)==1 else 0),'Actual trap vstart read')
            if name=='mt_prefix_checkpoint':
                require(self.retry and self.calls==3,'Fault checkpoint phase')
                for p in range(2):
                    for i in range(512):
                        require(self.u('mt_prefix',8,8+p*512+i)==ref.memword(p,i,'fault'),
                                'Full scalar prefix snapshot differs')
                require(self.u('mt_pages',8,2048)==(self.s['mt_pages']>>12<<10)|0xc7 and
                        self.u('mt_pages',8,2049)==((self.s['mt_pages']+4096)>>12<<10)|0xc7,
                        'Both target pages must remain mapped')
            if name=='mt_prefix_poison':
                require(self.regs[28]==self.s['mt_pages']+8 and self.regs[6]==ref.POISON,'Prefix poison address/data')
            if name=='mt_repair_index':
                require(self.regs[28]==self.s['mt_fix_index'],'Wrong index repair source')
            if name=='mt_restart_vstart_write':
                require(self.retry and self.regs[6]==2,'Saved vstart2 restoration')
            if name=='mt_retry_mret':
                require(self.retry and [self.u('mt_restart',8,i) for i in range(3)]==[3,24,2],
                        'Actual pre-MRET VL/vtype/vstart readbacks')
                self.retry=False
            if name=='mt_target': require(not self.retry and len(self.traps)==1,'Target before retry')
            self.actions.append(dict(name=name,cycle=cycle))
        write=scalar_store(r,self.regs)
        if write:
            a,vv,n=write
            for i,b in enumerate(vv.to_bytes(n,'little')):self.mem[a+i]=b
            if a in (self.s['mt_errors'],self.s['mt_unexpected']): require(vv==0,'Nonzero first-error state')
            if a==0xd0000000: require(vv==0 and n==8,'CTRL exit');self.exits.append(vv)
        if rd and not trap:self.regs[rd]=v
        self.regs[0]=0

    def finish(self):
        require(self.calls==self.u('mt_checks',4)==966,'Incomplete checks')
        require(self.u('mt_completed')==ref.DONE and self.exits==[0],'Missing completion/exit')
        require(self.u('mt_errors',4)==self.u('mt_unexpected')==0,'Error state')
        names=[a['name'] for a in self.actions]
        require(names==['handler','mt_trap_vstart_read','mt_prefix_checkpoint','mt_prefix_poison','mt_repair_index',
                        'mt_restart_vstart_write','mt_retry_mret','mt_target','mt_successor_indexed_store',
                        'mt_recovery_load','mt_successor_add','mt_younger_store','handler','mt_trap_vstart_read'],'Exact fault/retry/successor sequence: '+repr(names))
        require(len(self.traps)==2 and not self.retry,'Incomplete trap capture')
        for n,c in enumerate(self.traps):
            require(set(c)==set(range(10)),'Incomplete actual trap CSRs')
            got=[c[i] for i in range(10)];got[3]&=ref.MASK
            require(got==self.gold[5+n*12:15+n*12],'Actual trap CSRs differ')
            raw=[self.u('mt_records',8,n*12+i) for i in range(10)]
            require(raw==[c[i] for i in range(10)],'Stored record differs from CSR reads')
        return dict(status='INDEXED_PREFIX_CSV_PASS',rows=self.rows,retired_rows=self.order+1,last_cycle=self.cycle,
                    checks=self.calls,traps=self.traps,actions=self.actions,restore_readback_checks=14,
                    vector_memory_evidence='966 pinned on-device checks, independent expected operands; not vector RVFI data',
                    prefix_snapshot_bytes=8192,flush_evidence='software cause6/vstart2/prefix/retry/successor progress; no internal W-pressure claim')


def analyze(path,s,store):
    c=Checker(s,store)
    with path.open() as f:
        reader=csv.DictReader(f);require(reader.fieldnames==FIELDS,'CSV header')
        for row in reader:c.row(row)
    return c.finish()

