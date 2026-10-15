"""Actual frozen SoC PC ownership for e32/m1, including fresh per-call FP writes."""
def require(ok,why):
    if not ok:raise ValueError(why)
def width(code,write):
    if code&3!=3:
        quadrant,kind=code&3,(code>>13)&7
        if quadrant in (0,2) and kind in ((6,7) if write else (2,3)):
            return 4 if kind in (2,6) else 8
        return None
    if code&127==(35 if write else 3):return 1<<(((code>>12)&7)&3)
    return None
BSS_PC=0x80000046
SEED_PC=dict(b=0x80000400,a=0x80000402,a0=0x80000b90,b0=0x80000b94,
    a1=0x80000414,b1=0x80000418,a2=0x80000b86,b2=0x80000b8a,b3=0x80000b76)
FP_PC=(0x800009cc,0x800009d0)
MASK_SET_PC=0x80000532
INIT_PC=[0x8000056e+4*i for i in range(17)]
READ_PC=[0x800005ea]+[0x8000087c+10*i for i in range(16)]
# The final pair reverses destination registers but has the same10-byte stride.
CLEAR_PC=[0x800004ae+8*i for i in range(8)]+[0x800004ea+4*i for i in range(8)]
SENTINEL=0x0000005b0000005b
def full_group(vectors,first):
    require(first in (8,16,24) and first in vectors,'Missing full physical register')
    require(0<=vectors[first]<1<<1024,'Actual VLEN128B')
    return vectors[first].to_bytes(128,'little')
def words(values):return b''.join(v.to_bytes(4,'little') for v in values)
def seed_schedule():
    events=[]
    for seed in range(3):
        rng=0x937ad68de41c725f^seed
        for i in range(32):
            rng^=(rng<<13)&((1<<64)-1);rng^=rng>>7;rng^=(rng<<17)&((1<<64)-1)
            events += [(seed,SEED_PC['b'],'b',4*i,(rng>>19)&0xffffffff),(seed,SEED_PC['a'],'a',4*i,rng&0xffffffff)]
            if i%8==0:events += [(seed,SEED_PC['a0'],'a',4*i,0),(seed,SEED_PC['b0'],'b',4*i,0)]
            elif i%8==1:events += [(seed,SEED_PC['a1'],'a',4*i,0xffffffff),(seed,SEED_PC['b1'],'b',4*i,1)]
            elif i%8==2:events += [(seed,SEED_PC['a2'],'a',4*i,0x80000000),(seed,SEED_PC['b2'],'b',4*i,0xffffffff)]
            elif i%8==3:events.append((seed,SEED_PC['b3'],'b',4*i,32))
    require(len(events)==276,'Three original92-store seed initializations');return events
