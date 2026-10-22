"""Actual-ELF bounded ABI spills, following Aquinas' main+handler recovery.

Unknown values enter only at exact first caller spills, never business stores.
No reset-zero assumption and no permission inferred from arbitrary trace PCs.
"""
import hashlib
import csv
from pathlib import Path
import source_owners as owners
import csv_check as core
import observer as o
need=o.require
CALLEE=(8,9,18,19,20,21,22,23,24,25,26,27)
HANDLER=(1,5,6,7,28,29,30,31,10,11,12,13,14,15,16,17)
OPAQUE_HANDLER=(7,28,29,30,31)

def frame_size(insn):
    if insn&0xef83==0x6101:
        imm=((insn>>12)&1)<<9|((insn>>6)&1)<<4|((insn>>5)&1)<<6|((insn>>3)&3)<<7|((insn>>2)&1)<<5
        if imm&512:imm-=1024
    else:
        need(insn&0xfffff==0x10113,'Only addi sp,sp or c.addi16sp frame')
        imm=insn>>20
        if imm&2048:imm-=4096
    need(imm<0 and imm%16==0 and -imm<=512,'Bounded ABI frame')
    return -imm

def profile(spec):
    code={int(k):v for k,v in spec['code'].items()};s=spec['symbols']
    need(hashlib.sha256(Path(spec['elf']).read_bytes()).hexdigest()==spec['elf_sha256'],'Actual SoC ELF identity')
    actual=o.elf_bytes(spec['elf']);pcs=o.window(code,s['main'],14)
    size=frame_size(code[pcs[0]])
    slots=[]
    for i,pc in enumerate(pcs[1:]):
        d=core.memory_op(code[pc]);reg=(1,*CALLEE)[i]
        need(d and d['kind']=='write' and d['base']==2 and d['register']==reg and d['size']==8
             and d['offset']==size-8*(i+1),'Exact main ra/callee spill sequence')
        slots.append(dict(pc=pc,register=reg,offset=d['offset']))
    following=pcs[-1]+(2 if code[pcs[-1]]&3!=3 else 4)
    need(code[following]&0xfffff07f==0x30002073,'First following actual mstatus read')
    hp=o.window(code,s['fx_handler'],17)
    need(code[hp[0]]==0xf8010113,'Exact handler frame128')
    for i,(pc,reg) in enumerate(zip(hp[1:],HANDLER)):
        need(core.memory_op(code[pc])==dict(kind='write',size=8,base=2,register=reg,offset=i*8,signed=False),'Exact handler stores')
    rp=o.window(code,s['fx_trap_mret']-68,16)
    for i,(pc,reg) in enumerate(zip(rp,HANDLER)):
        need(core.memory_op(code[pc])==dict(kind='read',size=8,base=2,register=reg,offset=i*8,signed=True),'Exact handler restores')
    need(code[s['fx_trap_mret']-4]==0x08010113 and code[s['fx_trap_mret']]==0x30200073,'Handler SP/MRET')
    for pc in pcs+hp+rp+[following,s['fx_trap_mret']-4,s['fx_trap_mret']]:
        n=2 if code[pc]&3!=3 else 4
        need(int.from_bytes(bytes(actual[pc+i] for i in range(n)),'little')==code[pc],'ELF instruction bytes')
    return dict(main_pcs=pcs,main_codes=[code[p] for p in pcs],frame_size=size,main_slots=slots,
                following_pc=following,handler_pcs=hp,handler_codes=[code[p] for p in hp],restore_pcs=rp,
                allowed_main_opaque=list(CALLEE),allowed_handler_opaque=list(OPAQUE_HANDLER))

