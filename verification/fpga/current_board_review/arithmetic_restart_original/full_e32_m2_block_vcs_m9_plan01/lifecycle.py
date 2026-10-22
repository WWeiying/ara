"""Hashbound m2 scalar sites and ownership, including real seed-cache accesses."""
from context import ROOT,SOFT,read,require,width

BSS_PC=0x80000046
SEED_PC=dict(b=0x80000410,a=0x80000412,a0=0x800015f6,b0=0x800015fa,
    a1=0x8000042e,b1=0x80000430,a2=0x80001608,b2=0x8000160c,b3=0x800015d8)
CACHE_LOAD_PC=0x80000452
CACHE_STORE_PC=0x80000458
SENTINEL=0x0000005b0000005b
STATIC=read(ROOT/'compiled_audit01/RESULT.json')['compiled']['soc']
FP_PC=[int(x['pc'],16) for x in STATIC['FP_events']]
FP_LOAD_PC=[pc-2 for pc in FP_PC]
INIT_PC=[int(pc,16) for pc in STATIC['output_store_pcs']]
READ_PC=[int(pc,16) for pc in STATIC['output_read_pcs']]
CLEAR_PC=[int(x['pc'],16) for x in STATIC['mask_paths']['0']['clear']]
FP_INPUTS=(0xc1000000,0xc0000000,0x80000000,0,0x3f000000,0x3f800000,0x40000000,0x41000000)

def words(values):return b''.join(v.to_bytes(4,'little') for v in values)
def full_group(vectors,first):
    require(first in (8,16,24) and all(n in vectors for n in (first,first+1)),'Missing full two-register group')
    require(all(0<=vectors[n]<1<<1024 for n in (first,first+1)),'Actual128B physical register')
    return b''.join(vectors[n].to_bytes(128,'little') for n in (first,first+1))
def lw_value(value):return value if value<0x80000000 else value|0xffffffff00000000
def seed_schedule():
    events=[]
    for seed in range(3):
        rng=0x937ad68de41c725f^seed
        for i in range(64):
            rng^=(rng<<13)&((1<<64)-1);rng^=rng>>7;rng^=(rng<<17)&((1<<64)-1)
            events += [(seed,SEED_PC['b'],'b',4*i,(rng>>19)&0xffffffff),(seed,SEED_PC['a'],'a',4*i,rng&0xffffffff)]
            if i%8==0:events += [(seed,SEED_PC['a0'],'a',4*i,0),(seed,SEED_PC['b0'],'b',4*i,0)]
            elif i%8==1:events += [(seed,SEED_PC['a1'],'a',4*i,0xffffffff),(seed,SEED_PC['b1'],'b',4*i,1)]
            elif i%8==2:events += [(seed,SEED_PC['a2'],'a',4*i,0x80000000),(seed,SEED_PC['b2'],'b',4*i,0xffffffff)]
            elif i%8==3:events.append((seed,SEED_PC['b3'],'b',4*i,32))
    require(len(events)==552,'Three184-store original RNG initializations');return events
