"""Actual e64/m2 PC ownership, including every-call FP clone paths."""
from lifecycle_context import require,width,read,SOFT
INFO=read(SOFT/"audit_artifacts02/RESULT.json")["compiled"]["soc"]
SYMBOLS=read(SOFT/"soc/symbols.json")
BSS_PC=0x80000046
SEED_PC=dict(b=0x800006da,a=0x800006dc,a0=0x80000f24,b0=0x80000f28,
    a1=0x800006ee,b1=0x800006f2,a2=0x80000f18,b2=0x80000f1c,b3=0x80000efc)
FP_ENTRY=int(INFO['refresh_pc'],16)
FP_PATHS=INFO['paths']
FP_STORE_PCS={int(e['pc'],16) for p in FP_PATHS for e in p['stores']}
MASK_SET_PC=0x8000080c
INIT_PC=[int(v,16) for v in INFO['output_store_pcs']]
READ_PC=[int(v,16) for v in INFO['output_read_pcs']]
CLEAR_PC=[0x80000784+8*i for i in range(10)]+[0x800007d0+4*i for i in range(6)]
SENTINEL=0x5b
def full_group(vectors,first):
    require(first in (8,16,24),'Actual physical group base')
    raw=[]
    for n in range(first,first+2):
        require(n in vectors and 0<=vectors[n]<(1<<1024),'Missing full physical128B register')
        raw.append(vectors[n].to_bytes(128,'little'))
    return b''.join(raw)
