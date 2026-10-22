"""Scalar RVFI values reconstruct vector-store bytes; no invented vector payload."""
import csv
from pathlib import Path
from checker import source as o,require
FIELDS='cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap'.split(',')
CSR_FIELDS={0x342:0,0x341:1,0x343:2,0x300:3,0x180:4,0xc20:5,0xc21:6,8:7,3:8,15:9}
COUNTS=(4117,8450,12563,17052)

def memory_op(insn,regs):
    if insn&3!=3:return o.decoder.decode(insn)
    op=insn&127;f=(insn>>12)&7
    if op not in (3,35):return None
    write=op==35;size=1<<(f if write else f&3)
    imm=(((insn>>25)<<5)|((insn>>7)&31)) if write else insn>>20
    if imm&2048:imm-=4096
    return dict(kind='write' if write else 'read',size=size,base=(insn>>15)&31,
                register=(insn>>20)&31 if write else (insn>>7)&31,offset=imm,
                signed=not write and f<4)

class Checker:
    def __init__(self,spec):
        self.spec=spec;self.s=spec['symbols'];self.code={int(k):v for k,v in spec['code'].items()}
        self.mem=o.elf_bytes(spec['elf']);self.regs={i:0 for i in range(32)};self.csrs={}
        self.rows=0;self.retired=0;self.last_cycle=-1;self.calls=0;self.actions=[];self.points=[]
        self.step=0;self.suspended=False;self.cap=0;self.enter=0;self.traps=[];self.capture=None
        self.target_traps=0;self.target_success=0;self.mrets=[];self.refill=None;self.refills=[]
        self.memory_phase=None;self.memory_reads=[];self.snapshots=[];self.output_reads=[]
        self.ctrl=[];self.exited=False;self.parked=0;self.cvx={};self.cvx_faults=[]
    def u64(self,name):return o.readint(self.mem,self.s[name])
    def scalar(self,r,insn,trap):
        a,rm,wm,value=(int(r[k],16) for k in ('mem_addr','mem_rmask','mem_wmask','mem_wdata'))
        if not (rm or wm):return
        require(not trap and not(rm and wm),'Faulting/bidirectional scalar memory row')
        d=memory_op(insn,self.regs);require(d is not None,'Non-scalar RVFI memory mask')
        width=d['size'];require(width in (1,2,4,8) and a%8+width<=8,'Scalar alignment/width')
        require(a==(self.regs[d['base']]+d['offset'])&o.MASK64,'Scalar effective address')
        require((wm or rm)==((1<<width)-1)<<(a%8),'Shifted RVFI byte-enable')
        bits=(1<<(8*width))-1
        if wm:
            require(d['kind']=='write' and value&bits==self.regs[d['register']]&bits,'Scalar store source')
            value&=bits
            if self.refill is not None:
                index=self.refill
                require(width==2 and a==self.s['mx_pages']+2*index and value==o.original(index),'Lower refill address/value/order')
                self.refill+=1
            if a in (self.s['mx_errors'],self.s['mx_unexpected']):require(value==0,'Nonzero error store')
            if a==self.s['mx_pages']+16384 and value:
                require(self.actions[-1:] == ['checkpoint1'] and width==8 and
                        value==(self.s['mx_pages']>>12<<10)|0xc7,'Premature/wrong lower mapping')
                self.actions.append('pte')
            if a==0xd0000000:
                require(int(r['pc'],16)==self.spec['exit_store'] and width==8 and value==0,'CTRL raw exit must be0, not HTIF1')
                self.ctrl.append(value);self.exited=True
        else:
            rd=int(r['rd']);raw=int(r['rd_wdata'],16)
            require(d['kind']=='read' and rd==d['register'] and rd!=0,'Scalar load destination')
            value=raw&bits
            signed=d.get('signed',width==4)
            want=value|((o.MASK64^bits) if signed and value>>(8*width-1) else 0)
            require(raw==want,'Signed/unsigned scalar load result')
            for j,b in enumerate(value.to_bytes(width,'little')):
                require(a+j not in self.mem or self.mem[a+j]==b,'Scalar read disagrees with stored/ELF bytes')
            if self.memory_phase is not None and self.s['mx_pages']<=a<self.s['mx_pages']+8192:
                require(width==2,'Full memory oracle halfword width');self.memory_reads.append(a)
            if self.step==10 and self.s['mx_out']<=a<self.s['mx_out']+260:
                require(width==2,'Full output oracle halfword width');self.output_reads.append(a)
        for j,b in enumerate(value.to_bytes(width,'little')):self.mem[a+j]=b
    def row(self,r):
        require(set(r)==set(FIELDS) and None not in r.values(),'Malformed/truncated row')
        self.rows+=1;cycle=int(r['cycle']);require(cycle>=self.last_cycle,'Cycle reversal');self.last_cycle=cycle
        event=r['event'];insn=int(r['insn'],16)
        if event=='cvx_req':
            tid=int(r['trans_id']);require(tid not in self.cvx,'Duplicate CVX ID');self.cvx[tid]=insn
        if event=='cvx_resp':
            tid=int(r['trans_id']);require(tid in self.cvx,'CVX response without request');op=self.cvx.pop(tid)
            if int(r['trap']):
                require(op==0x09c55c07 and not self.cvx_faults,'Wrong/extra CVX exception')
                self.cvx_faults.append(dict(cycle=cycle,insn=hex(op)))
        require(event in ('retire','cvx_req','cvx_resp','arch_start','uop_alloc','uop_done'),'Unknown event')
        if event!='retire':return
        require(int(r['order'])==self.retired,'Retirement order gap');self.retired+=1
        pc=int(r['pc'],16);rd=int(r['rd']);val=int(r['rd_wdata'],16);trap=int(r['trap'])
        require(self.code.get(pc)==insn,'Actual ELF PC/encoding mismatch')
        require(pc not in self.spec['unused'] and pc not in (self.s['trap_entry'],self.s['replay_mismatch']),'Unused helper/default trap/mismatch')
        if self.exited:
            require(pc==self.spec['park'] and rd==0 and int(r['mem_rmask'],16)==int(r['mem_wmask'],16)==0,'Non-park after CTRL')
            self.parked+=1;return
        require(not trap or pc in (self.s['fault_0_pc'],self.s['mx_ecall']),'Unexpected retirement trap')
        if self.refill is not None and not self.s['mx_refill_page']<=pc<self.s['mx_trap']:
            require(self.refill==2048,'Incomplete lower page refill');self.refills.append(self.refill);self.refill=None
        if pc==self.s['check']:
            require(self.regs[10]==self.regs[11],'Actual scalar comparison failure');self.calls+=1
        if pc==self.s['check_memory']:
            phase=self.regs[10];require(phase==len(self.points),'Memory phase/order')
            self.memory_phase=phase;self.memory_reads=[]
        if pc==self.s['mx_enter_s']:
            self.enter+=1;require(self.enter==1 and self.points[-1:][0]['phase']==0,'Missing initial state/extra entry')
            require(self.regs[11]==(8<<60)|((self.s['mx_pages']+8192)>>12),'S-mode SATP argument')
        if pc in self.spec['capacity']:
            require(self.cap<3 and pc==self.spec['capacity'][self.cap] and self.step==0,'Capacity once/order')
            if self.cap==1:require(rd==10 and val==64,'Actual VLMAX64')
            self.cap+=1
        if 0<self.step<10 and not self.suspended and pc not in self.spec['helper']:
            require(self.step==5 and pc==self.s['mx_handler'],'Interrupted original helper outside fault boundary')
        if pc==self.s['mx_handler']:
            require(len(self.traps)<2,'Extra trap handler')
            if not self.traps:require(self.step==5 and len(self.cvx_faults)==1,'Missing original fault request');self.suspended=True
            else:require(self.step==10,'Completion trap before helper end')
            self.capture={};self.traps.append(self.capture);self.actions.append('handler')
        if pc in self.spec['helper']:
            require(self.cap==3 and pc==self.spec['helper'][self.step] and not self.suspended,'Original ten-instruction window/order')
            i=self.step
            if i==0:
                require(self.enter==1 and self.actions[-1:] == ['checkpoint0'],'Wrong first helper phase')
                require([self.regs[j] for j in range(10,16)]==[o.VA+4118,self.s['mx_input'],self.s['mx_out']+2,self.s['mx_mask'],64,self.s['mx_stride']],'Original six arguments')
            if i in (0,4,7):require(rd==5 and val==(8 if i==4 else 64),'Helper VSET return')
            if i==5:
                require(self.regs[10]==o.VA+4118 and self.regs[28]==o.MASK64-7,'Target base/signed stride')
                if trap:self.target_traps+=1;require(self.target_traps==1,'Duplicate trap-retire');return
                require(len(self.mrets)==1 and self.actions[-1:] == ['retry'],'Target success before repair/MRET')
                self.target_success+=1;self.actions.append('target')
            if i==6:require(rd==10 and val==0,'Immediate returned vstart')
            self.step+=1
        if insn&127==0x73 and (insn>>12)&7:
            csr=insn>>20;f=(insn>>12)&7;src=(insn>>15)&31;writing=f in (1,5) or src!=0
            if self.s['mx_trap']<=pc<self.s['main'] and csr in CSR_FIELDS and rd and f==2 and src==0:
                require(self.capture is not None and CSR_FIELDS[csr] not in self.capture,'Repeated/unowned handler CSR')
                self.capture[CSR_FIELDS[csr]]=val
            if not writing:
                if rd:self.csrs[csr]=val
            else:
                value=src if f>=5 else self.regs[src];old=self.csrs.get(csr,0)
                self.csrs[csr]=value if f in (1,5) else old|value if f in (2,6) else old&~value
                if csr==0x341 and self.suspended:raise ValueError('Fault mepc overwritten')
        if insn&0x707f==0x7057:
            require(rd!=0 or pc not in self.spec['helper'],'Missing VSET result')
            if insn>>30==3:vtype=(insn>>20)&1023
            elif insn>>31==0:vtype=(insn>>20)&2047
            else:vtype=self.regs[(insn>>20)&31]
            self.csrs[0xc21]=vtype;self.csrs[0xc20]=val if rd else self.regs[(insn>>15)&31];self.csrs[8]=0
        if pc==self.s['mx_repair_sfence']:
            require(self.actions[-1:] == ['pte'] and self.regs[(insn>>15)&31]==o.VA,'Lower-page addressed repair')
            self.actions.append('repair')
        if pc==self.s['mx_refill_page']:
            require(self.actions[-1:] == ['repair'] and self.refill is None,'Refill order');self.refill=0;self.actions.append('refill')
        if pc==self.s['mx_trap_mret']:
            require(self.capture and len(self.capture)==10,'Incomplete actual handler CSR reads')
            if len(self.traps)==1:
                require(self.suspended and self.actions[-1:] == ['checkpoint2'],'Retry before full repair checkpoint')
                o.retry_context(self.s,self.regs,self.csrs)
                self.mrets.append(dict(cycle=cycle,mepc=self.csrs[0x341],vstart=self.csrs[8],base=self.regs[10],stride=self.regs[28]))
                self.suspended=False;self.actions.append('retry')
            else:self.actions.append('return_m')
        if pc==self.s['mx_younger_store']:self.actions.append('younger')
        if insn&0x707f==0x5027:
            a=self.regs[(insn>>15)&31];valid=[self.s['mx_out']+2]
            valid += [self.s[n]+64+128*j for n in ('mx_fault','mx_result') for j in range(3)]
            require(a in valid,'Unexpected vector destination')
            for j in range(128):self.mem.pop(a+j,None)
            self.snapshots.append(a)
        if pc==self.s['mx_checkpoint']:
            phase=self.u64('mx_phase');require(phase==len(self.points)==self.memory_phase,'Checkpoint phase')
            require(self.memory_reads==[self.s['mx_pages']+2*i for i in range(4096)],'Missing/reordered full8KiB scalar reads')
            checked=o.compare(self.mem,self.s,phase)
            count=2 if phase==3 else 1 if phase else 0
            require(len(self.traps)==count and self.calls==COUNTS[phase] and self.u64('mx_checks')==self.calls,'Checkpoint trap/oracle count')
            for n in range(count):
                actual={j:o.readint(self.mem,self.s['mx_records']+96*n+8*j) for j in range(10)}
                require(self.traps[n]==actual,'Actual CSR reads vs stored context')
            self.points.append(dict(phase=phase,cycle=cycle,bytes=checked,checks=self.calls));self.actions.append('checkpoint'+str(phase))
            self.memory_phase=None
        self.scalar(r,insn,trap)
        if rd and not trap:self.regs[rd]=val
        self.regs[0]=0
    def finish(self):
        require(self.actions==['checkpoint0','handler','checkpoint1','pte','repair','refill','checkpoint2','retry','target','younger','handler','return_m','checkpoint3'],'Exact source fault/repair/order')
        require(self.step==10 and self.cap==3 and self.target_success==1 and len(self.mrets)==1,'Original helper/capacity/retry')
        require(self.refills==[2048] and self.refill is None,'Complete lower page refill')
        require(self.calls==self.u64('mx_checks')==17274 and self.u64('mx_completed')==o.DONE,'Complete scalar oracle/CSR/completion')
        require(self.output_reads==[self.s['mx_out']+2*i for i in list(range(1,65))+[0,65]+list(range(66,130))],'Complete output64/guards/extrastorage reads')
        require(self.ctrl==[0] and len(self.cvx_faults)==1 and not self.cvx,'CTRL/CVX terminal')
        return dict(status='PASS_NEGATIVE_STRIDE_FULL_SINGLE',rows=self.rows,retired=self.retired,last_cycle=self.last_cycle,
                    checks=self.calls,checkpoints=self.points,actual_handler_csrs=self.traps,retry_mrets=self.mrets,
                    helper_instructions=10,optional_trapping_retirements=self.target_traps,refills=self.refills,
                    actions=self.actions,ctrl=self.ctrl,cvx_faults=self.cvx_faults,postexit_park=self.parked,
                    vector_evidence='Actual scalar loads after pinned vector stores; no direct RVFI vector payload claim')

def analyze(path,spec):
    checker=Checker(spec)
    try:
        with Path(path).open() as f:
            rows=csv.DictReader(f);require(rows.fieldnames==FIELDS,'CSV columns')
            for row in rows:checker.row(row)
        return checker.finish()
    except (ValueError,KeyError,TypeError,OSError,IndexError) as error:
        return dict(status='NOT_PASS_NEGATIVE_STRIDE',error=str(error),rows=checker.rows,
                    retired=checker.retired,last_cycle=checker.last_cycle,checks=checker.calls,
                    actions=checker.actions,checkpoints=checker.points)
