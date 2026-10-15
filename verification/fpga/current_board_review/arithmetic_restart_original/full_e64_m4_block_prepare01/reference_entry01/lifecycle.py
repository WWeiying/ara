"""Actual owned scalar phases; all full-sized original events are mandatory."""
from context import require,definition,width

def words(values):return b''.join(v.to_bytes(8,'little') for v in values)
def full_group(vectors,first):
    require(first in (8,16,24),'Original group base')
    require(all(n in vectors and 0<=vectors[n]<1<<1024 for n in range(first,first+4)),'All four real128B physical registers')
    return b''.join(vectors[n].to_bytes(128,'little') for n in range(first,first+4))
def seed_schedule(pc):
    events=[]
    for seed in range(3):
        rng=0x937ad68de41c725f^seed
        for i in range(64):
            rng^=(rng<<13)&((1<<64)-1);rng^=rng>>7;rng^=(rng<<17)&((1<<64)-1)
            events.extend([(seed,pc['b'],'b',8*i,rng>>19),(seed,pc['a'],'a',8*i,rng)])
            if i%8==0:events.extend([(seed,pc['a0'],'a',8*i,0),(seed,pc['b0'],'b',8*i,0)])
            elif i%8==1:events.extend([(seed,pc['a1'],'a',8*i,(1<<64)-1),(seed,pc['b1'],'b',8*i,1)])
            elif i%8==2:events.extend([(seed,pc['a2'],'a',8*i,1<<63),(seed,pc['b2'],'b',8*i,(1<<64)-1)])
            elif i%8==3:events.append((seed,pc['b3'],'b',8*i,64))
    require(len(events)==552,'Original three184-write RNG initializations');return events

