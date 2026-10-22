#!/usr/bin/env python3
"""Offline NF2 CSV observer. Never starts or polls a simulator."""
import csv
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import reference as ref

FIELDS = 'cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap'.split(',')
CSR = {0x342:0,0x341:1,0x343:2,0x300:3,0x180:4,0xc20:5,0xc21:6,8:7,3:8,15:9}
COUNTS = (756,758,756,758)
require = ref.base.require


def scalar_store(row,regs):
    """CVA6 RVFI: shifted byte enable, unshifted source register data."""
    insn,addr,mask,value = (int(row[k],16) for k in ('insn','mem_addr','mem_wmask','mem_wdata'))
    if not mask: return None
    if insn&3 != 3:
        d=ref.base.compressed_memory(insn)
        require(d is not None and d['kind']=='write','Unknown compressed store')
        width,source=d['size'],d['register']
        require(addr==(regs[d['base']]+d['offset'])&((1<<64)-1),'Compressed store address differs')
    elif insn&127 == 0x23:
        width,source=1<<((insn>>12)&7),(insn>>20)&31
        imm=((insn>>25)<<5)|((insn>>7)&31)
        if imm&2048: imm-=4096
        require(addr==(regs[(insn>>15)&31]+imm)&((1<<64)-1),'Scalar store address differs')
    else:
        raise ValueError('Unexpected non-scalar RVFI memory write')
    require(width in (1,2,4,8) and addr%8+width<=8,'Unsupported store width/alignment')
    require(mask==((1<<width)-1)<<(addr%8),'Store byte mask differs')
    bits=(1<<(8*width))-1
    require(value&bits==regs[source]&bits,'Store value differs from source register')
    return addr,value&bits,width


