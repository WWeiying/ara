"""Actual source-owned memory and complete cache-PC lifecycle, no token waiver."""
from context import artifacts,linked,require,width
BSS_PC=0x80000046
SENTINEL=0x0000005b0000005b
REGS={n:i for i,n in enumerate(('zero','ra','sp','gp','tp','t0','t1','t2','s0','s1','a0','a1','a2','a3','a4','a5','a6','a7','s2','s3','s4','s5','s6','s7','s8','s9','s10','s11','t3','t4','t5','t6'))}
def words(values):return b''.join(v.to_bytes(4,'little') for v in values)
def full_group(vectors,first):
    require(first in (8,16,24) and all(n in vectors for n in range(first,first+4)),'Missing full4 physical registers')
    require(all(0<=vectors[n]<1<<1024 for n in range(first,first+4)),'Actual128B physical register width')
    return b''.join(vectors[n].to_bytes(128,'little') for n in range(first,first+4))

class Lifecycle:
    def __init__(self,symbols,code,entries,rows):
        self.s,self.code,self.entries,self.rows=symbols,code,tuple(entries),rows
        self.f,self.machine,self.proof=linked()
        self.packed=next(n for n in self.f if n.startswith('e32m4_packed'))
        self.cache_pcs={x['pc'] for x in self.f[self.packed]};self.cache_entry=min(self.cache_pcs)
        self.next_bss=symbols['__bss_start'];self.boot_locked=False;self.entered=False
        self.calls=0;self.seed_cursor=0;self.mask_cursor=0;self.fp_cursor=0;self.output_stores=0
        self.mask_groups=0;self.mask_clear_stores=0;self.mask_bit_stores=0;self.fp_calls=0;self.fp_stores=0;self.fp_reads=0
        self.output_reads=0;self.read_cursor=0;self.cache_calls=0;self.cache_active=False;self.cache_complete=True
        self.expected_reads=0;self.id_reads=0;self.hits=0;self.misses=0;self.comparisons=0
        paths=self.proof['leaf_paths']
        self.init=[e for e in paths['output']['events'] if e['kind']=='OUT']
        self.fp={int(k):[e for e in v['events'] if e['kind'] in ('FP','A','B')] for k,v in paths['FP'].items()}
        self.fp_store_pcs={int(e['pc'],16) for e in self.fp[0] if e['kind'] in ('A','B')}
        self.mask={int(k):[e for e in v['events'] if e['kind']=='MASK'] for k,v in paths['mask'].items()}
        self.seed=self.seed_schedule()
        require(code[BSS_PC]==0x0002b023 and len(self.init)==65,'BSS and full65 init binding')
        for e in self.init:require(width(code[int(e['pc'],16)],True)==8,'Actual SD init site')
    def seed_schedule(self):
        def site(args):
            pcs=[x['pc'] for x in self.f['arithmetic_main'] if x['op']=='sw' and x['args']==args]
            require(len(pcs)==1,'Unique actual linked RNG store '+args);return pcs[0]
        pcs={k:site(v) for k,v in dict(b='a4,0(a2)',a='a5,0(a1)',a0='zero,0(a1)',b0='zero,0(a2)',a1='a7,0(a1)',b1='t3,0(a2)',a2='t5,0(a1)',b2='a7,0(a2)',b3='t4,0(a2)').items()}
        events=[]
        for seed in range(3):
            rng=0x937ad68de41c725f^seed
            for i in range(128):
                rng^=(rng<<13)&((1<<64)-1);rng^=rng>>7;rng^=(rng<<17)&((1<<64)-1)
                events.extend([(seed,pcs['b'],self.s['b']+4*i,4,(rng>>19)&0xffffffff),(seed,pcs['a'],self.s['a']+4*i,4,rng&0xffffffff)])
                if i%8==0:values=(('a0','a',0),('b0','b',0))
                elif i%8==1:values=(('a1','a',0xffffffff),('b1','b',1))
                elif i%8==2:values=(('a2','a',0x80000000),('b2','b',0xffffffff))
                elif i%8==3:values=(('b3','b',32),)
                else:values=()
                events.extend((seed,pcs[key],self.s[bank]+4*i,4,value) for key,bank,value in values)
        require(len(events)==1104,'Full original368 RNG writes per seed');return events
    def row(self):
        require(self.entered and self.calls<len(self.rows),'Current source setup owner');return self.rows[self.calls]
    def ready(self,row):
        require(self.seed_cursor==368*(row['seed']+1),'Complete original source RNG before setup')
        require(self.cache_complete and (self.calls==0 or self.read_cursor==65),'Prior whole cache/actual oracle complete')
    def match(self,e,pc,address,size,value):
        require((pc,address,size,value)==(int(e['pc'],16),e['address'],e['size'],e['value']),'Exact linked source memory site/order/address/width/value')
    def enter(self,pc,regs=None):
        if pc==self.s['main']:
            require(not self.boot_locked and self.next_bss==self.s['__bss_end'],'Full BSS before main');self.boot_locked=True
        if pc==self.s['arithmetic_main']:
            require(self.boot_locked and not self.entered,'Unique arithmetic entry');self.entered=True
        if pc in self.entries:
            row=self.row();self.ready(row)
            require(pc==self.entries[row['op']] and self.output_stores==65,'Exact next helper/all65 fresh SD')
            require(self.fp_cursor==(264 if row['op']>=25 else 0),'Every FP call fresh8LW+256SW')
            require(self.mask_cursor==(len(self.mask[row['mode']]) if row['si']==0 else 0),'Source group full16SD then ordered SB')
            if row['si']==0:self.mask_groups+=1
            if row['op']>=25:self.fp_calls+=1
            self.calls+=1;self.output_stores=self.fp_cursor=self.mask_cursor=0;self.read_cursor=0;self.cache_complete=False
        if pc==self.cache_entry:
            require(self.calls==self.cache_calls+1 and not self.cache_active and not self.cache_complete,'Exactly one cache owned by completed current helper')
            row=self.rows[self.calls-1]
            self.plan=self.machine.walk(self.packed,self.s['e32m4_expected_ids']+18*(self.calls-1),row['gold'])
            self.plan_branches={int(b['pc'],16):b for b in self.plan['branches']}
            self.cache_pc_cursor=0;self.cache_mem_cursor=0;self.cache_active=True
        if self.cache_active:
            require(pc==self.plan['pcs'][self.cache_pc_cursor],'Complete actual cache PC path: no missing fill/read/compare/tag')
            b=self.plan_branches.get(pc)
            if b is not None:
                require(regs is not None and regs.get(REGS[b['left']])==b['left_value'] and regs.get(REGS[b['right']])==b['right_value'],'Actual live expected/output/tag operands')
                if b['taint']==['ID']:
                    self.hits+=int(b['taken']);self.misses+=int(not b['taken'])
                else:
                    require(regs.get(10)==0 and b['taken'],'Actual sticky0 positive oracle comparison');self.comparisons+=1
            self.cache_pc_cursor+=1
            if self.cache_pc_cursor==len(self.plan['pcs']):
                require(self.cache_mem_cursor==len(self.plan['events']) and self.read_cursor==65,'Cache return only after full actual/expected/ID reads')
                self.cache_calls+=1;self.misses+=1;self.cache_active=False;self.cache_complete=True
        else:require(pc not in self.cache_pcs,'Cache interior without owned entry')
    def store(self,pc,insn,address,size,value):
        require(self.code.get(pc)==insn,'Actual store PC/code')
        if pc==BSS_PC:
            require(not self.boot_locked and size==8 and value==0 and address==self.next_bss and address+8<=self.s['__bss_end'],'Ordered initial BSS')
            self.next_bss+=8;return
        for bank in ('a','b'):
            base=self.s[bank]
            if address<base+4096 and address+size>base:
                row=self.row()
                if pc in self.fp_store_pcs:
                    self.ready(row)
                    require(row['op']>=25 and self.output_stores==0 and self.mask_cursor==(len(self.mask[row['mode']]) if row['si']==0 else 0) and self.fp_cursor<264,'Fresh FP source phase')
                    self.match(self.fp[row['seed']][self.fp_cursor],pc,address,size,value);self.fp_cursor+=1;self.fp_stores+=1
                else:
                    require(self.seed_cursor<len(self.seed),'Extra original RNG store')
                    seed,wpc,addr,w,val=self.seed[self.seed_cursor]
                    require(self.calls==seed*1995 and self.cache_complete and self.mask_cursor==self.fp_cursor==self.output_stores==0,'RNG exact source-seed owner')
                    require((pc,address,size,value)==(wpc,addr,w,val),'Actual original linked RNG store order/value');self.seed_cursor+=1
                return
        if address<self.s['out']+4104 and address+size>self.s['out']:
            row=self.row();self.ready(row)
            require(self.output_stores<65 and self.fp_cursor==(264 if row['op']>=25 else 0) and self.mask_cursor==(len(self.mask[row['mode']]) if row['si']==0 else 0),'Output initialization after all per-call fresh setup')
            self.match(self.init[self.output_stores],pc,address,size,value);self.output_stores+=1;return
        if address<self.s['mask']+128 and address+size>self.s['mask']:
            row=self.row();self.ready(row);events=self.mask[row['mode']]
            require(row['si']==0 and self.mask_cursor<len(events) and self.fp_cursor==self.output_stores==0,'Mask group exact owner')
            self.match(events[self.mask_cursor],pc,address,size,value);self.mask_cursor+=1
            if size==8:self.mask_clear_stores+=1
            else:self.mask_bit_stores+=1
    def read(self,pc,address,size,value):
        if self.cache_active and pc in self.cache_pcs:
            require(self.cache_mem_cursor<len(self.plan['events']),'Extra cache memory read')
            e=self.plan['events'][self.cache_mem_cursor];self.match(e,pc,address,size,value);self.cache_mem_cursor+=1
            if e['kind']=='OUT':self.read_cursor+=1;self.output_reads+=1
            elif e['kind']=='GOLD':self.expected_reads+=1
            elif e['kind']=='ID':self.id_reads+=1
            else:raise ValueError('Unexpected cache memory kind')
            return
        if self.s['fp_inputs']<=address<self.s['fp_inputs']+32:
            row=self.row();self.ready(row)
            require(row['op']>=25 and self.output_stores==0 and self.mask_cursor==(len(self.mask[row['mode']]) if row['si']==0 else 0) and self.fp_cursor<8,'Fresh8 FP input LW before any SW')
            self.match(self.fp[row['seed']][self.fp_cursor],pc,address,size,value);self.fp_cursor+=1;self.fp_reads+=1;return
        for base,length in ((self.s['out'],4104),(self.s['e32m4_expected_blocks'],144128),(self.s['e32m4_expected_ids'],107730)):
            require(not(address<base+length and address+size>base),'Relevant oracle read outside current cache owner')
    def finish(self):
        require((self.calls,self.seed_cursor,self.output_reads,self.fp_stores,self.fp_reads,self.fp_calls,self.mask_groups,self.mask_clear_stores,self.mask_bit_stores,self.cache_calls,self.expected_reads,self.id_reads,self.hits,self.misses,self.comparisons)==
            (5985,1104,389025,483840,15120,1890,2205,35280,154350,5985,124041,53865,33123,14757,389025),'Complete exact full source/cache lifecycle')
        require(self.cache_complete and not self.cache_active and self.read_cursor==65 and self.mask_cursor==self.fp_cursor==self.output_stores==0,'No incomplete current source/cache owner')
