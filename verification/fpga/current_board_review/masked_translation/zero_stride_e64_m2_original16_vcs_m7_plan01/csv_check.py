"""Full16 RVFI observer: observed scalar values, exact windows, fault/CSR ledger."""
import csv
from pathlib import Path
from checker import source as o,require,load,HERE,CAP,ALLOC,VTYPE,CHECKS,SNAPSHOT_HIGH_OFFSET
old=load('zero16_memory_decode',HERE.parent/'negative_stride_store_vcs_m6_plan01/csv_check.py')
old.o=o.base
memory_op=old.memory_op
FIELDS=old.FIELDS
CSR_FIELDS=old.CSR_FIELDS
POINTS={};n=4
for c in range(16):
    POINTS[c,0]=n
    if c%4<3:n+=29+c%4;POINTS[c,1]=POINTS[c,2]=n
    n+=23;POINTS[c,3]=n;n+=1024+2*CAP+2;POINTS[c,4]=n
require(n+16==CHECKS,'Independent scalar-count accounting')

class Checker:
    def __init__(self,spec):
        self.spec=spec;self.s=spec['symbols'];self.code={int(k):v for k,v in spec['code'].items()}
        self.mem=o.base.elf_bytes(spec['elf']);self.regs={0:0};self.csrs={}
        self.rows=self.retired=self.calls=self.cap=self.boot=0;self.last_cycle=-1
        self.case=-1;self.step=10;self.suspended=False;self.enter=0;self.points=[];self.entries=[]
        self.traps=[];self.capture=None;self.capture_order=[];self.mrets=[];self.ecalls=0
        self.cvx={};self.cvx_faults=[];self.target_req=[];self.target_arch=[];self.pending={};self.done=[]
        self.refill=None;self.refills=[];self.outputs=[];self.results=[];self.data_reads=[]
        self.ctrl=[];self.exited=False;self.parked=0;self.fault_retire=0;self.target_success=[]
        self.unknown=set();self.snapshots=[];self.contexts={};self.saved=None;self.initial={}
        self.windows=spec['windows'];self.allhelper=set(self.windows['replay_0']+self.windows['replay_1'])
    def u(self,name):return o.readint(self.mem,self.s[name])
    def invalidate(self,a,n):
        for j in range(n):self.mem.pop(a+j,None);self.unknown.add(a+j)
    def scalar(self,r,insn,trap):
        a,rm,wm,val=(int(r[k],16) for k in ('mem_addr','mem_rmask','mem_wmask','mem_wdata'))
        if not(rm or wm):return
        require(not trap and not(rm and wm),'Faulting/bidirectional scalar memory')
        d=memory_op(insn,self.regs);require(d is not None,'Non-scalar RVFI masks')
        width=d['size'];bits=(1<<(width*8))-1
        require(width in (1,2,4,8) and a%8+width<=8,'Scalar width/alignment')
        require(a==(self.regs[d['base']]+d['offset'])&o.MASK64 and (rm or wm)==((1<<width)-1)<<(a%8),'Scalar address/BE')
        if wm:
            require(d['kind']=='write' and val&bits==self.regs[d['register']]&bits,'Actual scalar store source');val&=bits
            if self.refill is not None:
                require(width==8 and a==self.s['mx_pages']+4096+8*self.refill and val==37*(512+self.refill)+11,'Full upper-page refill address/value/order')
                self.refill+=1
            if a in (self.s['mx_errors'],self.s['mx_unexpected']):require(val==0,'Nonzero error')
            if a==0xd0000000:
                require(int(r['pc'],16)==self.spec['exit_store'] and width==8 and val==0,'CTRL raw0, not HTIF1');self.ctrl.append(val);self.exited=True
        else:
            rd=int(r['rd']);raw=int(r['rd_wdata'],16)
            require(d['kind']=='read' and rd==d['register'] and rd!=0,'Actual scalar load destination')
            val=raw&bits;sign=d.get('signed',width==4)
            require(raw==val|((o.MASK64^bits) if sign and val>>(8*width-1) else 0),'Sign extension')
            for j,b in enumerate(val.to_bytes(width,'little')):
                require(a+j not in self.mem or self.mem[a+j]==b,'Read disagrees with previously observed data')
            if self.case>=0 and self.u('mx_phase')==3:
                if self.s['mx_pages']<=a<self.s['mx_pages']+8192:
                    require(width==8,'Full-memory oracle uint64 width');self.data_reads.append(a)
                if self.s['mx_out']<=a<self.s['mx_out']+(ALLOC+2)*8:
                    require(width==8,'Output oracle uint64 width');self.outputs.append(a)
                if self.s['mx_result']+64<=a<self.s['mx_result']+SNAPSHOT_HIGH_OFFSET:
                    require(width==8,'Result oracle uint64 width');self.results.append(a)
        for j,b in enumerate(val.to_bytes(width,'little')):self.mem[a+j]=b;self.unknown.discard(a+j)
    def checkpoint(self):
        c,p=self.u('mx_case'),self.u('mx_phase');expected=list(POINTS)
        require(len(self.points)<len(expected) and (c,p)==expected[len(self.points)],'Original72 checkpoint order')
        require(self.calls==self.u('mx_checks')==POINTS[c,p],'Exact checkpoint scalar oracle count')
        gold=o.expected(self.s,c,p);unchecked=[]
        for a,v in gold.items():
            if a in self.unknown:
                # These stores have no RVFI payload. Require all ORIGINAL
                # output/memory and saved-prefix bytes observed by final phase.
                if p==4:
                    require(self.s['mx_action_copy']<=a<self.s['mx_action_copy']+24,'Missing final original byte observation')
                unchecked.append(a);continue
            require(self.mem.get(a)==v,f'Case{c}/phase{p} byte{a:x} got{self.mem.get(a)} expected{v}')
        for row in range(c+1):
            count=(2 if row%4<3 else 1) if row<c or p>=3 else int(row%4<3 and p>=1)
            for index in range(count):
                rec={j:o.readint(self.mem,self.s['mx_records']+192*row+96*index+8*j) for j in range(10)}
                require(rec[3]&0x8000031888==0x800,'Trap privilege/status')
                require(rec==self.contexts[row,index],'Actual CSR reads differ from stored context')
        if p==0:
            self.outputs=[];self.results=[];self.data_reads=[]
        if p==4:
            require(self.outputs==[self.s['mx_out']+8*i for i in list(range(1,CAP+1))+[0,CAP+1]],'Full64 outputs and exact2 guards')
            require(self.results==[self.s['mx_result']+64+8*i for i in range(CAP)],'Full result snapshot reads')
            require(self.data_reads==[self.s['mx_pages']+8*i for i in range(1024)],'Full8KiB original scalar oracle reads')
        self.points.append(dict(case=c,phase=p,cycle=self.last_cycle,checks=self.calls,checked_bytes=len(gold)-len(unchecked),unobservable_bytes=len(unchecked)))
    def row(self,r):
        require(set(r)==set(FIELDS) and None not in r.values(),'Malformed/truncated CSV')
        self.rows+=1;cycle=int(r['cycle']);require(cycle>=self.last_cycle,'Cycle reversal');self.last_cycle=cycle
        event=r['event'];insn=int(r['insn'],16);target=insn in (0x09c57c07,0x09c57c27)
        if event=='cvx_req':
            tid=int(r['trans_id']);require(tid not in self.cvx,'Duplicate CVX owner');self.cvx[tid]=(insn,self.case)
            if target:
                require(self.case in range(16) and insn==(0x09c57c27 if (self.case//4)%2 else 0x09c57c07),'Target identity')
                self.target_req.append((self.case,insn))
                if insn==0x09c57c27:self.invalidate(self.s['mx_pages']+4096,8)
        if event=='arch_start' and target:self.target_arch.append(int(r['order']))
        if event=='uop_alloc' and target:
            key=(int(r['order']),int(r['port']));require(key[0] in self.target_arch and key not in self.pending,'Target owner allocation');self.pending[key]=cycle
        if event=='uop_done' and target:
            key=(int(r['order']),int(r['port']));require(key in self.pending,'Target completion owner');self.done.append(key);del self.pending[key]
        if event=='cvx_resp':
            tid=int(r['trans_id']);require(tid in self.cvx,'CVX response owner');op,c=self.cvx.pop(tid)
            if int(r['trap']):
                require(op in (0x09c57c07,0x09c57c27) and c%4<3 and c not in [x['case'] for x in self.cvx_faults],'Wrong/extra CVX exception')
                self.cvx_faults.append(dict(case=c,cycle=cycle,insn=hex(op)))
        require(event in ('retire','cvx_req','cvx_resp','arch_start','uop_alloc','uop_done'),'Unknown CSV event')
        if event!='retire':return
        require(int(r['order'])==self.retired,'Retire order gap');self.retired+=1
        pc=int(r['pc'],16);rd=int(r['rd']);val=int(r['rd_wdata'],16);trap=int(r['trap'])
        require(self.code.get(pc)==insn,'Actual SoC PC/encoding')
        require(pc not in (self.s['trap_entry'],self.s['replay_mismatch']),'Default trap or mismatch function')
        if self.exited:
            require(pc==self.spec['park'] and rd==0 and int(r['mem_rmask'],16)==int(r['mem_wmask'],16)==0,'Post-CTRL only original park');self.parked+=1;return
        require(not trap or pc in (self.s['fault_0_pc'],self.s['fault_1_pc'],self.s['mx_ecall']),'Unexpected retirement trap')
        if self.refill is not None and not self.s['mx_refill_page']<=pc<self.s['restore_page']:
            require(self.refill==512,'Incomplete upper refill');self.refills.append(self.case);self.refill=None
        if pc==self.s['main']:self.saved=dict(self.csrs)
        if pc==self.s['check']:require(self.regs[10]==self.regs[11],'Actual scalar oracle comparison');self.calls+=1
        if pc in self.windows['capacity']:
            require(self.cap<3 and pc==self.windows['capacity'][self.cap] and not self.entries,'Capacity once/ordering')
            if self.cap==1:require(rd==10 and val==CAP,'Actual VLMAX64')
            self.cap+=1
        if pc in self.spec['bootstrap']:
            require(self.cap==3 and self.boot<8 and pc==self.spec['bootstrap'][self.boot] and not self.entries,'Original bootstrap window');self.boot+=1
        if pc==self.s['mx_enter_s']:
            c=self.u('mx_case');require(self.enter==c and self.points[-1]['case']==c and self.points[-1]['phase']==0,'Original S entry ordering');self.enter+=1
            require(self.regs[11]==self.u('mx_satp'),'Actual SATP argument')
        if pc in (self.s['replay_0'],self.s['replay_1']):
            self.case=self.u('mx_case');require(self.case==len(self.entries) and self.step==10 and self.cap==3 and self.boot==8,'Continuous16 entry')
            require(pc==self.s[f'replay_{(self.case//4)%2}'] and [self.regs[i] for i in range(10,16)]==o.args(self.s),'Original six arguments/helper')
            self.step=0;self.entries.append(self.case)
        h=self.windows[f'replay_{(self.case//4)%2}'] if self.case>=0 else []
        if 0<self.step<10 and not self.suspended and pc not in h:
            require(self.step==5 and pc==self.s['mx_handler'],'Interrupted original helper outside fault boundary')
        if pc==self.s['mx_handler']:
            finish=self.u('mx_marker')==1
            require(not self.pending and set(self.target_arch)=={x[0] for x in self.done},'Handler before same-owner target completion')
            if finish:require(self.step==10,'Ecall before helper completion')
            else:
                require(self.step==5 and self.case%4<3 and self.cvx_faults[-1]['case']==self.case,'Original fault request boundary');self.suspended=True
            n=int(self.case%4<3) if finish else 0
            require((self.case,n) not in self.contexts,'Duplicate handler');self.capture={};self.contexts[self.case,n]=self.capture
            self.capture_order=[];self.traps.append(dict(case=self.case,index=n,finish=finish,cycle=cycle))
        if pc in self.allhelper:
            require(pc==h[self.step] and not self.suspended,'Original contiguous ten-instruction window')
            i=self.step
            if i in (0,4,7):require(rd==5 and val==(8 if i==4 else CAP),'Helper VSET VL')
            if i==5:
                require(self.regs[10]==o.VA+4096 and self.regs[28]==0,'Actual zero-stride source/base')
                if trap:self.fault_retire+=1;return
                require((self.case%4==3 and not any(x['case']==self.case for x in self.mrets)) or
                        self.mrets[-1]['case']==self.case,'Successful target before original retry')
                self.target_success.append(self.case)
            if i==6:require(rd==10 and val==0,'Original immediate returned vstart')
            self.step+=1
        if insn&127==0x73 and (insn>>12)&7:
            csr=insn>>20;f=(insn>>12)&7;src=(insn>>15)&31;writing=f in (1,5) or src!=0
            if self.s['mx_trap']<=pc<self.s['main'] and csr in CSR_FIELDS and rd and f==2 and src==0:
                require(self.capture is not None and CSR_FIELDS[csr] not in self.capture,'Actual handler CSR owner/multiplicity')
                self.capture[CSR_FIELDS[csr]]=val;self.capture_order.append(csr)
            if not writing:
                if rd:
                    self.csrs[csr]=val
                    if self.saved is not None and self.cap==0:self.initial.setdefault(csr,val)
            else:
                v=src if f>=5 else self.regs[src]
                require(f in (1,5) or csr in self.csrs,'Unknown prior CSR for read-modify-write')
                prev=self.csrs.get(csr)
                self.csrs[csr]=v if f in (1,5) else prev|v if f in (2,6) else prev&~v
                if csr==0x341 and self.suspended:raise ValueError('Fault retry mepc overwritten')
        if insn&0x707f==0x7057:
            vt=(insn>>20)&1023 if insn>>30==3 else (insn>>20)&2047 if insn>>31==0 else self.regs[(insn>>20)&31]
            self.csrs[0xc21]=vt
            if rd: self.csrs[0xc20]=val
            elif insn>>30==3: self.csrs[0xc20]=(insn>>15)&31
            else: self.csrs[0xc20]=self.regs[(insn>>15)&31]
            self.csrs[8]=0
        if pc==self.s['mx_refill_page']:
            require(self.case>=8 and self.refill is None and self.case not in self.refills,'Original8 unmapped refills');self.refill=0
        if pc==self.s['mx_trap_mret']:
            require(self.capture is not None and len(self.capture)==10 and self.capture_order[:3]==[8,0xc21,0xc20],'Vector CSR reads before diagnostic RVV')
            if self.suspended:
                require(self.points[-1]['case']==self.case and self.points[-1]['phase']==2,'Retry before repair checkpoint')
                require([self.regs[i] for i in range(10,16)]==o.args(self.s) and self.regs[28]==0,'Retry original arguments')
                require(self.csrs.get(0x341)==self.s[f'fault_{(self.case//4)%2}_pc'] and
                        [self.csrs.get(k) for k in (0xc20,0xc21,8)]==[8,VTYPE,self.case%4] and self.csrs.get(0x300,0)&0x1800==0x800,'Same PC/VL/type/start/privilege retry')
                self.mrets.append(dict(case=self.case,cycle=cycle,mepc=self.csrs[0x341],vstart=self.csrs[8]));self.suspended=False
        if pc==self.s['mx_ecall']:self.ecalls+=1
        if insn&0x707f==0x7027 and pc not in (self.s['fault_0_pc'],self.s['fault_1_pc']):
            a=self.regs[(insn>>15)&31]
            if pc in self.spec['bootstrap']:require(a==self.s['mx_action_copy'],'Bootstrap destination');width=24
            else:
                require(a in (self.s['mx_out']+8,self.s['mx_fault']+64,self.s['mx_result']+64),'Original vector store destination');width=8*CAP
            self.invalidate(a,width);self.snapshots.append((self.case,a))
        if pc==self.s['mx_checkpoint']:self.checkpoint()
        self.scalar(r,insn,trap)
        if rd and not trap:self.regs[rd]=val
        self.regs[0]=0
    def finish(self):
        require(self.entries==list(range(16)) and self.target_success==list(range(16)) and self.step==10 and self.enter==16,'Full16 source calls/completion')
        require([(x['case'],x['phase']) for x in self.points]==list(POINTS),'Original72 checkpoints')
        faultcases=[c for c in range(16) if c%4<3]
        require([x['case'] for x in self.mrets]==faultcases and [x['case'] for x in self.cvx_faults]==faultcases,'Original12 fault/retry contexts')
        require(len(self.traps)==28 and self.ecalls==16 and self.refills==list(range(8,16)) and self.refill is None,'Original16ecalls/8refills')
        require(self.calls==self.u('mx_checks')==CHECKS and self.u('mx_completed')==o.DONE and self.u('mx_signals')==12,'Full original oracle/terminal')
        want=[(c,0x09c57c27 if (c//4)%2 else 0x09c57c07) for c in range(16) for _ in range(1 if c%4==3 else 2)]
        require(self.target_req==want and len(self.target_arch)==28 and not self.pending and not self.cvx,'Exact28 target attempts/full backend completion')
        require(self.ctrl==[0] and self.cap==3 and self.boot==8,'CTRL0/capacity/bootstrap')
        for k,v in self.initial.items():
            if k!=0xc22:require(self.csrs.get(k)==v,'Original CSR restored at terminal')
        return dict(status='PASS_ORIGINAL16_FULL_ORACLE',rows=self.rows,retired=self.retired,last_cycle=self.last_cycle,
          cases=16,checks=self.calls,outputs=16*CAP,guards=32,memory_words=16384,returned_vstart=16,
          checkpoints=self.points,handler_csrs=[dict(**t,csrs=self.contexts[t['case'],t['index']]) for t in self.traps],
          faults=self.cvx_faults,retry_mrets=self.mrets,ecalls=self.ecalls,refills=self.refills,target_attempts=len(self.target_req),
          optional_trapping_retirements=self.fault_retire,ctrl=self.ctrl,postexit_park=self.parked,
          unobserved='Bootstrap copy has no scalar read; pre-cleanup vector side effects and AXI/MMU physical transactions are not proven by RVFI',
          original_final_data='Full actual scalar reads for all source CAP outputs/2guards/8KiB each; no invented vector-write payload',
          linux_stall_closed=False,current_mask_drain_candidate_tested=True)

def analyze(path,spec):
    c=Checker(spec)
    try:
        with Path(path).open() as f:
            rows=csv.DictReader(f);require(rows.fieldnames==FIELDS,'CSV columns')
            for r in rows:c.row(r)
        return c.finish()
    except (ValueError,KeyError,IndexError,TypeError,OSError) as e:
        return dict(status='NOT_PASS_ORIGINAL16',error=str(e),rows=c.rows,retired=c.retired,last_cycle=c.last_cycle,
                    checks=c.calls,case=c.case,step=c.step,checkpoints=c.points)