class Checker:
    def __init__(self,s):
        self.s=s; self.regs={i:0 for i in range(32)}; self.mem={}
        self.c=-1; self.active=False; self.last_cycle=-1; self.order=-1
        self.calls=0; self.enter_calls=0; self.finished=[]; self.points=[]
        self.actions=[[] for _ in range(4)]; self.traps=[]; self.capture=None
        self.exit=[]; self.vstart_write=None; self.trapping_targets=[]
        self.alternate=[False]*4

    def u64(self,a):
        require(all(a+i in self.mem for i in range(8)),f'Missing scalar state {a:#x}')
        return int.from_bytes(bytes(self.mem[a+i] for i in range(8)),'little')

    def value(self,name,index=0): return self.u64(self.s[name]+index*8)

    def action(self,name):
        require(self.active and 0<=self.c<4,'Action outside active case')
        self.actions[self.c].append(name)

    def check_records(self,c,phase):
        pages=self.s['mx_pages']; captured=[t for t in self.traps if t['case']==c]
        require(len(captured)==phase,'Handler count differs at checkpoint')
        for n in range(phase):
            fault=n==0
            actual=[self.u64(self.s['mx_records']+192*c+96*n+8*j) for j in range(12)]
            require(captured[n]['values']==dict(enumerate(actual[:10])),'CSR reads disagree with stored record')
            gold=[(15 if c%2 else 13) if fault else 9,self.s[ref.SITE[c]] if fault else self.s['mx_ecall'],
                  ref.VA+ref.OFF[c]+20+(2 if c>=2 else 0) if fault else 0,0x800,
                  (8<<60)|((pages+8192)>>12),8,8,5 if fault else 0,117,5,0 if fault else 1,
                  0 if fault else ((pages+4096)>>12<<10)|0xc7]
            if fault and c<2 and actual[2]==ref.VA+ref.OFF[c]+22:
                gold[2]=actual[2]; self.alternate[c]=True
            masked=list(actual); masked[3]&=0x8000031888
            require(masked==gold,f'Exact trap record differs case{c}/{n}: {actual}')
        if phase==1:
            require([self.u64(self.s['mx_records']+192*c+96+8*j) for j in range(12)]==[(1<<64)-1]*12,
                    'Unused second trap record changed')

    def row(self,r):
        require(set(r)==set(FIELDS) and None not in r.values(),'Malformed/truncated CSV row')
        cycle=int(r['cycle']); require(cycle>=self.last_cycle,'Cycle regressed'); self.last_cycle=cycle
        if r['event']!='retire': return
        order=int(r['order']); require(order==self.order+1,'Retirement gap/duplicate'); self.order=order
        pc,insn,rd,value,trap=(int(r[k],16 if k in ('pc','insn','rd_wdata') else 10)
                              for k in ('pc','insn','rd','rd_wdata','trap'))
        require(pc!=self.s['trap_entry'],'Default trap handler executed')
        require(pc!=self.s['replay_mismatch'],'Firmware mismatch diagnostic reached')
        if pc==self.s['check']:
            self.calls+=1
            require(self.regs[10]==self.regs[11],f'Firmware oracle mismatch case{self.c} check{self.calls}: '
                    f'{self.regs[10]:#x} != {self.regs[11]:#x}')
        if pc==self.s['mx_enter_s']:
            require(not self.active and len(self.finished)<4,'Overlapping/extra case entry')
            c=self.value('mx_current'); require(c==len(self.finished),'Skipped/reordered case')
            self.c=c; self.active=True; self.enter_calls=self.calls; self.action('enter')
            require([self.u64(self.s['mx_args']+8*i) for i in range(2)]==[ref.VA+ref.OFF[c],self.s[ref.SITE[c]]],
                    'Target address/site differs')
            require([self.mem.get(self.s['mx_mask']+16*c+i) for i in range(16)]==[0x24]*16,'Mask bytes differ')
            require(self.u64(self.s['mx_pages']+16384+8)==0,'Protected page initially mapped')
            self.capture=None
        if pc==self.s['mx_handler']:
            require(self.active,'Handler outside active case')
            self.capture=dict(case=self.c,cycle=cycle,values={})
            self.traps.append(self.capture); self.action('handler')
        if self.s['mx_trap']<=pc<self.s['main'] and insn&127==0x73 and rd and (insn>>12)&7 in (2,3) and (insn>>15)&31==0:
            csr=insn>>20
            if csr in CSR:
                require(self.capture is not None,'CSR read without handler')
                field=CSR[csr]; require(field not in self.capture['values'],'Repeated handler CSR read')
                self.capture['values'][field]=value
        if insn&127==0x73 and (insn>>12)&7 in (1,2,3,5,6,7):
            f=(insn>>12)&7; source=(insn>>15)&31; writing=f in (1,5) or source!=0
            if writing and insn>>20==0x341 and self.active and self.capture and self.capture['values'].get(0) in (13,15):
                raise ValueError('Fault restart mepc overwritten')
            if writing and insn>>20==8:
                require(f in (1,5),'Unexpected vstart read-modify-write')
                self.vstart_write=source if f==5 else self.regs[source]
        if pc==self.s['mx_repair_sfence']:
            require(self.active and insn&0xfe007fff==0x12000073 and self.regs[(insn>>15)&31]==ref.VA+4096,
                    'Wrong addressed repair SFENCE')
            require(self.u64(self.s['mx_pages']+16392)==((self.s['mx_pages']+4096)>>12<<10)|0xc7,'Leaf not repaired')
            self.action('repair')
        if pc==self.s['mx_trap_mret']:
            require(self.capture is not None,'MRET without handler')
            fault=self.capture['values'].get(0) in (13,15)
            if fault:
                require(self.vstart_write==self.value('mx_restart')==5,'Retry vstart not5')
                for field in (0,1):
                    off=ref.OFF[self.c]+8+2*field; a=self.s['mx_pages']+off
                    poison=(ref.seed(self.c,field+1,2) if self.c%2 else ref.orig(off//2))^0x5b
                    require(self.mem.get(a)==poison&255 and self.mem.get(a+1)==poison>>8,'Both-field prefix poison missing')
            self.action('retry' if fault else 'return_m')
        if pc in (self.s['mx_segment_load'],self.s['mx_segment_store']):
            require(self.active and pc==self.s[ref.SITE[self.c]],'Wrong NF2 target site')
            require(insn==(0x20055c27 if self.c%2 else 0x20055c07),'Original NF2 opcode changed')
            if trap: self.trapping_targets.append(dict(case=self.c,pc=hex(pc),cycle=cycle))
            else: self.action('target')
        if pc==self.s['mx_younger_store']: self.action('younger')
        if pc==self.s['mx_checkpoint']:
            c=self.c; phase=self.value('mx_phase')
            require(self.active and phase in (1,2),'Checkpoint outside case')
            require(self.value('mx_errors')==self.value('mx_unexpected')==0,'Checkpoint with firmware error')
            self.check_records(c,phase)
            expected_checks=(300 if c%2==0 else 302) if phase==1 else COUNTS[c]
            require(self.calls-self.enter_calls==expected_checks-self.alternate[c],'Checkpoint oracle-call count differs')
            require(self.value('mx_count',c)==phase and self.value('mx_marker',c)==phase-1,'Trap/marker ordering differs')
            leaf=0 if phase==1 else ((self.s['mx_pages']+4096)>>12<<10)|0xc7
            require(self.u64(self.s['mx_pages']+16392)==leaf,'Denied/repaired PTE differs')
            if phase==2:
                require([self.u64(self.s['mx_post']+40*c+8*j) for j in range(5)]==[8,8,0,117,5],'Post-target CSR differs')
            self.points.append(dict(case=c,phase=phase,cycle=cycle,checks=self.calls))
            self.action('fault_checkpoint' if phase==1 else 'final_checkpoint')
        write=scalar_store(r,self.regs)
        if write:
            a,v,width=write
            for i,b in enumerate(v.to_bytes(width,'little')): self.mem[a+i]=b
            if self.active and a==self.s['mx_pages']+16392:
                require(self.actions[self.c][-1]=='fault_checkpoint','Premature/extra PTE repair')
                require(width==8 and v==((self.s['mx_pages']+4096)>>12<<10)|0xc7,'Wrong repaired leaf')
                self.action('pte')
            if a in (self.s['mx_errors'],self.s['mx_unexpected']): require(v==0,'Nonzero error state written')
            if self.s['mx_case_checks']<=a<self.s['mx_case_checks']+32 and v:
                c=(a-self.s['mx_case_checks'])//8
                require(self.active and c==self.c and width==8,'Wrong case-completion store')
                require(v==COUNTS[c]-self.alternate[c] and self.calls-self.enter_calls==v,'Case check count differs')
                require(self.actions[c][-1]=='final_checkpoint','Completion before final checkpoint')
                self.action('case_done'); self.finished.append(c); self.active=False
            if a==0xd0000000:
                require(width==8 and v==0,'Wrong/nonzero CTRL completion'); self.exit.append(v)
        if rd and not trap: self.regs[rd]=value
        self.regs[0]=0

    def finish(self):
        require(self.finished==list(range(4)) and not self.active,'Incomplete four-case sequence')
        require([(p['case'],p['phase']) for p in self.points]==[(c,p) for c in range(4) for p in (1,2)],'Checkpoint order differs')
        for c in range(4):
            require(self.actions[c]==['enter','handler','fault_checkpoint','pte','repair','retry','target','younger',
                                     'handler','return_m','final_checkpoint','case_done'],f'Case{c} event order differs')
        require(len(self.traps)==8,'Wrong total handler count')
        require(self.calls==self.value('mx_checks')==4133-sum(self.alternate),'Total firmware oracle count differs')
        require(self.value('mx_completed')==ref.DONE,'Missing completion magic')
        require(self.exit==[0],'Missing/duplicate CTRL completion')
        return dict(status='NF2_CSV_ORACLE_PASS',cases=self.finished,checkpoints=self.points,checks=self.calls,
                    traps=self.traps,actions=self.actions,last_cycle=self.last_cycle,
                    alternate_protected_field=self.alternate,trapping_target_retirements=self.trapping_targets,
                    vector_data_evidence='Pinned firmware full scalar oracle; RVFI CSV does not expose vector writes')


def analyze(path,symbols):
    checker=Checker(symbols)
    try:
        with Path(path).open() as stream:
            reader=csv.DictReader(stream); require(reader.fieldnames==FIELDS,'Wrong CSV header')
            for row in reader: checker.row(row)
        return checker.finish()
    except (ValueError,KeyError,TypeError,OSError) as error:
        return dict(status='NF2_CSV_NOT_PASS',error=str(error),case=checker.c,completed_cases=checker.finished,
                    checkpoints=checker.points,checks=checker.calls,last_cycle=checker.last_cycle,
                    actions=checker.actions,traps=checker.traps)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('csv',type=Path); p.add_argument('--symbols',type=Path,required=True)
    args=p.parse_args(); result=analyze(args.csv,json.loads(args.symbols.read_text()))
    print(json.dumps(result,indent=2)); sys.exit(result['status']!='NF2_CSV_ORACLE_PASS')