def mask_schedule(mode):
    events=[(pc,8*i,8,0,None) for i,pc in enumerate(CLEAR_PC)];mask=[0]*128
    for event in STATIC['mask_paths'][str(mode)]['bitsets']:
        i=event['index'];mask[i//8]|=1<<(i%8)
        events.append((int(event['pc'],16),i//8,1,mask[i//8],int(event['load_pc'],16)))
    return events

class Lifecycle:
    def __init__(self,symbols,code,entries,rows):
        self.s,self.code,self.entries,self.rows=symbols,code,set(entries),rows
        self.ordered_entries=tuple(entries);self.next_bss=symbols['__bss_start'];self.boot_locked=False;self.entered=False
        self.calls=0;self.seed_cursor=0;self.seed=seed_schedule()
        self.cache_base=symbols['__stack_top']-336+192
        self.cache_reads=0;self.cache_stores=0;self.cache_pending=None
        self.fp_cursor=0;self.fp_stores=0;self.fp_calls=0;self.fp_reads=0;self.fp_pending=None
        self.mask_cursor=0;self.mask_groups=0;self.mask_clear_stores=0;self.mask_bit_stores=0;self.mask_pending=None
        self.output_stores=0;self.read_cursor=0;self.output_reads=0
        self.mask_wants={m:mask_schedule(m) for m in range(3)}
        self.mask_loads={e[4] for events in self.mask_wants.values() for e in events if e[4] is not None}
        self.fp_pc_set=set(FP_PC);self.fp_loads=set(FP_LOAD_PC)
        require(code[BSS_PC]==0x0002b023,'Actual BSS code')
        for pc in [*SEED_PC.values(),*FP_PC,CACHE_STORE_PC]:require(width(code[pc],True)==4,'Actual input/cache SW site')
        for pc in INIT_PC+CLEAR_PC:require(width(code[pc],True)==8,'Actual SD site')
        for pc in READ_PC:require(width(code[pc],False)==8,'Actual33 LD, no short tail')
        for pc in FP_LOAD_PC+[CACHE_LOAD_PC]:require(width(code[pc],False)==4,'Actual cache LW site')
        fp_seed=read(SOFT/'sequence.json')[1365]['a'][:8] if rows is None else rows[1365]['a'][:8]
        require(tuple(fp_seed)==FP_INPUTS,'Actual original eight FP source patterns')
    def row(self):
        require(self.entered and self.calls<len(self.rows),'Active source call owner');return self.rows[self.calls]
    def setup_ready(self,row):
        require(self.seed_cursor==184*(row['seed']+1) and self.cache_stores==8*(row['seed']+1) and self.cache_pending is None,'Complete source seed/cache before mask/FP/output')
        require(self.calls==0 or self.read_cursor==33,'Complete previous full oracle')
    def enter(self,pc):
        if pc==self.s['main']:
            require(not self.boot_locked and self.next_bss==self.s['__bss_end'],'Complete BSS before main');self.boot_locked=True
        if pc==self.s['arithmetic_main']:
            require(self.boot_locked and not self.entered,'Single arithmetic entry');self.entered=True
        if pc in self.entries:
            row=self.row();self.setup_ready(row)
            require(pc==self.ordered_entries[row['op']],'Actual helper belongs to next original op')
            require(self.output_stores==33,'All33 output initialization stores')
            require(self.fp_cursor==(128 if row['op']>=25 else 0) and self.fp_pending is None,'Each FP call full128 paired cache LW/SW even equal old values')
            require(self.mask_cursor==(len(self.mask_wants[row['mode']]) if row['si']==0 else 0) and self.mask_pending is None,'Complete clear/selected mask source owner')
            if row['si']==0:self.mask_groups+=1
            if row['op']>=25:self.fp_calls+=1
            self.calls+=1;self.output_stores=0;self.read_cursor=0;self.fp_cursor=0;self.mask_cursor=0
    def store(self,pc,insn,address,size,value):
        require(self.code.get(pc)==insn,'Actual scalar store PC/code')
        if pc==BSS_PC:
            require(not self.boot_locked and size==8 and value==0 and address==self.next_bss and address+8<=self.s['__bss_end'],'Ordered BSS clear')
            self.next_bss+=8;return
        if pc==CACHE_STORE_PC or address<self.cache_base+32 and address+size>self.cache_base:
            row=self.row();seed,k=divmod(self.cache_stores,8)
            require(self.calls==seed*1995 and self.seed_cursor==184*(seed+1) and self.output_stores==self.mask_cursor==self.fp_cursor==0,'Cache source seed owner/phase')
            require(self.cache_pending==(seed,k) and (pc,address,size,value)==(CACHE_STORE_PC,self.cache_base+4*k,4,FP_INPUTS[(k+seed)%8]),'Cache exact ordered SW after actual source LW')
            self.cache_pending=None;self.cache_stores+=1;return
        out=self.s['out']
        if address<out+4104 and address+size>out:
            row=self.row();self.setup_ready(row)
            require(self.output_stores<33 and self.fp_cursor==(128 if row['op']>=25 else 0) and self.fp_pending is None and
                self.mask_cursor==(len(self.mask_wants[row['mode']]) if row['si']==0 else 0),'Setup phases before output')
            require((pc,address,size,value)==(INIT_PC[self.output_stores],out+8*self.output_stores,8,SENTINEL),'Exact33 SD initialization order/value/address')
            self.output_stores+=1
        for name in ('a','b'):
            base=self.s[name]
            if address<base+4096 and address+size>base:
                row=self.row()
                if pc in self.fp_pc_set:
                    self.setup_ready(row)
                    require(row['op']>=25 and self.fp_cursor<128 and self.output_stores==0 and
                        self.mask_cursor==(len(self.mask_wants[row['mode']]) if row['si']==0 else 0),'Current FP call owner/phase')
                    i,bank=divmod(self.fp_cursor,2);key=('a','b')[bank]
                    require(self.fp_pending==self.fp_cursor and (pc,address,size,value)==(FP_PC[self.fp_cursor],self.s[key]+4*i,4,row[key][i]),'FP128 ordered bank/index/site/value and matching cache LW')
                    self.fp_pending=None;self.fp_cursor+=1;self.fp_stores+=1
                else:
                    require(self.seed_cursor<len(self.seed),'Extra seed store')
                    seed,wpc,key,offset,wvalue=self.seed[self.seed_cursor]
                    require(self.calls==seed*1995 and self.cache_stores==seed*8 and self.cache_pending is None and
                        (pc,address,size,value)==(wpc,self.s[key]+offset,4,wvalue),'Seed RNG exact original store owner/order')
                    self.seed_cursor+=1
        mask=self.s['mask']
        if address<mask+128 and address+size>mask:
            row=self.row();self.setup_ready(row);want=self.mask_wants[row['mode']]
            require(row['si']==0 and self.mask_cursor<len(want) and self.fp_cursor==self.output_stores==0,'Mask group source owner/phase')
            wpc,off,w,val,load=want[self.mask_cursor]
            require((pc,address,size,value)==(wpc,mask+off,w,val),'Exact ordered clear/bitset and cumulative value')
            require(self.mask_pending==(self.mask_cursor if size==1 else None),'Selected SB requires actual corresponding LBU after16SD')
            self.mask_pending=None;self.mask_cursor+=1
            if size==8:self.mask_clear_stores+=1
            else:self.mask_bit_stores+=1
    def read(self,pc,address,size,value):
        if pc==CACHE_LOAD_PC:
            row=self.row();seed,k=divmod(self.cache_stores,8)
            require(self.cache_pending is None and self.cache_reads==self.cache_stores and self.calls==seed*1995 and
                self.seed_cursor==184*(seed+1) and self.mask_cursor==self.fp_cursor==self.output_stores==0,'Seed cache LW owner/order')
            require((address,size,value)==(self.s['fp_inputs']+4*((seed+k)%8),4,lw_value(FP_INPUTS[(seed+k)%8])),'Actual source fp_inputs seed-cycle LW')
            self.cache_pending=(seed,k);self.cache_reads+=1
        if pc in self.fp_loads:
            row=self.row();self.setup_ready(row)
            require(row['op']>=25 and self.fp_cursor<128 and self.fp_pending is None and self.output_stores==0 and
                self.mask_cursor==(len(self.mask_wants[row['mode']]) if row['si']==0 else 0),'FP cache LW source owner/order')
            i,bank=divmod(self.fp_cursor,2);slot=(3*i if bank else i)%8
            require((pc,address,size,value)==(FP_LOAD_PC[self.fp_cursor],self.cache_base+4*slot,4,lw_value(row[('a','b')[bank]][i])),'Actual FP cache seed slot/value/site')
            self.fp_pending=self.fp_cursor;self.fp_reads+=1
        if pc in self.mask_loads:
            row=self.row();self.setup_ready(row);want=self.mask_wants[row['mode']]
            require(row['si']==0 and 16<=self.mask_cursor<len(want) and self.mask_pending is None and self.fp_cursor==self.output_stores==0,'Mask LBU only after all16SD before next selected SB')
            _,off,w,val,load=want[self.mask_cursor]
            previous=0
            for _,earlier,wid,v,_ in want[16:self.mask_cursor]:
                if earlier==off:previous=v
            require((pc,address,size,value)==(load,self.s['mask']+off,1,previous),'Exact previous cumulative mask LBU')
            self.mask_pending=self.mask_cursor
        out=self.s['out']
        if address<out+4104 and address+size>out:
            require(self.calls>0 and self.read_cursor<33,'Owned scalar output read')
            require((pc,address,size)==(READ_PC[self.read_cursor],out+8*self.read_cursor,8),'Exact33 ordered LD incl element63/rear guard')
            self.read_cursor+=1;self.output_reads+=1
    def finish(self):
        require((self.calls,self.output_stores,self.read_cursor,self.output_reads,self.seed_cursor,self.fp_cursor,self.fp_stores,self.fp_calls,
                 self.mask_cursor,self.mask_groups,self.mask_clear_stores,self.mask_bit_stores,self.cache_reads,self.cache_stores,self.fp_reads)==
                (5985,0,33,197505,552,0,241920,1890,0,2205,35280,77175,24,24,241920),'Full exact source lifecycle through final call')
        require(self.cache_pending is self.fp_pending is self.mask_pending is None,'No outstanding scalar setup pair')