class Checker(owners.Checker):
    def __init__(self,spec):
        need(spec['abi_profile']==profile(spec),'Exact independently extracted ABI profile')
        super().__init__(spec)
        self.abi=spec['abi_profile'];self.mi=None;self.hi=None;self.current_main=None;self.current_handler=None
        self.frame_sp=None;self.trap_sp=None;self.previous_pc=None;self.ecall=None
        self.main_opaque=[];self.handler_opaque=[];self.handler_saved={};self.handler_restored=[]

    def row(self,r):
        me=he=False
        if r['event']=='retire':
            pc=int(r['pc'],16);insn=int(r['insn'],16)
            if pc==self.s['main']:
                need(self.mi is None and not self.started and self.regs.get(2)==self.s['__stack_top'],'Main once, actual startup SP')
                self.frame_sp=self.regs[2]-self.abi['frame_size'];self.mi=0
                need(self.frame_sp%16==0 and self.frame_sp>self.s['__bss_end'],'Main frame outside business memory')
            if self.mi is not None and self.mi<14:
                i=self.mi
                need(pc==self.abi['main_pcs'][i] and insn==self.abi['main_codes'][i] and not int(r['trap']),'Contiguous exact main ABI entry')
                if i==0:
                    need(int(r['rd'])==2 and int(r['rd_wdata'],16)==self.frame_sp and int(r['mem_rmask'],16)==int(r['mem_wmask'],16)==0,'Main SP allocation')
                else:self.spill_row(r,self.frame_sp+self.abi['main_slots'][i-1]['offset'],self.frame_sp)
                self.current_main=i;me=True
            elif pc in self.abi['main_pcs']:raise ValueError('Main prologue replay')
            if pc==self.s['fx_ecall']:
                need(self.ecall is None and self.step==11 and self.cap==3 and self.mi==14
                     and self.actions==['checkpoint0','enter_s','helper','younger'] and insn==0x73 and int(r['trap'])==1
                     and self.u64('fx_return')==self.cfg['returned_vl'] and self.u64('fx_marker')==1,'Actual completion ecall after full helper')
                need((self.csrs.get(0xc20),self.csrs.get(0xc21),self.csrs.get(8))==(8,self.cfg['vtype'],0)
                     and self.regs.get(2)==self.frame_sp-16,'Actual completion vector context/SP')
                self.ecall=dict(pc=pc,cycle=int(r['cycle']),sp=self.regs[2])
            if pc==self.s['fx_handler']:
                need(self.ecall is not None and self.previous_pc==self.s['fx_ecall'] and self.hi is None
                     and self.regs.get(2)==self.ecall['sp'],'One actual completion-to-handler transition')
                self.trap_sp=self.regs[2]-128;self.hi=0
                need(self.trap_sp%16==0 and self.trap_sp>self.s['__bss_end'],'Isolated trap frame')
            if self.hi is not None and self.hi<17:
                i=self.hi
                need(pc==self.abi['handler_pcs'][i] and insn==self.abi['handler_codes'][i] and not int(r['trap']),'Contiguous handler ABI entry')
                if i==0:
                    need(int(r['rd'])==2 and int(r['rd_wdata'],16)==self.trap_sp and int(r['mem_rmask'],16)==int(r['mem_wmask'],16)==0,'Handler SP allocation')
                else:self.spill_row(r,self.trap_sp+8*(i-1),self.trap_sp)
                self.current_handler=i;he=True
            elif pc in self.abi['handler_pcs']:raise ValueError('Handler entry replay')
            if pc in self.abi['restore_pcs']:
                i=len(self.handler_restored);need(i<16 and pc==self.abi['restore_pcs'][i] and self.hi==17,'Ordered handler restore')
                reg=HANDLER[i]
                need(self.regs.get(2)==self.trap_sp and int(r['rd'])==reg and int(r['rd_wdata'],16)==self.handler_saved.get(reg)
                     and int(r['mem_rmask'],16)==255 and int(r['mem_wmask'],16)==0 and int(r['mem_addr'],16)==self.trap_sp+8*i
                     and not int(r['trap']),'Actual handler restored value/address/BE')
                self.handler_restored.append(reg)
            if pc==self.s['fx_trap_mret']:
                need(self.handler_restored==list(HANDLER) and self.regs.get(2)==self.ecall['sp'],'Full caller restore before MRET')
        super().row(r)
        if me:self.mi+=1;self.current_main=None
        if he:self.hi+=1;self.current_handler=None
        if r['event']=='retire':self.previous_pc=int(r['pc'],16)

    def spill_row(self,r,address,sp):
        need(self.regs.get(2)==sp and int(r['rd'])==0 and int(r['mem_addr'],16)==address and address%8==0
             and int(r['mem_wmask'],16)==255 and int(r['mem_rmask'],16)==0 and not int(r['trap']),'Actual complete ABI spill')

    def scalar(self,r,pc,insn,trap):
        if int(r['mem_wmask'],16):
            d=core.memory_op(insn);need(d is not None and d['base'] in self.regs,'Known scalar store address')
            reg=d['register'];value=int(r['mem_wdata'],16)
            need(0<=value<=o.MASK64,'RVFI store value width')
            if reg not in self.regs:
                if self.current_main is not None:
                    i=self.current_main
                    need(2<=i<14 and self.mi==i and pc==self.abi['main_pcs'][i] and reg==CALLEE[i-2]
                         and d['base']==2 and d['size']==8 and d['offset']==self.abi['main_slots'][i-1]['offset']
                         and reg not in self.main_opaque,'Only first exact main callee spill')
                    self.spill_row(r,self.frame_sp+d['offset'],self.frame_sp);self.main_opaque.append(reg)
                elif self.current_handler is not None:
                    i=self.current_handler
                    need(i>0 and self.hi==i and pc==self.abi['handler_pcs'][i] and reg==HANDLER[i-1]
                         and reg in OPAQUE_HANDLER and reg not in self.handler_opaque and self.ecall is not None
                         and d['base']==2 and d['size']==8 and d['offset']==8*(i-1),'Only first exact handler temporary spill')
                    self.spill_row(r,self.trap_sp+d['offset'],self.trap_sp);self.handler_opaque.append(reg)
                else:raise ValueError('Unknown business/nonentry store register')
                self.regs[reg]=value
            if self.current_handler is not None and self.current_handler>0:
                need(reg==HANDLER[self.current_handler-1] and reg not in self.handler_saved,'Unique handler saved register')
                self.handler_saved[reg]=value
        super().scalar(r,pc,insn,trap)

    def finish(self):
        result=super().finish()
        need(self.mi==14 and self.hi==17 and self.main_opaque==list(CALLEE)
             and self.handler_restored==list(HANDLER),'Full actual ABI entry/restore')
        need(set(self.handler_opaque)<=set(OPAQUE_HANDLER),'Narrow handler opaque scope')
        result.update(opaque_main_registers=self.main_opaque,opaque_handler_registers=self.handler_opaque,
                      handler_saved=self.handler_saved,handler_restored=self.handler_restored,completion_ecall=self.ecall,
                      abi_policy='exact_ELF_main_and_handler_first_spills_no_reset_defaults')
        return result

def analyze(path,spec):
    q=Checker(spec)
    current=None
    with Path(path).open() as f:
        rows=csv.DictReader(f);need(rows.fieldnames==core.FIELDS,'Actual CSV header')
        for number,r in enumerate(rows,1):
            current=dict(row=number,**{k:r.get(k) for k in ('cycle','event','pc','insn')})
            try:q.row(r)
            except (ValueError,KeyError,TypeError,IndexError,OSError) as error:
                import diagnostics
                result=diagnostics.context(error,'soc_full_oracle_owner_abi',current,f'e{spec["sew"]}_sc{spec["scenario"]}')
                result.update(status='NOT_ACCEPTED_FIRST_CHECKER_FAILURE',helper_step=q.step,actions=q.actions)
                return result
    return q.finish()
