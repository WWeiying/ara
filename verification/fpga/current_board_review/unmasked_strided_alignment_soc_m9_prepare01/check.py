"""Independent scalar oracle and exact alignment/retry trace contract."""
import csv
import importlib.util
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
spec=importlib.util.spec_from_file_location('rv64c_current',ROOT/'verification/coverage/scoped_rv64c_memory.py')
decoder=importlib.util.module_from_spec(spec);spec.loader.exec_module(decoder)
GUARD=0xe370697ce370697c
POISON=0xfedcba9876543210
DONE=0x7374726964650009
MASK=0x8000031888
MASK64=(1<<64)-1
RESTORE=[0x180,0x305,0x341,0x342,0x343,0x302,0x303,0x304,0xc20,0xc21,8,15,3,0x300]
CSR={0x342:0,0x341:1,0x343:2,0x300:3,0x180:4,0xc20:5,0xc21:6,8:7,3:8,15:9}
FIELDS='cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap'.split(',')

def need(ok,msg):
    if not ok:raise ValueError(msg)
def seed(i):return 0x9134576800000000^(37*i+11)
def data(p,i):return 0xa136570000000000^(p<<48)^(53*i+19)
def base(s,sv):return s['mt_mem']+16-(0x40000000 if sv else 0)
def satp(s,sv):return (8<<60)|(s['mt_root']>>12) if sv else 0
def record(s,st,sv,n):
    return [(9 if sv else 11) if n else 6 if st else 4,s['mt_ecall'] if n else s['mt_target'],
            0 if n else base(s,sv)+4,0x800 if sv else 0x1800,satp(s,sv),2,24,0 if n else 1,117,5]
def gold(s,st,sv):
    g=[128,0,0,0,2]+record(s,st,sv,0)+record(s,st,sv,1)
    for v in (2,24,0,117,5):g += [v,v]
    g += [1]
    for b in range(4):
        g += [GUARD]*4
        for i in range(16):
            if b==1 and not st and i==1:continue
            v=seed(i)
            if not st and ((b==1 and i==0) or (b==2 and i<2)):v=data(0,i)
            if b==3 and i<2:v=data(1,i)
            g.append(v)
    g += [seed(0) if st and i==0 else data(0,i) for i in range(16)]
    for p in range(2):
        g += [GUARD]*4
        for i in range(16):
            v=data(p,i)
            if p==0 and i==0:v=POISON
            if p==0 and st and i==1:v=seed(1)
            if p==1 and i in (8,9):v=data(1,i-8)
            g.append(v)
    g += [0x200000cf if sv and i in (1,2) else 0 for i in range(512)]
    need(len(g)==683+int(st),'Gold count')
    return g

def memory_op(insn):
    if insn&3!=3:return decoder.decode(insn)
    op,f=insn&127,(insn>>12)&7
    if op not in (3,35):return None
    write=op==35;imm=((insn>>25)<<5)|((insn>>7)&31) if write else insn>>20
    if imm&2048:imm-=4096
    return dict(kind='write' if write else 'read',size=1<<(f if write else f&3),
                base=(insn>>15)&31,register=(insn>>20)&31 if write else (insn>>7)&31,
                offset=imm,signed=not write and f<4)

SITES=['mt_target','mt_trap_vstart_read','mt_fault_snapshot','mt_poison_prefix','mt_repair_stride',
       'mt_restore_start','mt_retry_mret','mt_result_snapshot','mt_successor_load','mt_successor_store','mt_next_snapshot']