def words(values):return b''.join(v.to_bytes(8,'little') for v in values)
def seed_schedule():
    events=[]
    for seed in range(3):
        rng=0x937ad68de41c725f^seed
        for i in range(32):
            rng^=(rng<<13)&((1<<64)-1);rng^=rng>>7;rng^=(rng<<17)&((1<<64)-1)
            events += [(seed,SEED_PC['b'],'b',8*i,(rng>>19)&0xffffffffffffffff),(seed,SEED_PC['a'],'a',8*i,rng&0xffffffffffffffff)]
            if i%8==0:events += [(seed,SEED_PC['a0'],'a',8*i,0),(seed,SEED_PC['b0'],'b',8*i,0)]
            elif i%8==1:events += [(seed,SEED_PC['a1'],'a',8*i,0xffffffffffffffff),(seed,SEED_PC['b1'],'b',8*i,1)]
            elif i%8==2:events += [(seed,SEED_PC['a2'],'a',8*i,0x8000000000000000),(seed,SEED_PC['b2'],'b',8*i,0xffffffffffffffff)]
            elif i%8==3:events.append((seed,SEED_PC['b3'],'b',8*i,64))
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
        self.fp_entries=0;self.fp_trace_cursor=0;self.fp_active=False;self.fp_complete=False;self.fp_read_cursor=0
        require(code[BSS_PC]==0x0002b023,'Actual BSS code')
        for pc in [*SEED_PC.values(),*FP_STORE_PCS]:require(width(code[pc],True)==8,'Original64bit input store site')
        for pc in INIT_PC+CLEAR_PC:require(width(code[pc],True)==8,'Actual SD site')
        for pc in READ_PC:require(width(code[pc],False)==8,'Actual LD site34, no short tail')
        require(code[MASK_SET_PC]&127==35 and (code[MASK_SET_PC]>>12)&7==0,'Original bitset SB')
    def enter(self,pc):
        if pc==FP_ENTRY:
            require(self.entered and self.calls<len(self.rows),'FP clone current source owner')
            row=self.rows[self.calls]
            require(row['op']>=25 and self.fp_entries==self.fp_cursor==self.output_stores==0 and
                self.seed_cursor==92*(row['seed']+1) and
                (self.calls==0 or self.read_cursor==34) and
                self.mask_cursor==(len(mask_schedule(row['mode'])) if row['si']==0 else 0),
                'FP clone every-call owner after mask before output, not a replay')
            self.fp_entries=1;self.fp_active=True;self.fp_trace_cursor=0
        if self.fp_active:
            row=self.rows[self.calls];path=FP_PATHS[row['seed']]['pcs']
            require(self.fp_trace_cursor<len(path) and pc==int(path[self.fp_trace_cursor],16),
                'Actual FP clone full contiguous path/seed, no drop duplicate branch')
            self.fp_trace_cursor+=1
            if self.fp_trace_cursor==len(path):
                require(self.fp_cursor==64 and self.fp_read_cursor==8,'Clone return without64SD/eighttableLD')
                self.fp_active=False;self.fp_complete=True
        elif FP_ENTRY<=pc<SYMBOLS['number']:
            raise ValueError('Unowned clone instruction')
        if pc==self.s['main']:
            require(not self.boot_locked and self.next_bss==self.s['__bss_end'],'Complete BSS before main');self.boot_locked=True
        if pc==self.s['arithmetic_main']:
            require(self.boot_locked and not self.entered,'Single arithmetic entry');self.entered=True
        if pc in self.entries:
            require(self.entered and self.calls<len(self.rows),'Helper owner')
            row=self.rows[self.calls]
            require(pc==self.ordered_entries[row['op']],'Actual helper belongs to next original op')
            require(self.output_stores==34 and (self.calls==0 or self.read_cursor==34),'Complete output fresh/prior reads')
            require(self.seed_cursor==92*(row['seed']+1),'Every seed exact original writes')
            require(self.fp_cursor==(64 if row['op']>=25 else 0) and self.fp_complete==(row['op']>=25),'Every FP call64 fresh SD even if old bytes match')
            wantmask=len(mask_schedule(row['mode'])) if row['si']==0 else 0
            require(self.mask_cursor==wantmask,'Complete16 clear then original bitset, owner si0 only')
            if row['si']==0:self.mask_groups+=1
            if row['op']>=25:self.fp_calls+=1
            self.calls+=1;self.output_stores=0;self.read_cursor=0;self.fp_cursor=0;self.mask_cursor=0
            self.fp_entries=0;self.fp_trace_cursor=0;self.fp_read_cursor=0;self.fp_complete=False
    def store(self,pc,insn,address,size,value):
        require(self.code.get(pc)==insn,'Actual scalar store PC/code')
        if pc==BSS_PC:
            require(not self.boot_locked and size==8 and value==0 and address==self.next_bss and address+8<=self.s['__bss_end'],'Ordered BSS clear')
            self.next_bss+=8;return
        out=self.s['out']
        if address<out+8208 and address+size>out:
            require(self.entered and self.calls<len(self.rows) and self.output_stores<34,'Owned output init')
            row=self.rows[self.calls]
            require((self.calls==0 or self.read_cursor==34) and self.seed_cursor==92*(row['seed']+1) and
                self.fp_cursor==(64 if row['op']>=25 else 0) and
                self.mask_cursor==(len(mask_schedule(row['mode'])) if row['si']==0 else 0),'Setup phases before output init')
            require((pc,address,size,value)==(INIT_PC[self.output_stores],out+self.output_stores*8,8,SENTINEL),'Exact34 SD init order/value/address')
            self.output_stores+=1
        for name in ('a','b'):
            base=self.s[name]
            if address<base+8192 and address+size>base:
                require(self.entered and self.calls<len(self.rows),'Input owner')
                row=self.rows[self.calls]
                if pc in FP_STORE_PCS:
                    require(row['op']>=25 and self.fp_cursor<64 and self.seed_cursor==92*(row['seed']+1),'FP current call owner')
                    require(self.output_stores==0 and self.mask_cursor==(len(mask_schedule(row['mode'])) if row['si']==0 else 0),
                        'Mask phase before FP refresh/output')
                    i,bank=divmod(self.fp_cursor,2);key=('a','b')[bank]
                    require((pc,address,size,value)==(int(FP_PATHS[row['seed']]['stores'][self.fp_cursor]['pc'],16),self.s[key]+8*i,8,row[key][i]),'FP every index/bank/site/value/order')
                    self.fp_cursor+=1;self.fp_stores+=1
                else:
                    require(self.seed_cursor<len(self.seed),'Extra seed store')
                    seed,wpc,key,offset,wvalue=self.seed[self.seed_cursor]
                    require(self.calls==seed*1995 and (pc,address,size,value)==(wpc,self.s[key]+offset,8,wvalue),'Seed RNG exact source write/owner')
                    self.seed_cursor+=1
        mask=self.s['mask']
        if address<mask+128 and address+size>mask:
            require(self.entered and self.calls<len(self.rows),'Mask owner')
            row=self.rows[self.calls];want=mask_schedule(row['mode'])
            require(row['si']==0 and self.mask_cursor<len(want),'si0 mask lifecycle only')
            require(self.seed_cursor==92*(row['seed']+1) and self.fp_cursor==self.output_stores==0 and
                    (self.calls==0 or self.read_cursor==34),'Seed/prior-oracle before mask, FP/output after mask')
            wpc,offset,width,val=want[self.mask_cursor]
            require((pc,address,size,value)==(wpc,mask+offset,width,val),'Ordered clear/bitset phase and full128 byte ownership')
            self.mask_cursor+=1
            if size==8:self.mask_clear_stores+=1
            else:self.mask_bit_stores+=1
    def read(self,pc,address,size):
        if SYMBOLS['fp_inputs']<=address<SYMBOLS['fp_inputs']+64:
            row=self.rows[self.calls] if self.calls<len(self.rows) else None
            require(row is not None and self.fp_active and self.fp_read_cursor<8,
                'Owned fresh input table read inside current clone')
            want=FP_PATHS[row['seed']]['loads'][self.fp_read_cursor]
            require((pc,address,size)==(int(want['pc'],16),SYMBOLS['fp_inputs']+8*self.fp_read_cursor,8),
                'Eight exact source table reads per FP call')
            self.fp_read_cursor+=1
        out=self.s['out']
        if address<out+8208 and address+size>out:
            require(self.calls>0 and self.read_cursor<34,'Owned scalar output read')
            require((pc,address,size)==(READ_PC[self.read_cursor],out+8*self.read_cursor,8),'Exact34 ordered LD / whole272B including guards')
            self.read_cursor+=1;self.output_reads+=1
    def finish(self):
        require((self.calls,self.output_stores,self.read_cursor,self.output_reads,self.seed_cursor,self.fp_cursor,self.fp_stores,self.fp_calls,
                 self.mask_cursor,self.mask_groups,self.mask_clear_stores,self.mask_bit_stores)==
                (5985,0,34,203490,276,0,120960,1890,0,2205,35280,38955),'Complete lifecycle including last call/group')
