#!/usr/bin/env python3
"""Post-run extended8 CSV checks; never starts or polls a simulator."""
import csv
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import reference as ref

FIELDS = 'cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap'.split(',')
CSR = {0x342:0,0x341:1,0x343:2,0x300:3,0x180:4,0xc20:5,0xc21:6,8:7,3:8,15:9}
COUNTS = [630]*5+[456,448,456]
require = ref.base.require


def scalar_store(row, regs):
    """RVFI uses byte-lane mask but unshifted source data (including C.SW)."""
    insn,addr,mask,value = (int(row[k],16) for k in ('insn','mem_addr','mem_wmask','mem_wdata'))
    if not mask:
        return None
    if insn & 3 != 3:
        d = ref.base.compressed_memory(insn)
        require(d is not None and d['kind']=='write','Unexpected compressed memory write')
        width,source = d['size'],d['register']
        require(addr == (regs[d['base']]+d['offset']) & ((1<<64)-1),'Compressed store address differs')
    elif insn & 127 == 0x23:
        width,source = 1<<((insn>>12)&7),(insn>>20)&31
        imm = ((insn>>25)<<5)|((insn>>7)&31)
        if imm & 2048: imm-=4096
        require(addr == (regs[(insn>>15)&31]+imm)&((1<<64)-1),'Scalar store address differs')
    else:
        # Vector data are not scalar RVFI memory writes in this monitor.
        raise ValueError('Unexpected non-scalar RVFI write')
    require(width in (1,2,4,8) and addr%8+width<=8,'Unsupported scalar write width/alignment')
    require(mask == ((1<<width)-1) << (addr%8),'RVFI byte mask differs from instruction')
    bits=(1<<(width*8))-1
    require(value & bits == regs[source] & bits,'Store value differs from source register')
    return addr,value & bits,width