class Observer:
    def __init__(self,spec,store,sv39):
        self.spec=spec;self.s=spec['symbols'];self.code={int(k):v for k,v in spec['code'].items()}
        self.st=store;self.sv=sv39;self.g=gold(self.s,store,sv39)
        self.regs={0:0};self.mem={};self.saved={};self.captures=[];self.capture=None
        self.calls=0;self.actions=[];self.retired=0;self.exit=[];self.entered=False;self.retry=False
        self.sites={self.s[n]:n for n in SITES};self.initialized=set();self.target_success=0
        self.cvx={};self.target_reqs=0;self.cvx_faults=0;self.uops={};self.done=[]
    def phys(self,a):return a+0x40000000 if 0x40000000<=a<0x80000000 else a
    def u(self,name,n=8,offset=0):
        a=self.s[name]+offset;need(all(a+i in self.mem for i in range(n)),'Missing state '+name)
        return int.from_bytes(bytes(self.mem[a+i] for i in range(n)),'little')
    def write(self,a,v,n):
        a=self.phys(a)
        for i,b in enumerate((v&((1<<(8*n))-1)).to_bytes(n,'little')):self.mem[a+i]=b
    def initial(self):
        for b,name in enumerate(('mt_seed','mt_fault','mt_result','mt_next','mt_mem','mt_other')):
            for i in range(20):
                v=GUARD if i<2 or i>=18 else seed(i-2) if b==0 else GUARD if b<4 else data(b-4,i-2)
                need(self.u(name,8,8*i)==v,'Actual initialization '+name)
        for i in range(512):need(self.u('mt_root',8,8*i)==(0x200000cf if self.sv and i in(1,2) else 0),'Root initialization')
        need(self.u('mt_target_addr')==base(self.s,self.sv) and self.u('mt_expected_satp')==satp(self.s,self.sv),'Mapped address setup')
    def step(self,pc,insn,gprs,access=(),trap=False,mode=None):
        if pc>=0x80000000:need(self.code.get(pc)==insn,'Actual ELF encoding at '+hex(pc))
        need(pc not in (self.s['trap_entry'],self.s['replay_mismatch'],self.s['mt_bad_trap']),'First error/default trap')
        if pc==self.s['mt_check'] and not trap:
            i=self.calls;need(i<len(self.g)+14,'Extra oracle call')
            if i<len(self.g):v=self.g[i]
            else:
                csr=RESTORE[i-len(self.g)];need(csr in self.saved,'Missing saved CSR')
                v=self.saved[csr]&~8 if csr==0x300 else self.saved[csr]
            need(self.regs.get(10)==self.regs.get(11)==v,f'Check{i+1} got={self.regs.get(10)} expected_operand={self.regs.get(11)} gold={v}')
            self.calls+=1
        if pc==self.s['mt_enter']:
            self.initial();self.entered=True
        if pc==self.s['mt_handler']:
            need(len(self.captures)<2,'Extra trap');self.capture={};self.captures.append(self.capture)
            self.actions.append('handler');self.retry=len(self.captures)==1
        if insn&127==0x73:
            f,src,csr,rd=(insn>>12)&7,(insn>>15)&31,insn>>20,(insn>>7)&31
            pure=f in (2,3) and src==0 and rd!=0 and not trap
            if pure:
                need(rd in gprs,'Missing actual CSR result')
                if not self.entered and csr in RESTORE:self.saved.setdefault(csr,gprs[rd])
                if self.s['mt_handler']<=pc<self.s['mt_check_ecall'] and csr in CSR:
                    need(self.capture is not None and CSR[csr] not in self.capture,'CSR capture repetition')
                    self.capture[CSR[csr]]=gprs[rd]
            if self.retry and csr==0x341 and f in (1,2,3,5,6,7) and (f in (1,5) or src):
                raise ValueError('Mepc changed before same-PC retry')
        name=self.sites.get(pc)
        if name and not trap:
            self.actions.append(name)
            if mode is not None:
                user_site=name in ('mt_target','mt_result_snapshot','mt_successor_load','mt_successor_store','mt_next_snapshot')
                need(mode==(1 if self.sv and user_site else 3),'Actual site privilege '+name)
            if name=='mt_trap_vstart_read':need(gprs.get(6)==(1 if len(self.captures)==1 else 0),'Fault vstart read')
            if name=='mt_restore_start':need(self.regs.get(6)==1,'Restored original vstart')
            if name=='mt_retry_mret':need(self.retry,'Unpaired retry');self.retry=False
            if name=='mt_target':need(len(self.captures)==1 and not self.retry,'Target not same-PC retry');self.target_success+=1
        for kind,a,v,n in access:
            d=memory_op(insn)
            if d is not None:
                need(d['kind']==kind and d['size']==n,'Scalar access kind/size')
                need(d['base'] in self.regs and a==(self.regs[d['base']]+d['offset'])&MASK64,'Scalar effective address')
                if kind=='write':
                    src=d['register'];bits=(1<<(8*n))-1
                    if src not in self.regs:
                        # Only compiler entry spills may save opaque caller registers.
                        need(not self.entered and self.s['main']<=pc<self.s['mt_handler'] and
                             d['base']==2 and src in (8,9,*range(18,28)) and n==8,'Unknown source GPR')
                        self.regs[src]=v&bits
                    need(v&bits==self.regs[src]&bits,'Scalar store operand')
            if kind=='write':
                self.write(a,v,n)
                if a in (self.s['mt_errors'],self.s['mt_unexpected']):need(v==0,'Nonzero failure state')
                if a in (self.s['tohost'],0xd0000000):self.exit.append((a,v))
        self.regs.update(gprs);self.regs[0]=0;self.retired+=1
    def finish(self,endpoint):
        need(self.calls==len(self.g)+14==self.u('mt_checks',4),'Incomplete checks')
        need(self.u('mt_completed')==DONE and self.u('mt_errors',4)==self.u('mt_unexpected')==0,'Magic/error state')
        need(self.exit==[(self.s['tohost'],1)] if endpoint=='spike' else self.exit==[(0xd0000000,0)],'Actual exit endpoint')
        goldactions=['handler','mt_trap_vstart_read','mt_fault_snapshot','mt_poison_prefix','mt_repair_stride',
                     'mt_restore_start','mt_retry_mret','mt_target','mt_result_snapshot','mt_successor_load',
                     'mt_successor_store','mt_next_snapshot','handler','mt_trap_vstart_read']
        need(self.actions==goldactions and len(self.captures)==2 and not self.retry and self.target_success==1,'Exact actions')
        for n,c in enumerate(self.captures):
            need(set(c)==set(range(10)),'Complete trap CSR capture')
            values=[c[i] for i in range(10)];values[3]&=MASK
            need(values==record(self.s,self.st,self.sv,n),'Precise fault/ecall state')
            need([self.u('mt_records',8,n*80+i*8) for i in range(10)]==[c[i] for i in range(10)],'Stored CSR vs actual reads')
        return dict(status='FULL_ORACLE_PASS',checks=self.calls,retired=self.retired,actions=self.actions,
                    traps=self.captures,restore_readback_checks=14,endpoint=endpoint)

