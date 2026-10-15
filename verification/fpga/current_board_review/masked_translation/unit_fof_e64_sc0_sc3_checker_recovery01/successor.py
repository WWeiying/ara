"""Exact main caller-register spills only; all sealed business checks inherited."""
import ast
import importlib.util
from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
WORKER=HERE.parent/'unit_fof_e64_sc0_sc3_vcs_m9_plan01'
sys.path.insert(0,str(WORKER))
import checker as frozen
old=frozen.csv_source
o=frozen.source
need=frozen.require
ENTRY=(0x7115,0xed86,0xe9a2,0xe5a6,0xe1ca,0xfd4e,0xf952,
       0xf556,0xf15a,0xed5e,0xe962,0xe566,0xe16a,0xfcee)
CALLEE=(8,9,18,19,20,21,22,23,24,25,26,27)

def symbol_keys():
    tree=ast.parse(Path(old.__file__).read_text())
    return sorted({n.slice.value for n in ast.walk(tree)
        if isinstance(n,ast.Subscript) and isinstance(n.value,ast.Attribute)
        and isinstance(n.value.value,ast.Name) and n.value.value.id=='self'
        and n.value.attr=='s' and isinstance(n.slice,ast.Constant)
        and isinstance(n.slice.value,str)})

class Checker(frozen.source_owners.Checker):
    def __init__(self,spec):
        need(spec==frozen.specification(spec['scenario']),'Exact sealed SoC spec/ELF')
        super().__init__(spec)
        need(set(symbol_keys())<=set(self.s),'Every literal original symbol key present')
        self.entry_pcs=o.window(self.code,self.s['main'],len(ENTRY))
        need(tuple(self.code[pc] for pc in self.entry_pcs)==ENTRY,'Exact original main prologue')
        actual=o.elf_bytes(spec['elf'])
        for pc,insn in zip(self.entry_pcs,ENTRY):
            need(int.from_bytes(bytes(actual[pc+i] for i in range(2)),'little')==insn,
                 'Actual ELF prologue bytes')
        need(self.code[self.entry_pcs[-1]+2]==0x300024f3,'Prologue ends before first mstatus save')
        self.entry_index=None
        self.current_entry=None
        self.frame_sp=None
        self.opaque_spills=[]

    def row(self,r):
        in_entry=False
        if r['event']=='retire':
            pc=int(r['pc'],16)
            if pc==self.s['main']:
                need(self.entry_index is None and not self.started,'Main entry exactly once')
                need(self.regs.get(2)==self.s['__stack_top'],'Actual known startup SP')
                self.frame_sp=self.regs[2]-224
                need(self.frame_sp%16==0 and self.frame_sp>self.s['__bss_end'],'Isolated aligned main frame')
                self.entry_index=0
            if self.entry_index is not None and self.entry_index<len(ENTRY):
                i=self.entry_index
                need(pc==self.entry_pcs[i] and int(r['insn'],16)==ENTRY[i] and int(r['trap'])==0,
                     'Contiguous exact prologue retirement')
                if i==0:
                    need(int(r['rd'])==2 and int(r['rd_wdata'],16)==self.frame_sp
                         and int(r['mem_rmask'],16)==int(r['mem_wmask'],16)==0,'Actual frame allocation')
                else:
                    need(int(r['rd'])==0 and self.regs.get(2)==self.frame_sp,'Spill has stable SP/no destination')
                self.current_entry=i
                in_entry=True
            elif pc in self.entry_pcs:
                raise ValueError('Prologue replay after original entry')
        super().row(r)
        if in_entry:
            self.entry_index+=1
            self.current_entry=None

    def scalar(self,r,pc,insn,trap):
        rm,wm=int(r['mem_rmask'],16),int(r['mem_wmask'],16)
        if rm or wm:
            d=old.memory_op(insn)
            need(d is not None and d['base'] in self.regs,'Known scalar address base')
            if wm:
                need(d['kind']=='write','Store decoder direction')
                reg=d['register']
                if reg not in self.regs:
                    i=self.current_entry
                    need(i is not None and 2<=i<len(ENTRY) and self.entry_index==i,
                         'Unknown business/nonentry store is forbidden')
                    need(pc==self.entry_pcs[i] and insn==ENTRY[i] and reg==CALLEE[i-2]
                         and d['base']==2 and d['size']==8 and d['offset']==224-8*i,
                         'Only exact first callee-saved main spill')
                    a=int(r['mem_addr'],16);value=int(r['mem_wdata'],16)
                    need(self.regs[2]==self.frame_sp and a==self.frame_sp+d['offset']
                         and self.frame_sp<=a and a+8<=self.s['__stack_top']
                         and a%8==0 and wm==0xff and rm==0 and not trap and int(r['rd'])==0,
                         'Actual spill address/BE/frame/retirement')
                    need(0<=value<=o.MASK64 and all(x['register']!=reg for x in self.opaque_spills),
                         'Single actual opaque input capture')
                    self.opaque_spills.append(dict(register=reg,value=value,pc=pc,address=a,
                                                   cycle=int(r['cycle']),source='actual_RVFI_first_caller_spill'))
                    self.regs[reg]=value
        super().scalar(r,pc,insn,trap)

    def finish(self):
        result=super().finish()
        need(self.entry_index==len(ENTRY) and self.current_entry is None
             and [x['register'] for x in self.opaque_spills]==list(CALLEE),
             'Complete original main entry and twelve first opaque spills')
        result.update(successor='exact_main_first_opaque_spill01',opaque_spills=self.opaque_spills,
                      actual_main_prologue_instructions=len(ENTRY),original_literal_symbol_keys=symbol_keys(),
                      unchanged_business_oracle=True)
        return result