class Lifecycle:
    def __init__(self,symbols,code,entries,rows,spec=None):
        self.spec=definition() if spec is None else spec
        self.s,self.code,self.rows=symbols,code,rows;self.entries=tuple(entries)
        self.next_bss=symbols['__bss_start'];self.boot_locked=False;self.entered=False
        self.calls=0;self.seed=seed_schedule(self.spec['seed_pc']);self.seed_cursor=0
        self.mask_cursor=0;self.mask_groups=0;self.mask_clear_stores=0;self.mask_bit_stores=0;self.mask_pending=None
        self.fp_cursor=0;self.fp_read_cursor=0;self.fp_seed_reads=0;self.fp_stores=0;self.fp_calls=0;self.fp_reads=0
        self.output_stores=0;self.read_cursor=0;self.expected_cursor=0;self.id_cursor=0
        self.output_reads=0;self.expected_reads=0;self.id_reads=0;self.beq_count=0;self.flag_zero_count=0
        self.completed_oracle=True;self.active=None;self.path=[];self.path_cursor=0
        self.mask_paths=self.spec['mask_paths'];self.fp_paths=self.spec['FP_paths'];self.cmp=self.spec['comparator']
        self.owned=set(self.cmp['all_equal_pcs'])|{x['li'] for x in self.cmp['sites']}
        for paths in (self.mask_paths,self.fp_paths):
            for path in paths.values():self.owned.update(path['pcs'])
        self.cmp_loads={x['pc']:x for x in self.cmp['loads']};self.cmp_ids={x['pc']:x for x in self.cmp['ids']}
        self.beqs={x['beq']:x for x in self.cmp['sites']}
        self.fp_store_pcs={x['pc'] for path in self.fp_paths.values() for x in path['stores']}
        self.init=self.spec['output_stores'];self.BSS_PC=0x80000046
        require(code[self.BSS_PC]==0x0002b023,'Actual startup BSS SD site')
    def row(self):
        require(self.entered and self.calls<len(self.rows),'Next original call owner');return self.rows[self.calls]
    def setup_ready(self,row):
        require(self.seed_cursor==184*(row['seed']+1) and self.completed_oracle,'Full seed/prior-oracle before setup')
    def mask_length(self,row):return len(self.mask_paths[str(row['mode'])]['events']) if row['si']==0 else 0
    def enter(self,pc,regs=None):
        if pc==self.s['main']:
            require(not self.boot_locked and self.next_bss==self.s['__bss_end'],'Ordered full BSS before main');self.boot_locked=True
        if pc==self.s['arithmetic_main']:
            require(self.boot_locked and not self.entered,'Single arithmetic entry');self.entered=True
        if self.active is None:
            if pc==self.mask_paths['0']['pcs'][0]:
                row=self.row();self.setup_ready(row)
                require(row['si']==0 and self.mask_cursor==self.fp_cursor==self.output_stores==0,'Mask only at original group start')
                self.active='mask';self.path=self.mask_paths[str(row['mode'])]['pcs'];self.path_cursor=0
            elif pc==self.fp_paths['0']['pcs'][0]:
                row=self.row();self.setup_ready(row)
                require(row['op']>=25 and self.mask_cursor==self.mask_length(row) and self.fp_cursor==self.output_stores==self.fp_read_cursor==self.fp_seed_reads==0,'Every FP call fresh, no cache reuse')
                self.active='fp';self.path=self.fp_paths[str(row['seed'])]['pcs'];self.path_cursor=0
            elif pc==self.cmp['all_equal_pcs'][0]:
                require(self.calls>0 and not self.completed_oracle and self.read_cursor==self.expected_cursor==self.id_cursor==0,'Owned comparator once after helper')
                self.active='cmp';self.path=self.cmp['all_equal_pcs'];self.path_cursor=0
            elif pc in self.owned:raise ValueError('Unowned/repeated FP/mask/comparator PC '+hex(pc))
        if self.active:
            require(self.path_cursor<len(self.path) and pc==self.path[self.path_cursor],'Complete actual scalar phase PC/code path')
            if self.active=='cmp' and pc in self.beqs:
                insn=self.code[pc];r1=(insn>>15)&31;r2=(insn>>20)&31
                require(regs is not None and r1 in regs and r2 in regs and regs[r1]==regs[r2] and regs.get(15)==0,'Actual equal BEQ inputs and sticky0')
                self.beq_count+=1
            self.path_cursor+=1
        if pc in self.entries:
            row=self.row();self.setup_ready(row)
            require(pc==self.entries[row['op']] and self.active is None,'Actual helper owner')
            require(self.output_stores==66 and self.mask_cursor==self.mask_length(row),'All original fresh output/mask stores')
            fp=row['op']>=25
            require(self.fp_cursor==(128 if fp else 0) and self.fp_read_cursor==(8 if fp else 0) and self.fp_seed_reads==(1 if fp else 0),'FP not elided on VL0/equal values/repeated calls')
            if row['si']==0:self.mask_groups+=1
            if fp:self.fp_calls+=1
            self.calls+=1;self.output_stores=self.mask_cursor=self.fp_cursor=self.fp_read_cursor=self.fp_seed_reads=0
            self.read_cursor=self.expected_cursor=self.id_cursor=0;self.completed_oracle=False
    def leave(self,pc,regs):
        if self.active is not None and self.path_cursor==len(self.path):
            require(pc==self.path[-1],'Phase closes at actual final retired instruction')
            if self.active=='mask':require(self.mask_cursor==self.mask_length(self.row()) and self.mask_pending is None,'Full16SD/selected SB with matching LBU')
            elif self.active=='fp':require(self.fp_cursor==128 and self.fp_read_cursor==8 and self.fp_seed_reads==1,'Full FP128 SD/eight table LD/actual seed')
            else:
                require(self.read_cursor==self.expected_cursor==66 and self.id_cursor==9 and regs.get(15)==0,'Final sticky decision after all66 pairs/nine IDs')
                self.completed_oracle=True
            self.active=None
    def effect(self,pc,rd):
        if pc==self.cmp['initial_zero']:
            require(self.active=='cmp' and rd==(15,0),'Exactly actual sticky register zero at call entry');self.flag_zero_count+=1
    def store(self,pc,insn,address,size,value):
        require(self.code.get(pc)==insn,'Actual scalar store code')
        if pc==self.BSS_PC:
            require(not self.boot_locked and size==8 and value==0 and address==self.next_bss and address+8<=self.s['__bss_end'],'Only exact ordered zero BSS')
            self.next_bss+=8;return
        out=self.s['out']
        if address<out+8208 and address+size>out:
            row=self.row();self.setup_ready(row)
            require(self.active is None and self.output_stores<66 and self.fp_cursor==(128 if row['op']>=25 else 0) and self.mask_cursor==self.mask_length(row),'Output only after full original setup')
            require((pc,address,size,value)==(self.init[self.output_stores],out+8*self.output_stores,8,91),'Exact66 typed64 fresh output SDs')
            self.output_stores+=1
        for key in ('a','b'):
            base=self.s[key]
            if address<base+8192 and address+size>base:
                row=self.row()
                if pc in self.fp_store_pcs:
                    self.setup_ready(row);require(self.active=='fp' and self.fp_read_cursor==8 and self.fp_seed_reads==1 and self.fp_cursor<128,'FP reads before ordered stores')
                    event=self.fp_paths[str(row['seed'])]['stores'][self.fp_cursor];bank=event['bank'];i=event['index']
                    require((pc,address,size,value)==(event['pc'],self.s[bank]+8*i,8,row[bank][i]),'FP exact128 SD site/bank/index/value/order')
                    self.fp_cursor+=1;self.fp_stores+=1
                else:
                    require(self.seed_cursor<len(self.seed) and self.completed_oracle and self.active is None,'Original seed phase')
                    seed,wpc,bank,offset,want=self.seed[self.seed_cursor]
                    require(self.calls==1995*seed and self.output_stores==self.mask_cursor==self.fp_cursor==0 and (pc,address,size,value)==(wpc,self.s[bank]+offset,8,want),'Original RNG all stores/overrides and cross-seed order')
                    self.seed_cursor+=1
        mask=self.s['mask']
        if address<mask+128 and address+size>mask:
            row=self.row();self.setup_ready(row);events=self.mask_paths[str(row['mode'])]['events']
            require(self.active=='mask' and self.mask_cursor<len(events) and row['si']==0,'Current original mask owner')
            e=events[self.mask_cursor]
            require((pc,address,size,value)==(e['pc'],mask+e['offset'],e['width'],e['value']),'Actual full clear/cumulative bitset order')
            require(self.mask_pending==(self.mask_cursor if size==1 else None),'Each selected SB has actual preceding LBU')
            self.mask_pending=None;self.mask_cursor+=1
            if size==8:self.mask_clear_stores+=1
            else:self.mask_bit_stores+=1
    def read(self,pc,address,size,value):
        if self.active=='mask':
            row=self.row();events=self.mask_paths[str(row['mode'])]['events']
            if self.mask_cursor<len(events) and pc==events[self.mask_cursor]['load']:
                e=events[self.mask_cursor]
                require(self.mask_cursor>=16 and self.mask_pending is None and (address,size,value)==(self.s['mask']+e['offset'],1,e['previous']),'Actual cumulative mask LBU after16SD')
                self.mask_pending=self.mask_cursor
        if self.active=='fp':
            row=self.row();path=self.fp_paths[str(row['seed'])];loadmap={x['pc']:x for x in path['loads']}
            if pc in loadmap:
                e=loadmap[pc];i=e['slot'];require(i==self.fp_read_cursor and (address,size)==(self.s['fp_inputs']+8*i,8),'Eight fresh ordered source table LD')
                # Constants are pinned once per observer, not host floating-point values.
                require(value==self.fp_inputs[i],'FP table bit pattern');self.fp_read_cursor+=1;self.fp_reads+=1
            else:
                asm=self.spec['asm'][str(pc)]
                if asm['op']=='ld' and asm['args']=='t3,144(sp)':
                    require(self.fp_seed_reads==0 and (address,size,value)==(self.s['__stack_top']-self.spec['main_frame']+144,8,row['seed']),'Actual per-call seed load, no cross-seed reuse')
                    self.fp_seed_reads+=1
        if pc in self.cmp_ids:
            require(self.active=='cmp' and self.id_cursor<9,'Owned ID load')
            r=self.rows[self.calls-1];i=self.id_cursor
            require(self.cmp_ids[pc]['block']==i and (address,size,value)==(self.s['e64m4_block_ids']+18*(self.calls-1)+2*i,2,r['ids'][i]),'Exact actual ordinal ID including ninth tail')
            self.id_cursor+=1;self.id_reads+=1
        if pc in self.cmp_loads:
            require(self.active=='cmp','Owned actual/dictionary load');e=self.cmp_loads[pc];r=self.rows[self.calls-1];i=e['word']
            if e['kind']=='actual':
                require(i==self.read_cursor==self.expected_cursor and (address,size,value)==(self.s['out']+8*i,8,r['words'][i]),'Actual full output/guard pair value')
                self.read_cursor+=1;self.output_reads+=1
            else:
                require(i==self.expected_cursor and self.read_cursor==i+1 and self.id_cursor==i//8+1,'Expected load after actual and its own ID')
                require((address,size,value)==(self.s['e64m4_dictionary']+64*r['ids'][i//8]+8*(i%8),8,r['words'][i]),'Actual expected dictionary address/value; no cache substitution')
                self.expected_cursor+=1;self.expected_reads+=1
    @property
    def fp_inputs(self):
        return (0xc020000000000000,0xc000000000000000,0x8000000000000000,0,0x3fe0000000000000,0x3ff0000000000000,0x4000000000000000,0x4020000000000000)
    def finish(self):
        require(self.active is None and self.completed_oracle and self.mask_pending is None,'Complete last scalar phases')
        require((self.calls,self.seed_cursor,self.output_stores,self.read_cursor,self.expected_cursor,self.id_cursor,self.output_reads,self.expected_reads,self.id_reads,self.beq_count,self.flag_zero_count,self.fp_cursor,self.fp_stores,self.fp_calls,self.fp_reads,self.mask_cursor,self.mask_groups,self.mask_clear_stores,self.mask_bit_stores)==
          (5985,552,0,66,66,9,395010,395010,53865,395010,5985,0,241920,1890,15120,0,2205,35280,77175),'Full original lifecycle, no partial acceptance')