def reference(path,spec,st,sv):
    c=Observer(spec,st,sv);s=c.s;partials=0;traps=[]
    with Path(path).open() as f:
        for line in f:
            t=re.search(r'exception\s+(\w+), epc 0x([0-9a-f]+)',line)
            if t:traps.append((t[1],int(t[2],16)))
            m=re.match(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$',line)
            if not m:continue
            mode,pc,insn,tail=int(m[1]),int(m[2],16),int(m[3],16),m[4]
            gp={int(n):int(v,16) for n,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)}
            accesses=[(int(a,16),int(v,16) if v else None) for a,v in re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?',tail)]
            d=memory_op(insn);acc=[]
            for a,v in accesses:
                if v is None:continue
                width=d['size'] if d else {0:1,5:2,6:4,7:8}[(insn>>12)&7]
                acc.append(('write',a,v,width))
            if pc==s['mt_target'] and not partials:
                need('e64 m1 l2' in tail and re.search(r'c8_vstart 0x0*1\b',tail),'Actual partial fault vstart')
                need(accesses==[(base(s,sv),seed(0) if st else None)],'Actual completed prefix access')
                for _,a,v,n in acc:c.write(a,v,n)
                partials+=1;continue
            if pc==s['mt_target']:
                need(accesses==[(base(s,sv)+8,seed(1) if st else None)],'Actual retry must start at element1')
            c.step(pc,insn,gp,acc,mode=mode)
    need(partials==1 and traps==[('trap_store_address_misaligned' if st else 'trap_load_address_misaligned',s['mt_target']),
                                  ('trap_supervisor_ecall' if sv else 'trap_machine_ecall',s['mt_ecall'])],'Exact raw trap ledger')
    result=c.finish('spike');result.update(partial_attempts=partials,raw_traps=traps)
    return result
