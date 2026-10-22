"""Exact completion-ecall save/restore of five otherwise undefined temporaries."""
import successor as base
need,old,o=base.need,base.old,base.o
HANDLER_REGS=(1,5,6,7,28,29,30,31,10,11,12,13,14,15,16,17)
OPAQUE=(7,28,29,30,31)

class Checker(base.Checker):
    def __init__(self,spec):
        super().__init__(spec)
        self.trap_pcs=o.window(self.code,self.s['fx_handler'],17)
        self.trap_codes=[0xf8010113]
        for i,reg in enumerate(HANDLER_REGS):
            off=i*8
            self.trap_codes.append((off>>5)<<25 | reg<<20 | 2<<15 | 3<<12 | (off&31)<<7 | 0x23)
        self.restore_pcs=o.window(self.code,self.s['fx_trap_mret']-68,16)
        actual=o.elf_bytes(spec['elf'])
        expected=dict(zip(self.trap_pcs,self.trap_codes))
        expected.update({pc:(i*8)<<20 | 2<<15 | 3<<12 | reg<<7 | 3
                         for i,(pc,reg) in enumerate(zip(self.restore_pcs,HANDLER_REGS))})
        expected[self.s['fx_trap_mret']-4]=0x08010113
        expected[self.s['fx_trap_mret']]=0x30200073
        for pc,insn in expected.items():
            need(self.code[pc]==insn and int.from_bytes(bytes(actual[pc+i] for i in range(4)),'little')==insn,
                 'Actual hashbound handler save/restore encoding')
        self.trap_index=None
        self.current_trap_entry=None
        self.trap_sp=None
        self.ecall_context=None
        self.last_retire_pc=None
        self.trap_saved={}
        self.handler_opaque=[]
        self.handler_restored=[]

    def row(self,r):
        in_entry=False
        if r['event']=='retire':
            pc=int(r['pc'],16)
            if pc in self.entry_pcs[1:]:
                i=self.entry_pcs.index(pc)
                need(int(r['mem_wmask'],16)==255 and int(r['mem_rmask'],16)==0
                     and int(r['mem_addr'],16)==self.regs.get(2,-1)+224-8*i,
                     'Every exact main prologue spill must be present')
            if pc==self.s['fx_ecall']:
                need(self.ecall_context is None and self.step==11 and self.cap==3
                     and self.actions==['checkpoint0','enter_s','helper','younger']
                     and int(r['insn'],16)==0x73 and int(r['trap'])==1
                     and self.u64('fx_return')==self.cfg['returned_vl'] and self.u64('fx_marker')==1,
                     'Real completion ecall after full source helper and younger marker')
                need((self.csrs.get(0xc20),self.csrs.get(0xc21),self.csrs.get(8))==(8,24,0),
                     'Completion VL8 distinct from FOF returned VL4')
                need(2 in self.regs and self.regs[2]==self.frame_sp-16,'Real fx_enter_s frame')
                self.ecall_context=dict(pc=pc,cycle=int(r['cycle']),sp=self.regs[2],
                                         returned_vl=self.cfg['returned_vl'],post_helper_vl=8)
            if pc==self.s['fx_handler']:
                need(self.ecall_context is not None and self.last_retire_pc==self.s['fx_ecall']
                     and self.trap_index is None and not self.handler and self.entry_index==14,
                     'Single actual ecall-to-handler entry')
                need(self.regs.get(2)==self.ecall_context['sp'],'Actual pretrap SP')
                self.trap_sp=self.regs[2]-128
                need(self.trap_sp%16==0 and self.trap_sp>self.s['__bss_end'],'Isolated actual trap frame')
                self.trap_index=0
            if self.trap_index is not None and self.trap_index<17:
                i=self.trap_index
                need(pc==self.trap_pcs[i] and int(r['insn'],16)==self.trap_codes[i] and int(r['trap'])==0,
                     'Exact contiguous17 handler entry')
                if i==0:
                    need(int(r['rd'])==2 and int(r['rd_wdata'],16)==self.trap_sp
                         and int(r['mem_rmask'],16)==int(r['mem_wmask'],16)==0,'Actual trap frame allocation')
                else:
                    need(self.regs.get(2)==self.trap_sp and int(r['rd'])==0
                         and int(r['mem_wmask'],16)==255 and int(r['mem_rmask'],16)==0
                         and int(r['mem_addr'],16)==self.trap_sp+8*(i-1),'Exact actual handler spill address/BE')
                self.current_trap_entry=i;in_entry=True
            elif pc in self.trap_pcs:
                raise ValueError('Handler entry replay')
            if pc in self.restore_pcs:
                i=len(self.handler_restored)
                need(i<16 and pc==self.restore_pcs[i] and self.trap_index==17
                     and self.regs.get(2)==self.trap_sp,'Exact handler restore order/frame')
                reg=HANDLER_REGS[i]
                need(int(r['rd'])==reg and int(r['rd_wdata'],16)==self.trap_saved.get(reg)
                     and int(r['mem_rmask'],16)==255 and int(r['mem_wmask'],16)==0
                     and int(r['mem_addr'],16)==self.trap_sp+8*i and int(r['trap'])==0,
                     'Actual restored caller value/address/BE')
                self.handler_restored.append(reg)
            if pc==self.s['fx_trap_mret']:
                need(self.handler_restored==list(HANDLER_REGS) and self.regs.get(2)==self.ecall_context['sp'],
                     'All16 caller registers and SP restored before MRET')
        super().row(r)
        if in_entry:self.trap_index+=1;self.current_trap_entry=None
        if r['event']=='retire':self.last_retire_pc=int(r['pc'],16)

    def scalar(self,r,pc,insn,trap):
        i=self.current_trap_entry
        if i is not None and i>0:
            d=old.memory_op(insn);reg=HANDLER_REGS[i-1]
            need(d==dict(kind='write',size=8,base=2,register=reg,offset=8*(i-1),signed=False),
                 'Exact handler sd decoder')
            need(pc==self.trap_pcs[i] and insn==self.trap_codes[i] and self.trap_index==i
                 and self.ecall_context is not None and self.regs.get(2)==self.trap_sp
                 and int(r['mem_addr'],16)==self.trap_sp+8*(i-1)
                 and int(r['mem_wmask'],16)==255 and int(r['mem_rmask'],16)==0
                 and int(r['rd'])==0 and not trap,'Narrow actual handler capture context')
            value=int(r['mem_wdata'],16)
            need(0<=value<=o.MASK64 and reg not in self.trap_saved,'One actual saved word per register')
            if reg not in self.regs:
                need(reg in OPAQUE and reg not in self.handler_opaque,'Only five first opaque handler temporaries')
                self.regs[reg]=value
                self.handler_opaque.append(reg)
            self.trap_saved[reg]=value
        super().scalar(r,pc,insn,trap)

    def finish(self):
        result=super().finish()
        need(self.trap_index==17 and self.handler_opaque==list(OPAQUE)
             and self.handler_restored==list(HANDLER_REGS),'Full exact trap entry and restore')
        result.update(successor='exact_main_and_completion_handler_opaque_spills01',
                      completion_ecall_context=self.ecall_context,handler_prologue_instructions=17,
                      handler_opaque_registers=self.handler_opaque,
                      handler_saved_values=self.trap_saved,handler_restored_registers=self.handler_restored)
        return result
