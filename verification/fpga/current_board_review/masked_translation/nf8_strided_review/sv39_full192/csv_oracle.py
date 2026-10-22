#!/usr/bin/env python3
"""Incremental full192 grouped NF8 scalar RVFI oracle. It neither launches nor polls simulations."""
import csv
from pathlib import Path
import sys
sys.dont_write_bytecode=True
import reference as ref

require=ref.base.require
FIELDS='cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap'.split(',')
CSR={0x342:0,0x341:1,0x343:2,0x300:3,0x180:4,0xc20:5,0xc21:6,8:7,3:8,15:9}


def scalar_access(row,regs):
    insn=int(row['insn'],16)
    if insn&3!=3:
        d=ref.base.compressed_memory(insn)
        if d is None: return None
        kind,width,source=d['kind'],d['size'],d['register']
        address=(regs[d['base']]+d['offset'])&((1<<64)-1)
    else:
        op=insn&127
        if op not in (3,0x23): return None
        kind='read' if op==3 else 'write'
        f=(insn>>12)&7; width=1<<(f&3)
        source=(insn>>7)&31 if op==3 else (insn>>20)&31
        imm=insn>>20 if op==3 else ((insn>>25)<<5)|((insn>>7)&31)
        if imm&2048: imm-=4096
        address=(regs[(insn>>15)&31]+imm)&((1<<64)-1)
    require(kind in ('read','write') and width in (1,2,4,8),'Unknown scalar memory instruction')
    mask=int(row['mem_rmask' if kind=='read' else 'mem_wmask'],16)
    require(int(row['mem_addr'],16)==address,'Scalar memory address differs from instruction')
    require(mask==((1<<width)-1)<<(address%8),'Scalar RVFI byte mask differs')
    require(address%8+width<=8,'Unsupported scalar boundary crossing')
    if kind=='read':
        if not source: return None
        require(int(row['rd'])==source,'Scalar load rd differs')
        value=int(row['rd_wdata'],16)
    else:
        value=int(row['mem_wdata'],16)
        require(value&((1<<(width*8))-1)==regs[source]&((1<<(width*8))-1),'Scalar store source differs')
    return kind,address,value&((1<<(width*8))-1),width


