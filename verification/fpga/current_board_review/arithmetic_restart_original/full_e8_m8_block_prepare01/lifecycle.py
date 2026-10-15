"""Exact hash-bound Spike ELF startup and per-call output initializer."""
INIT=((0x80000506,0xe380,8),(0x80000508,0xe780,8),
      (0x8000050a,0xeb80,8),(0x8000050c,0xef80,8),
      (0x8000050e,0xf380,8),(0x80000510,0xf780,8),
      (0x80000512,0xfb80,8),(0x80000514,0xff80,8),
      (0x80000524,0x40f71023,2))

def require(ok,why):
    if not ok:raise ValueError(why)

class Lifecycle:
    def __init__(self,symbols,code,entries):
        self.s=symbols;self.entries=set(entries);self.next_bss=symbols['__bss_start']
        self.boot_locked=False;self.entered=False;self.stores=0;self.calls=0
        require(all(code.get(pc)==insn for pc,insn,_ in INIT),'Actual initializer PC/insn drift')
        require(code.get(0x80000046)==0x0002b023,'Actual BSS initializer drift')
    def enter(self,pc):
        if pc==self.s['main']:
            require(self.next_bss==self.s['__bss_end'] and not self.boot_locked,'Incomplete/duplicate BSS/main')
            self.boot_locked=True
        if pc==self.s['arithmetic_main']:
            require(self.boot_locked and not self.entered,'Actual arithmetic entry')
            self.entered=True
        if pc in self.entries:
            require(self.entered and self.stores==129,'Per-call exact128 SD plus SH missing/duplicated')
            self.calls+=1;self.stores=0
    def store(self,pc,insn,address,size,value):
        if pc==0x80000046:
            require(not self.boot_locked and insn==0x0002b023 and size==8 and value==0 and
                address==self.next_bss and address%8==0 and address+8<=self.s['__bss_end'],'Actual ordered startup BSS')
            self.next_bss+=8;return
        out=self.s['out']
        if address<out+1026 and address+size>out:
            require(self.entered and out<=address and address+size<=out+1026,'Unowned/wide output store')
            i=self.stores
            require(i<129,'Extra output initialization')
            require((pc,insn,size)==INIT[i%8 if i<128 else 8] and address==out+8*i and
                value==(0x5b5b if i==128 else 0x5b5b5b5b5b5b5b5b),'Exact output initializer PC/address/width/value/order')
            self.stores+=1