def mask_schedule(mode):
    events=[(pc,8*i,8,0) for i,pc in enumerate(CLEAR_PC)];mask=[0]*128
    for i in range(32):
        if mode==0 or mode==1 and i%2==1 or mode==2 and i%7==2:
            mask[i//8]|=1<<(i%8);events.append((MASK_SET_PC,i//8,1,mask[i//8]))
    return events
class Lifecycle:
    def __init__(self,symbols,code,entries,rows):
        self.s,self.code,self.entries,self.rows=symbols,code,set(entries),rows
        self.ordered_entries=tuple(entries)
        self.next_bss=symbols['__bss_start'];self.boot_locked=False;self.entered=False
        self.calls=0;self.seed_cursor=0;self.seed=seed_schedule();self.fp_cursor=0;self.fp_stores=0;self.fp_calls=0
        self.mask_cursor=0;self.mask_groups=0;self.mask_clear_stores=0;self.mask_bit_stores=0
        self.output_stores=0;self.read_cursor=0;self.output_reads=0
        require(code[BSS_PC]==0x0002b023,'Actual BSS code')
        for pc in [*SEED_PC.values(),*FP_PC]:require(width(code[pc],True)==4,'Original32bit input store site')
        for pc in INIT_PC+CLEAR_PC:require(code[pc]&127==35 and (code[pc]>>12)&7==3,'Actual SD site')
        for pc in READ_PC:require(code[pc]&127==3 and (code[pc]>>12)&7==3,'Actual LD site17, no short tail')
        require(code[MASK_SET_PC]&127==35 and (code[MASK_SET_PC]>>12)&7==0,'Original bitset SB')
    def enter(self,pc):
        if pc==self.s['main']:
            require(not self.boot_locked and self.next_bss==self.s['__bss_end'],'Complete BSS before main');self.boot_locked=True
        if pc==self.s['arithmetic_main']:
            require(self.boot_locked and not self.entered,'Single arithmetic entry');self.entered=True
        if pc in self.entries:
            require(self.entered and self.calls<len(self.rows),'Helper owner')
            row=self.rows[self.calls]
            require(pc==self.ordered_entries[row['op']],'Actual helper belongs to next original op')
            require(self.output_stores==17 and (self.calls==0 or self.read_cursor==17),'Complete output fresh/prior reads')
            require(self.seed_cursor==92*(row['seed']+1),'Every seed exact original writes')
            require(self.fp_cursor==(64 if row['op']>=25 else 0),'Every FP call64 fresh SW even if old bytes match')
            wantmask=len(mask_schedule(row['mode'])) if row['si']==0 else 0
            require(self.mask_cursor==wantmask,'Complete16 clear then original bitset, owner si0 only')
            if row['si']==0:self.mask_groups+=1
            if row['op']>=25:self.fp_calls+=1
            self.calls+=1;self.output_stores=0;self.read_cursor=0;self.fp_cursor=0;self.mask_cursor=0
    def store(self,pc,insn,address,size,value):
        require(self.code.get(pc)==insn,'Actual scalar store PC/code')
        if pc==BSS_PC:
            require(not self.boot_locked and size==8 and value==0 and address==self.next_bss and address+8<=self.s['__bss_end'],'Ordered BSS clear')
            self.next_bss+=8;return
        out=self.s['out']
        if address<out+4104 and address+size>out:
            require(self.entered and self.calls<len(self.rows) and self.output_stores<17,'Owned output init')
            row=self.rows[self.calls]
            require((self.calls==0 or self.read_cursor==17) and self.seed_cursor==92*(row['seed']+1) and
                self.fp_cursor==(64 if row['op']>=25 else 0) and
                self.mask_cursor==(len(mask_schedule(row['mode'])) if row['si']==0 else 0),'Setup phases before output init')
            require((pc,address,size,value)==(INIT_PC[self.output_stores],out+self.output_stores*8,8,SENTINEL),'Exact17 SD init order/value/address')
            self.output_stores+=1
        for name in ('a','b'):
            base=self.s[name]
            if address<base+4096 and address+size>base:
                require(self.entered and self.calls<len(self.rows),'Input owner')
                row=self.rows[self.calls]
                if pc in FP_PC:
                    require(row['op']>=25 and self.fp_cursor<64 and self.seed_cursor==92*(row['seed']+1),'FP current call owner')
                    require(self.output_stores==0 and self.mask_cursor==(len(mask_schedule(row['mode'])) if row['si']==0 else 0),
                        'Mask phase before FP refresh/output')
                    i,bank=divmod(self.fp_cursor,2);key=('a','b')[bank]
                    require((pc,address,size,value)==(FP_PC[bank],self.s[key]+4*i,4,row[key][i]),'FP every index/bank/site/value/order')
                    self.fp_cursor+=1;self.fp_stores+=1
                else:
                    require(self.seed_cursor<len(self.seed),'Extra seed store')
                    seed,wpc,key,offset,wvalue=self.seed[self.seed_cursor]
                    require(self.calls==seed*1995 and (pc,address,size,value)==(wpc,self.s[key]+offset,4,wvalue),'Seed RNG exact source write/owner')
                    self.seed_cursor+=1
        mask=self.s['mask']
        if address<mask+128 and address+size>mask:
            require(self.entered and self.calls<len(self.rows),'Mask owner')
            row=self.rows[self.calls];want=mask_schedule(row['mode'])
            require(row['si']==0 and self.mask_cursor<len(want),'si0 mask lifecycle only')
            require(self.seed_cursor==92*(row['seed']+1) and self.fp_cursor==self.output_stores==0 and
                    (self.calls==0 or self.read_cursor==17),'Seed/prior-oracle before mask, FP/output after mask')
            wpc,offset,width,val=want[self.mask_cursor]
            require((pc,address,size,value)==(wpc,mask+offset,width,val),'Ordered clear/bitset phase and full128 byte ownership')
            self.mask_cursor+=1
            if size==8:self.mask_clear_stores+=1
            else:self.mask_bit_stores+=1
    def read(self,pc,address,size):
        out=self.s['out']
        if address<out+4104 and address+size>out:
            require(self.calls>0 and self.read_cursor<17,'Owned scalar output read')
            require((pc,address,size)==(READ_PC[self.read_cursor],out+8*self.read_cursor,8),'Exact17 ordered LD / whole136B including guards')
            self.read_cursor+=1;self.output_reads+=1
    def finish(self):
        require((self.calls,self.output_stores,self.read_cursor,self.output_reads,self.seed_cursor,self.fp_cursor,self.fp_stores,self.fp_calls,
                 self.mask_cursor,self.mask_groups,self.mask_clear_stores,self.mask_bit_stores)==
                (5985,0,17,101745,276,0,120960,1890,0,2205,35280,38955),'Complete lifecycle including last call/group')