class Checker:
    def __init__(self,symbols):
        self.s=symbols; self.regs={i:0 for i in range(32)}; self.mem={}
        self.c=-1; self.active=False; self.last_cycle=-1; self.order=-1
        self.calls=0; self.enter_calls=0; self.finished=[]; self.points=[]
        self.actions=[[] for _ in range(8)]; self.traps=[]; self.capture=None
        self.exit=[]; self.warnings=[]; self.recorded_error=None
        self.vstart_write=None

    def value(self,name,index=0):
        return self.u64(self.s[name]+index*8)

    def u64(self,address):
        require(all(address+i in self.mem for i in range(8)),f'Missing scalar state {address:#x}')
        return int.from_bytes(bytes(self.mem[address+i] for i in range(8)),'little')

    def action(self,name):
        require(0<=self.c<8,'Action outside active case')
        self.actions[self.c].append(name)

    def record(self,c,n):
        return [self.u64(self.s['mx_records']+c*192+n*96+j*8) for j in range(12)]

    def check_records(self,c,phase):
        used=1 if phase==1 or not ref.CAUSE[c] else 2
        pages=self.s['mx_pages']
        for n in range(used):
            fault=bool(ref.CAUSE[c]) and n==0
            gold=[ref.CAUSE[c] if fault else 9,self.s[ref.SITE[c]] if fault else self.s['mx_ecall'],
                ref.VA+ref.OFF[c]+ref.START[c]*ref.STRIDE[c] if fault else 0,0x800,
                (8<<60)|((pages+8192)>>12),8,8,ref.START[c] if fault else 0,117,5,
                0 if fault else 1,0 if fault or not ref.CAUSE[c] else
                (((pages+ref.PAGE[c]*4096)>>12)<<10)|0xc7]
            actual=self.record(c,n); raw=list(actual); actual[3]&=0x8000031888
            require(actual==gold,f'Exact trap record differs case{c}/{n}: {actual}')
            captured=[t for t in self.traps if t['case']==c]
            require(len(captured)>=n+1,'Record without captured handler CSR reads')
            require(captured[n]['values']==dict(enumerate(raw[:10])),'CSR reads disagree with stored record')
        if used==1:
            require(self.record(c,1)==[(1<<64)-1]*12,'Unused trap record modified')

    def row(self,r):
        require(set(r)==set(FIELDS) and None not in r.values(),'Malformed/truncated CSV row')
        cycle=int(r['cycle']); require(cycle>=self.last_cycle,'Cycle regressed'); self.last_cycle=cycle
        if r['event']!='retire': return
        order=int(r['order']); require(order==self.order+1,'Retirement sequence gap/duplicate'); self.order=order
        pc,insn,rd,value,trap=(int(r[k],16 if k in ('pc','insn','rd_wdata') else 10)
                              for k in ('pc','insn','rd','rd_wdata','trap'))
        require(pc!=self.s['trap_entry'],'Default trap handler executed')
        require(pc!=self.s['replay_mismatch'],'Software mismatch diagnostic reached')
        if pc==self.s['check']:
            self.calls+=1
            require(self.regs[10]==self.regs[11],f'Oracle check {self.calls} case{self.c}: '
                    f'got {self.regs[10]:#x}, want {self.regs[11]:#x}')
        if pc==self.s['mx_enter_s']:
            require(not self.active and len(self.finished)<8,'Overlapping/extra case entry')
            c=self.value('mx_current'); require(c==len(self.finished),'Skipped/reordered case')
            self.c=c; self.active=True; self.enter_calls=self.calls; self.action('enter')
            require([self.u64(self.s['mx_args']+8*i) for i in range(3)]==[
                ref.VA+ref.OFF[c],ref.STRIDE[c]&((1<<64)-1),self.s[ref.SITE[c]]],'Target args differ')
            require([self.mem.get(self.s['mx_mask']+c*16+i) for i in range(16)]==[
                ref.MASK[c] if c<6 or i==0 else 0 for i in range(16)],'Predicate bytes differ')
            require(self.u64(self.s['mx_pages']+16384+ref.PAGE[c]*8)==0,'Fault page initially mapped')
            self.capture=None
        if pc==self.s['mx_handler']:
            require(self.active,'Handler outside a case')
            self.capture={'case':self.c,'cycle':cycle,'values':{}}
            self.traps.append(self.capture); self.action('handler')
        if self.s['mx_trap']<=pc<self.s['main'] and insn & 127==0x73 and rd and (insn>>12)&7 in (2,3) and (insn>>15)&31==0:
            csr=insn>>20
            if csr in CSR:
                require(self.capture is not None,'CSR read outside handler')
                field=CSR[csr]; require(field not in self.capture['values'],'Duplicate handler CSR read')
                self.capture['values'][field]=value
        if insn & 127==0x73 and (insn>>12)&7 in (1,2,3,5,6,7):
            f=(insn>>12)&7; source=(insn>>15)&31
            writing=f in (1,5) or source!=0
            if writing and insn>>20==0x341 and self.active and self.capture and self.capture['values'].get(0) in (13,15):
                raise ValueError('Fault restart mepc overwritten')
            if writing and insn>>20==8:
                require(f in (1,5),'Unexpected vstart read-modify-write')
                self.vstart_write=source if f==5 else self.regs[source]
        if pc==self.s['mx_repair_sfence']:
            require(self.active and ref.CAUSE[self.c],'Unexpected repair')
            require(insn & 0xfe007fff==0x12000073 and
                    self.regs[(insn>>15)&31]==ref.VA+ref.PAGE[self.c]*4096,'Wrong addressed SFENCE')
            pte=(((self.s['mx_pages']+ref.PAGE[self.c]*4096)>>12)<<10)|0xc7
            require(self.u64(self.s['mx_pages']+16384+ref.PAGE[self.c]*8)==pte,'PTE not repaired before SFENCE')
            self.action('repair')
        if pc==self.s['mx_trap_mret']:
            require(self.capture is not None,'MRET without trap')
            if self.capture['values'].get(0) in (13,15):
                require(self.vstart_write==ref.START[self.c] and self.value('mx_restart')==ref.START[self.c],
                        'Restart vstart not restored')
                for i in range(ref.START[self.c]):
                    if ref.MASK[self.c]>>i&1:
                        off=ref.OFF[self.c]+i*ref.STRIDE[self.c]
                        a=self.s['mx_pages']+off
                        poison=(ref.seed(self.c,1,i) if self.c in (1,3,5) else ref.orig(self.c,off//2))^0x5b
                        require(self.mem.get(a)==poison&255 and self.mem.get(a+1)==poison>>8,'Prefix not poisoned before retry')
            self.action('retry' if self.capture['values'].get(0) in (13,15) else 'return_m')
        if pc in {self.s[n] for n in ref.SITE}:
            require(self.active and pc==self.s[ref.SITE[self.c]],'Wrong target site')
            expected=(0x55c07,0x55c27,0x09c55c07,0x09c55c27,0x09c55c07,0x09c55c27,0x01055c07,0x01055c07)[self.c]
            require(insn==expected,'Wrong target opcode')
            # CVA6 may expose a trapping retirement; it is not successful completion.
            if not trap: self.action('target')
        if pc==self.s['mx_younger_store']:
            self.action('younger')
        if pc==self.s['mx_ecall']:
            # Exception instructions may be absent from retirement CSV on some monitors.
            require(self.active,'ECALL outside case')
        if pc==self.s['mx_checkpoint']:
            c=self.c; phase=self.value('mx_phase')
            require(self.active and phase in (1,2),'Checkpoint outside case')
            require(self.value('mx_errors')==self.value('mx_unexpected')==0,'Checkpoint after software error')
            self.check_records(c,phase)
            leaf=self.u64(self.s['mx_pages']+16384+ref.PAGE[c]*8)
            require(leaf==(0 if phase==1 or not ref.CAUSE[c] else
                          (((self.s['mx_pages']+ref.PAGE[c]*4096)>>12)<<10)|0xc7),
                    'Actual denied/repaired leaf state differs')
            require(self.value('mx_count',c)==(2 if phase==2 and ref.CAUSE[c] else 1),'Trap count differs')
            require(self.value('mx_marker',c)==int(phase==2),'Marker ordering differs')
            if phase==2:
                require([self.u64(self.s['mx_post']+c*40+j*8) for j in range(5)]==[ref.VL[c],8,0,117,5],
                        'Raw post-target CSR mismatch')
            prior=self.points[-1]['cycle'] if self.points else 0
            if cycle-prior>(160000 if self.points else 350000): self.warnings.append('Checkpoint cycle gap exceeded')
            self.points.append(dict(case=c,phase=phase,cycle=cycle,checks=self.calls))
            self.action('fault_checkpoint' if phase==1 else 'final_checkpoint')
        write=scalar_store(r,self.regs)
        if write:
            a,v,width=write
            for i,b in enumerate(v.to_bytes(width,'little')): self.mem[a+i]=b
            if self.active and a==self.s['mx_pages']+16384+ref.PAGE[self.c]*8:
                require(ref.CAUSE[self.c] and self.actions[self.c][-1]=='fault_checkpoint','Premature/extra leaf repair')
                require(width==8 and v==(((self.s['mx_pages']+ref.PAGE[self.c]*4096)>>12)<<10)|0xc7,'Wrong repair PTE')
                self.action('pte')
            if a in (self.s['mx_errors'],self.s['mx_unexpected']): require(v==0,'Nonzero error state written')
            if self.s['mx_case_checks']<=a<self.s['mx_case_checks']+64 and v:
                c=(a-self.s['mx_case_checks'])//8
                require(self.active and c==self.c and width==8,'Wrong case completion store')
                require(v==COUNTS[c] and self.calls-self.enter_calls==v,'Missing/repeated case oracle checks')
                require(self.actions[c][-1]=='final_checkpoint','Counter before final checkpoint')
                self.finished.append(c); self.active=False; self.action('case_done')
            if a==0xd0000000:
                require(width==8 and v==0,'Nonzero/wrong CTRL completion'); self.exit.append(v)
        if rd and not trap: self.regs[rd]=value
        self.regs[0]=0

    def finish(self):
        require(self.finished==list(range(8)) and not self.active,'Incomplete case sequence')
        require([(p['case'],p['phase']) for p in self.points]==[
            (c,p) for c in range(8) for p in ((1,2) if ref.CAUSE[c] else (2,))],'Missing/reordered checkpoints')
        for c in range(8):
            gold=['enter']+(['handler','fault_checkpoint','pte','repair','retry'] if ref.CAUSE[c] else [])+[
                'target','younger','handler','return_m','final_checkpoint','case_done']
            require(self.actions[c]==gold,f'Case{c} ordering differs: {self.actions[c]}')
        require(len(self.traps)==13,'Wrong total trap count')
        require(self.calls==self.value('mx_checks')==6227,'Missing/extra oracle calls')
        require(self.value('mx_completed')==0x6d78737633390008,'Missing completion magic')
        require(self.exit==[0],'Missing/duplicate CTRL completion')
        if self.last_cycle>1350000: self.warnings.append('Total cycle diagnostic ceiling exceeded')
        return dict(status='EXTENDED8_CSV_ORACLE_PASS',cases=self.finished,checkpoints=self.points,
                    checks=self.calls,traps=self.traps,actions=self.actions,last_cycle=self.last_cycle,
                    performance_warnings=self.warnings,vector_data_evidence='unchanged on-device full scalar oracle')


def analyze(path,symbols):
    checker=Checker(symbols)
    try:
        with Path(path).open() as stream:
            reader=csv.DictReader(stream)
            require(reader.fieldnames==FIELDS,'Unexpected CSV header')
            for row in reader: checker.row(row)
        return checker.finish()
    except (ValueError,KeyError,TypeError) as error:
        return dict(status='EXTENDED8_CSV_NOT_PASS',error=str(error),case=checker.c,
                    completed_cases=checker.finished,checkpoints=checker.points,checks=checker.calls,
                    last_cycle=checker.last_cycle,actions=checker.actions,traps=checker.traps)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('csv',type=Path); p.add_argument('--symbols',type=Path,required=True)
    args=p.parse_args()
    result=analyze(args.csv,json.loads(args.symbols.read_text()))
    print(json.dumps(result,indent=2))
    sys.exit(result['status']!='EXTENDED8_CSV_ORACLE_PASS')