class Checker:
    def __init__(self,symbols,cases,reference_status,ledger):
        self.s=symbols; self.cases=cases; self.gold=reference_status; self.ledger=ledger
        self.regs={i:0 for i in range(32)}; self.mem={}
        self.calls=0; self.c=None; self.active=False; self.finished=[]; self.points=[]
        self.actions={c['trial']:[] for c in cases}; self.traps=[]; self.capture=None
        self.cycle=-1; self.order=-1; self.enter_calls=0; self.exit=[]; self.vstart=None
        self.firsterror=None; self.csrs={}; self.restore_initial={}; self.compared_bytes=0

    def u64(self,a):
        require(all(a+i in self.mem for i in range(8)),f'Unobserved scalar state {a:#x}')
        return int.from_bytes(bytes(self.mem[a+i] for i in range(8)),'little')

    def value(self,name): return self.u64(self.s[name])
    def action(self,name):
        require(self.c is not None,'Action outside trial')
        self.actions[self.c['trial']].append(name)

    def invalidate(self,a,n):
        for p in range(a,a+n): self.mem.pop(p,None)

    def records(self,phase):
        c=self.c; fault=c['expected_cause'] is not None
        captures=[t for t in self.traps if t['trial']==c['trial']]
        used=2 if phase==2 and fault else 1
        require(len(captures)==used,'Unexpected handler count at checkpoint')
        for n in range(used):
            raw=[self.u64(self.s['na_records']+n*96+j*8) for j in range(12)]
            require(captures[n]['values']==dict(enumerate(raw[:10])),'Actual CSR reads differ from record')
            require(raw[3]&0x8000031888==0x800 and raw[3]&(1<<19)==0,'Not S-mode/MXR=0 trap')
            if n==0 and fault:
                require(raw[2] in [ref.VA+x['offset'] for x in c['allowed_fault_addresses']],
                        'tval outside permitted protected fields')

    def compare_call(self):
        trial=self.value('na_current'); phase=self.value('na_phase')
        kind,index,got,want=[self.regs[i] for i in range(10,14)]
        require(got==want,f'Firsterror trial={trial} phase={phase} kind={kind} index={index} got={got:#x} want={want:#x}')
        require(self.calls<len(self.ledger),'Extra oracle call')
        gold=self.ledger[self.calls]
        require([trial,phase,kind,index]==gold[:4],f'Oracle sequence differs at check {self.calls}')
        expected=gold[4]
        if isinstance(expected,dict):
            expected=self.s[expected['symbol']]
        # Restore compares against this DUT's captured initial CSR values, not Spike reset constants.
        if kind!=7:
            require(want==expected,f'Independent reference want differs at check {self.calls}')
        else:
            csr=(0x180,0x305,0x341,0x342,0x343,0x302,0x303,0x304,0xc20,0xc21,8,15,3,0x300)[index]
            require(csr in self.restore_initial,'Missing initial CSR for restoration')
            initial=self.restore_initial[csr]&~8 if csr==0x300 else self.restore_initial[csr]
            require(want==initial,'Restoration not bound to actual initial CSR')
        self.calls+=1

    def row(self,r):
        require(set(r)==set(FIELDS) and None not in r.values(),'Malformed/truncated CSV')
        cycle=int(r['cycle']); require(cycle>=self.cycle,'Cycle regressed'); self.cycle=cycle
        if r['event']!='retire': return
        order=int(r['order']); require(order==self.order+1,'Retirement gap/duplicate'); self.order=order
        pc,insn=int(r['pc'],16),int(r['insn'],16)
        rd,value,trap=int(r['rd']),int(r['rd_wdata'],16),int(r['trap'])
        require(pc not in (self.s['trap_entry'],self.s['replay_mismatch']),'Default trap/software firsterror reached')
        if pc==self.s['check']: self.compare_call()
        if pc==self.s['na_enter_s']:
            require(not self.active and len(self.finished)<len(self.cases),'Overlapping/extra trial entry')
            c=self.cases[len(self.finished)]
            require(self.value('na_current')==c['trial'],'Wrong original trial order')
            self.c=c; self.active=True; self.enter_calls=self.calls; self.capture=None
            self.action('enter')
            require([self.u64(self.s['na_args']+i*8) for i in range(2)]==
                    [ref.VA+c['base_offset'],self.s['replay_1' if c['store'] else 'replay_0']], 'Wrong base/target arguments')
            require(self.value('na_stride')==c['stride_bytes'],'Original positive stride differs')
            require([self.mem[self.s['na_mask']+i] for i in range(16)]==[c['mask']]*16,'Mask differs')
        if pc==self.s['na_handler']:
            require(self.active,'Handler outside trial')
            self.capture=dict(trial=self.c['trial'],cycle=cycle,values={})
            self.traps.append(self.capture); self.action('handler')
        if insn&127==0x73 and (insn>>12)&7:
            csr=insn>>20; f=(insn>>12)&7; source=(insn>>15)&31
            reading=rd and f in (2,3) and source==0
            writing=f in (1,5) or source!=0
            if reading:
                self.csrs[csr]=value
                if not self.finished and not self.active and csr not in self.restore_initial:
                    self.restore_initial[csr]=value
                if self.s['na_trap']<=pc<self.s['main'] and csr in CSR:
                    require(self.capture is not None,'CSR capture outside handler')
                    k=CSR[csr]; require(k not in self.capture['values'],'Duplicate trap CSR')
                    self.capture['values'][k]=value
                    if csr==0x342 and value==15:
                        for i in range(8):
                            if self.c['mask']>>i&1:
                                for off in self.c['field_offsets'][i]: self.invalidate(self.s['na_pages']+off,4)
            if writing and csr==8:
                require(f in (1,5),'Unexpected vstart read-modify-write')
                self.vstart=source if f==5 else self.regs[source]
            if writing and csr==0x341 and self.active and self.capture and self.capture['values'].get(0) in (13,15):
                raise ValueError('Fault retry overwrites original mepc')
        if pc==self.s['na_repair_sfence']:
            require(self.active and self.c['expected_cause'],'Unexpected repair')
            require(insn&0xfe007fff==0x12000073 and self.regs[(insn>>15)&31]==ref.VA+4096,'Wrong repair SFENCE')
            self.action('repair')
        if pc==self.s['na_retry_mret']:
            require(self.capture is not None,'MRET without handler')
            fault=self.capture['values'].get(0) in (13,15)
            if fault:
                start=self.c['expected_vstart']
                require(self.vstart==start and self.value('na_restart')==start,'Wrong restored vstart')
                for i in self.c['completed_active_prefix']:
                    for f,off in enumerate(self.c['field_offsets'][i]):
                        want=(ref.inp(f,i) if self.c['store'] else ref.orig(off))^0x5b
                        a=self.s['na_pages']+off
                        require(bytes(self.mem.get(a+j,0) for j in range(4))==want.to_bytes(4,'little'),'Prefix poison absent')
            self.action('retry' if fault else 'return_m')
        if pc in (self.s['fault_0_pc'],self.s['fault_1_pc']):
            require(self.active and pc==self.s['fault_1_pc' if self.c['store'] else 'fault_0_pc'],'Wrong target PC')
            require(insn==(0xe9c56c27 if self.c['store'] else 0xe9c56c07),'Wrong NF8 positive-stride instruction')
            if not trap: self.action('target')
        if insn&127==0x27:
            # Scalar RVFI cannot report vector data. Discard stale initialized bytes
            # until actual scalar oracle loads observe the stored vector results.
            if pc==self.s['fault_1_pc']:
                for i in range(8):
                    if self.c['mask']>>i&1:
                        for off in self.c['field_offsets'][i]: self.invalidate(self.s['na_pages']+off,4)
            else:
                a=self.regs[(insn>>15)&31]
                whole=((insn>>20)&31)==8
                self.invalidate(a,128 if whole else 64)
        if pc==self.s['na_younger_store']: self.action('younger')
        if pc==self.s['na_checkpoint']:
            require(self.active,'Checkpoint outside trial')
            phase=self.value('na_phase'); require(phase in (1,2),'Wrong phase')
            self.records(phase)
            want=ref.expected(self.s,self.c,phase)
            ref.check_state(self.mem,self.s,self.c,phase)
            self.compared_bytes+=len(want)
            gold=self.gold['checkpoints'][len(self.points)]
            require([self.c['trial'],phase,self.calls]==[gold['trial'],gold['phase'],gold['checks']], 'Checkpoint check-count differs')
            self.points.append(dict(trial=self.c['trial'],phase=phase,checks=self.calls,cycle=cycle,checked_bytes=len(want)))
            self.action('fault_checkpoint' if phase==1 else 'final_checkpoint')
        access=None if trap else scalar_access(r,self.regs)
        if access:
            kind,a,v,width=access
            for i,b in enumerate(v.to_bytes(width,'little')): self.mem[a+i]=b
            if kind=='write':
                if self.active and a==self.s['na_pages']+16392:
                    require(self.c['expected_cause'] and self.actions[self.c['trial']][-1]=='fault_checkpoint','Premature PTE repair')
                    require(v==(((self.s['na_pages']+4096)>>12)<<10)|0xc7,'Wrong repair PTE')
                    self.action('pte')
                if a in (self.s['na_errors'],self.s['na_unexpected']): require(v==0,'Nonzero firsterror state')
                if self.s['na_case_checks']<=a<self.s['na_case_checks']+32 and v:
                    n=(a-self.s['na_case_checks'])//8
                    require(self.active and n==len(self.finished) and width==8,'Invalid completion counter')
                    require(v==self.gold['case_checks'][n]==self.calls-self.enter_calls,'Case checks omitted/repeated')
                    require(self.actions[self.c['trial']][-1]=='final_checkpoint','Counter before final checkpoint')
                    self.finished.append(self.c['trial']); self.active=False; self.action('case_done')
                if a==0xd0000000:
                    require(width==8 and v==0,'CTRL failure'); self.exit.append(v)
        if rd and not trap: self.regs[rd]=value
        self.regs[0]=0

    def finish(self):
        require(self.finished==[c['trial'] for c in self.cases] and not self.active,'Incomplete original trial group')
        for c in self.cases:
            gold=['enter']+(['handler','fault_checkpoint','pte','repair','retry'] if c['expected_cause'] else [])+[
                'target','younger','handler','return_m','final_checkpoint','case_done']
            require(self.actions[c['trial']]==gold,'Request/fault/retry/completion ordering differs')
        require(len(self.points)==len(self.gold['checkpoints']),'Missing checkpoints')
        require(self.calls==len(self.ledger)==self.gold['checks']==self.value('na_checks'),'Incomplete check sequence')
        require(self.value('na_completed')==ref.DONE and self.value('na_cases_done')==len(self.cases),'Missing full-group magic/count')
        require(self.value('na_errors')==self.value('na_unexpected')==0 and self.exit==[0],'Error or missing CTRL completion')
        return dict(status='NF8_CSV_ORACLE_PASS',trials=self.finished,checks=self.calls,checkpoints=self.points,
                    traps=self.traps,actions=self.actions,last_cycle=self.cycle,observed_memory_bytes=self.compared_bytes)

    def failure(self,error):
        return dict(status='NF8_CSV_NOT_PASS',error=str(error),trial=self.c['trial'] if self.c else None,
                    phase=self.mem.get(self.s['na_phase']),checks=self.calls,completed_trials=self.finished,
                    checkpoints=self.points,last_cycle=self.cycle,last_order=self.order)


def analyze(path,symbols,cases,status,ledger):
    checker=Checker(symbols,cases,status,ledger)
    try:
        with Path(path).open() as stream:
            reader=csv.DictReader(stream)
            require(reader.fieldnames==FIELDS,'Wrong CSV header')
            for row in reader: checker.row(row)
        return checker.finish()
    except (ValueError,KeyError,TypeError) as error:
        return checker.failure(error)
