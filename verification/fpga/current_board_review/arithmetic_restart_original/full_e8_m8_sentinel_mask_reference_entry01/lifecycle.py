"""One shared actual shadow and exact new-ELF source store epochs."""
from context import *
class Lifecycle:
    def __init__(self,symbols,code,entries):
        self.s,self.code,self.entries=symbols,code,set(entries)
        self.profile=read(HERE/'PROFILE.json');require(self.profile['elf_sha256']==ELF_SHA,'Profile new ELF')
        self.rows=read(OLD/'sequence.json');self.memory={}
        self.next_bss=symbols['__bss_start'];self.boot_locked=False;self.entered=False
        self.calls=0;self.stores=0;self.mask_cursor=0;self.seed_cursor=0
        self.seed=[e for s in self.profile['seed_profiles'] for e in s['events']]
        self.seed_ends=[sum(len(p['events']) for p in self.profile['seed_profiles'][:i+1]) for i in range(3)]
        self.abi=set(self.profile['abi_unknown_save_pcs'])
        for pc in self.abi:
            d=memory_op(code[pc])
            require(d and d['kind']=='write' and d['base']==2 and d['size']==8 and d['register'] in (8,9,18,19,20,21,22,23,24,25,26,27),'Only actual ABI callee-save whitelist')
    def enter(self,pc):
        require(pc not in self.profile['failure_pcs'],'Actual failure/trap PC')
        if pc==self.s['main']:
            require(self.next_bss==self.s['__bss_end'] and not self.boot_locked,'Complete BSS/main once');self.boot_locked=True
        if pc==self.s['arithmetic_main']:
            require(self.boot_locked and not self.entered,'Original arithmetic entry once');self.entered=True
        if pc in self.entries:
            require(self.entered and self.calls<4095 and self.stores==129,'Missing full fresh128SD+SH')
            row=self.rows[self.calls];wanted=16 if row['si']==0 else 0
            require(self.mask_cursor==wanted and self.seed_cursor==self.seed_ends[row['seed']],'Original mask/seed source epoch before helper')
            self.calls+=1;self.stores=0;self.mask_cursor=0
    def source_store(self,pc,insn,address,size,value,regs):
        d=memory_op(insn);require(d and d['kind']=='write' and d['size']==size and self.code.get(pc)==insn,'Actual scalar store decode/PC')
        require(d['base'] in regs and address==(regs[d['base']]+d['offset'])&MASK64,'Actual source base GPR/address')
        if d['register'] not in regs:
            require(pc in self.abi and d['register'] in (8,9,18,19,20,21,22,23,24,25,26,27) and self.s['__stack_top']-304<=address<self.s['__stack_top'],'Unknown GPR only exact ABI save')
        else:
            require(value==regs[d['register']]&((1<<(8*size))-1),'Actual source GPR/store data')
        self.store(pc,insn,address,size,value)
    def store(self,pc,insn,address,size,value):
        require(self.code.get(pc)==insn,'Store exact actual code')
        if pc==self.profile['bss_pc']:
            require(not self.boot_locked and insn==self.profile['bss_code'] and size==8 and value==0 and address==self.next_bss and address+8<=self.s['__bss_end'],'Exact full startup BSS')
            self.next_bss+=8
        elif self.s['out']<=address<self.s['out']+1026:
            require(self.entered and self.calls<4095 and self.stores<129,'Output source owner')
            e=self.profile['initializer'][self.stores]
            require((pc,insn,address-self.s['out'],size,value)==(e['pc'],e['insn'],e['offset'],e['size'],e['value']),'Actual ordered PC/width/value full fresh output')
            self.stores+=1
        elif self.s['mask']<=address<self.s['mask']+128:
            require(self.entered and self.calls<4095,'Mask source owner')
            row=self.rows[self.calls]
            require(row['si']==0 and self.mask_cursor<16 and self.stores==0,'Original mask group phase, no replay')
            e=self.profile['mask_profiles'][row['mode']]['events'][self.mask_cursor]
            require((pc,insn,address-self.s['mask'],size,value)==(e['pc'],e['insn'],e['offset'],e['size'],e['value']),'Actual mask reordered PC/width/value')
            self.mask_cursor+=1
        elif any(self.s[n]<=address<self.s[n]+1024 for n in ('a','b')):
            require(self.entered and self.calls in (0,1365,2730) and self.seed_cursor<len(self.seed) and self.stores==self.mask_cursor==0,'Exact next-seed RNG phase')
            e=self.seed[self.seed_cursor]
            require((pc,insn,address-self.s[e['bank']],size,value)==(e['pc'],e['insn'],e['offset'],e['size'],e['value']),'Every original RNG store PC/value/order')
            self.seed_cursor+=1
        for i in range(size):self.memory[address+i]=(value>>(8*i))&255
    def value(self,address,size):
        require(all(address+i in self.memory for i in range(size)),'Missing actual initialized shadow byte')
        return sum(self.memory[address+i]<<(8*i) for i in range(size))
    def finish(self):
        require(self.calls==4095 and self.stores==self.mask_cursor==0 and self.seed_cursor==len(self.seed),'Complete original lifecycle')
