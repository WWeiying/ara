"""RVFI adapter; inherit proven source events, decode and control flow.

Vector payload is not available here. Full actual scalar output reads and CSR
returns supply architectural evidence; no reference vector effects are invented.
"""
from specification import *
from scope import *
MASK=isa.MASK
class Strict(source.Checker):
    def __init__(self,s=None):
        super().__init__(source.config())
        self.s=dict(specification() if s is None else s);self.s['code']={int(k):v for k,v in self.s['code'].items()}
        self.a=self.s['symbols'];self.code=self.s['code'];self.memory=isa.elf_image(ELF)
        self.helpers=self.s['helpers'];self.lookup={r['pc']:(o,i) for o,h in enumerate(self.helpers) for i,r in enumerate(h)}
        self.capmap={r['pc']:i for i,r in enumerate(self.s['capacity'])};self.opaque=set(self.s['opaque'])
        self.soc_stores={p-14 for p in self.stores};self.soc_reads={p-14 for p in self.readmap}
        self.rows=0;self.cycle=-1;self.offloads=[];self.spilled=set();self.gold=model()
    def next_address(self,r):
        if self.code[r['pc']]['op']=='jr':
            require(r['pc']==self.s['switch'] and 15 in self.regs,'Actual switch target');return self.regs[15]&~1
        return isa.Checker.next_address(self,r)
    def helper(self,r,pair):
        op,i=pair;g=self.g();rd,val=r['rd'],r['value']
        require((op,i)==(g['op'],self.step) and self.cap==3 and self.pre==6,'Original helper order')
        def returned(reg,want):require((rd,val)==(reg,want),'Actual helper scalar return/CSR')
        if i==0:
            require(self.active is None and self.fresh==18 and self.counts['input_SH']==16*(g['scenario']+1) and self.counts['seed_SD']==16*(g['scenario']+1),'Original full setup before helper')
            require([self.regs.get(x) for x in range(10,18)]==[self.a['input'],self.a['seed'],self.a['output']+8,g['vl'],16,self.a['mask'],g['rm'],g['sticky']],'Eight original arguments')
            for n,vs,w in [('input',[source.original_input(self.s['bits'],g['scenario'],j) for j in range(16)]+[0]*496,2),('seed',[g['seed']]*64,2),('mask',[g['mask']]*64,1),('output',[91]*144,1)]:
                require(all(isa.word(self.memory,self.a[n]+j*w,w)==v for j,v in enumerate(vs)),'Full source initialized/backing '+n)
            self.active=dict(vstart=None,flags=None)
        if i in (0,3,6,18):
            vl,typ=(64,8) if i in (0,18) else (16 if i==3 else g['vl'],14)
            returned(5,vl);self.csr.update(vl=vl,vtype=typ,vstart=0)
        if i in (7,8):
            returned(29 if i==7 else 30,0);require(self.csr.get('frm' if i==7 else 'fflags')==0,'Saved original CSR')
        if i in (9,10,16,17):
            name='frm' if i in (9,16) else 'fflags';reg=16 if i==9 else 17 if i==10 else 29 if i==16 else 30
            want=g['rm'] if i==9 else g['sticky'] if i==10 else 0
            require(rd==0 and self.regs.get(reg)==want,'Actual CSR write/restore operand');self.csr[name]=want
        if i==11:require((self.csr.get('vl'),self.csr.get('vtype'),self.csr.get('vstart'),self.csr.get('frm'),self.csr.get('fflags'))==(g['vl'],14,0,g['rm'],g['sticky']),'Actual target context')
        if i in (12,13,14,15):
            returned(10 if i in (12,15) else 6,0 if i==12 else g['flags'] if i==13 else g['flags']<<32)
            if i==12:self.active['vstart']=0
            if i==13:self.active['flags']=g['flags'];self.flags_seen|=g['flags']
        q=helper_owner(self.s,op,i,g)
        if q:self.offloads.append(dict(pc=r['pc'],insn=r['insn'],kind=q[0],required=q[1],call=self.calls,helper_index=i))
        self.hcounts[op,i]+=1;self.step=(self.step+1)%21
    def consume(self,row):
        self.rows+=1
        require(int(row['trap'])==0,'Unexpected architectural trap')
        cyc=int(row['cycle']);require(cyc>=self.cycle,'Cycle reversal');self.cycle=cyc
        if row['event']!='retire':
            require(row['event'] in ('cvx_req','cvx_resp','arch_start','uop_alloc','uop_done'),'Unknown event');return
        pc,c=int(row['pc'],16),int(row['insn'],16);rd,val=int(row['rd']),int(row['rd_wdata'],16)
        address,rm,wm,wd=(int(row[k],16) for k in ('mem_addr','mem_rmask','mem_wmask','mem_wdata'))
        require(int(row['order'])==self.retired,'Retire continuity');self.retired+=1
        self.current_context=dict(row=self.rows,retire=self.retired,completed=self.calls,pc=hex(pc),step=self.step,fresh=self.fresh)
        require(pc in self.code and c==int(self.code[pc]['insn'],16),'Actual SoC PC/code')
        if self.exited:
            require(pc==self.s['park'] and c==0xa001 and rd==rm==wm==0,'Post-CTRL pure park');self.parks+=1;return
        require(pc==(0x80000000 if self.nextpc is None else self.nextpc),'Actual scalar/helper control flow')
        require(pc not in self.s['failure_pcs'],'Original failure/diagnostic path')
        pair=self.lookup.get(pc)
        if self.step:require(pair==(self.g()['op'],self.step),'Contiguous original helper21')
        if 0<self.cap<3:require(self.capmap.get(pc)==self.cap,'Capacity contiguous3')
        if csr(c) and pair is None:
            require(self.pre<6 and pc==self.s['prelude'][self.pre] and self.calls==self.cap==0,'Exact bootstrap CSR')
            src=(c>>15)&31;operand=src if c&(1<<14) else self.regs.get(src)
            if self.pre<5:
                require(operand==[0,self.a['trap_entry'],0x6600,0,0][self.pre] and rd==0,'Bootstrap CSR operand')
                if self.pre==3:self.csr.update(frm=0,fflags=0)
                if self.pre==4:self.csr['vstart']=0
            else:require((rd,val)==(8,128),'Actual vlenb128')
            self.pre+=1
        if pc in self.capmap:
            i=self.capmap[pc];require(i==self.cap and self.pre==6 and not self.calls,'Capacity once')
            if i==0:require((rd,val)==(5,MASK),'Capacity AVL')
            if i==1:require((rd,val)==(10,16),'Actual capacity16')
            self.cap+=1
        if vector(c):require(pair is not None or pc==self.s['capacity'][1]['pc'],'No extra RVV')
        if pair:self.helper(dict(pc=pc,insn=c,rd=rd,value=val),pair)
        elif offload(c):self.offloads.append(dict(pc=pc,insn=c,kind='configuration',required=False,call=None,helper_index=None))
        desc=isa.memory_desc(c)
        if desc:
            w=desc['size'];low=(1<<(8*w))-1;b=self.regs.get(desc['base'])
            require(b is not None and address==(b+desc['offset'])&MASK,'Actual scalar effective address');be=((1<<w)-1)<<(address%8)
            if desc['kind']=='write':
                require(wm==be and rm==0 and rd==0,'Scalar write BE/schema');value=wd&low;src=self.regs.get(desc['register'])
                if src is None:
                    require(pc in self.opaque and pc not in self.spilled and self.calls==self.fresh==0,'Exact first opaque ABI spill');self.spilled.add(pc)
                else:require(value==src&low,'Scalar store operand')
                if pc==self.s['bss_store']:
                    require((address,value,w)==(self.a['__bss_start']+8*self.bss,0,8) and address+8<=self.a['__bss_end'] and self.pre==5 and self.cap==0,'Ordered zero BSS');self.bss+=1
                elif pc in self.soc_stores or pc==0x80000238:self.setup_store(pc+14,address,value,w)
                else:require(not any(address<self.a[n]+size and address+w>self.a[n] for n,size in [('input',1024),('seed',128),('mask',64),('output',144)]),'Unexpected business store')
                if address==0xc0000000:
                    require(pc in self.s['uart_stores'] and w==1,'Actual UART SB');self.console.append(value)
                    require(not source.re.search(r'DETAIL|FAIL|TRAP|MISMATCH',self.console.decode('ascii')),'Raw failure veto')
                elif address==0xd0000000:
                    require(pc==self.s['exit_store'] and w==8 and value==0 and self.regs.get(10)==0,'Actual CTRL0 not HTIF1');self.validate_complete();self.exited=True;self.exit_count=self.retired
                else:
                    stack=self.a['__stack_top']
                    require(self.a['__bss_start']<=address and address+w<=self.a['__bss_end'] or stack-65536<=address and address+w<=stack,'Store outside BSS/stack/MMIO')
                    self.memory.update({address+j:(value>>(8*j))&255 for j in range(w)})
            else:
                require(rm==be and wm==0 and rd==desc['register'] and rd!=0,'Scalar load BE/destination')
                if pc in self.soc_reads:
                    self.oracle(pc+14,address,val,w)
                    self.memory.update({address+j:(val>>(8*j))&255 for j in range(w)})
                else:
                    expected=isa.word(self.memory,address,w)
                    if ((desc['expanded']>>12)&7)<4 and w<8 and expected>>(8*w-1):expected|=MASK^low
                    require(val==expected,'Scalar load vs initialized data')
                    if pc in (0x80000330,0x80000332):self.fixture_read(pc+14,address,val,w)
                    elif self.a['output']<=address<self.a['output']+144:raise ValueError('Unexpected output load')
        elif not vector(c):require(rm==wm==0,'Nonmemory scalar side effect')
        if pc==self.s['main_call']:require(self.bss*8==self.a['__bss_end']-self.a['__bss_start'],'Complete BSS before main')
        nxt=self.next_address(dict(pc=pc))
        if rd:self.regs[rd]=val
        self.regs[0]=0;self.nextpc=nxt
    def finish(self):
        require(self.exited,'EOF without full actual CTRL success');self.validate_complete()
        return dict(status='FULL6720_RVFI_SOURCE_PARENT_ACCEPTED_NOT_LINUX',calls=self.calls,output_bytes=967680,flags=6720,vstarts=6720,
                    helper_instructions=sum(self.hcounts.values()),capacity_instructions=self.cap,events=dict(self.counts),flags_seen=self.flags_seen,
                    rows=self.rows,retired=self.retired,last_cycle=self.cycle,firmware_to_CTRL=self.exit_count,park_rows=self.parks,
                    console=self.console.decode('ascii'),full_parent=True,linux=False,vector_payload_observed=False)
