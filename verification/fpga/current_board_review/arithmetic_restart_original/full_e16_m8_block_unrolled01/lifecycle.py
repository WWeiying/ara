"""Actual typed16 initializer PCs, exactBSS phase and128SD+SW footprint."""
from pathlib import Path
import json
from model import CHECKED_BYTES
HERE=Path(__file__).resolve().parent
def require(ok,why):
    if not ok:raise ValueError(why)

class Lifecycle:
    def __init__(self,symbols,code,entries):
        self.s=symbols;self.entries=set(entries);self.next_bss=symbols['__bss_start']
        self.boot_locked=False;self.entered=False;self.stores=self.calls=0
        profile=json.loads((HERE/'lowering.json').read_text())['spike']
        require(profile['elf_sha256']==json.loads((HERE/'proof.json').read_text())['backends']['spike']['sha256'],
            'Actual typed16 lowering ELF identity')
        self.init=profile['initializer'];self.bss_pc=profile['bss_store']
        require(all(code.get(row['pc'])==row['insn'] for row in self.init) and code.get(self.bss_pc)==0x0002b023,
            'Actual typed16 initializer/BSS PCs/code')
    def enter(self,pc):
        if pc==self.s['main']:
            require(self.next_bss==self.s['__bss_end'] and not self.boot_locked,'Complete actual BSS/main')
            self.boot_locked=True
        if pc==self.s['arithmetic_main']:
            require(self.boot_locked and not self.entered,'Original arithmetic entry once');self.entered=True
        if pc in self.entries:
            require(self.entered and self.stores==129,'Missing exact per-call128SD+SW initializer')
            self.calls+=1;self.stores=0
    def store(self,pc,insn,address,size,value):
        if pc==self.bss_pc:
            require(not self.boot_locked and insn==0x0002b023 and size==8 and value==0 and
                address==self.next_bss and address%8==0 and address+8<=self.s['__bss_end'],'Exact startupBSS SDzero sequence')
            self.next_bss+=8;return
        out=self.s['out']
        if address<out+2052 and address+size>out:
            require(self.entered and out<=address and address+size<=out+CHECKED_BYTES and self.stores<129,'Business output owner/footprint')
            item=self.init[self.stores]
            require((pc,insn,size)==(item['pc'],item['insn'],item['size']) and address==out+item['offset'] and
                value==(0x005b005b if size==4 else 0x005b005b005b005b),'Exact typed005b PC/data/order/width')
            self.stores+=1
