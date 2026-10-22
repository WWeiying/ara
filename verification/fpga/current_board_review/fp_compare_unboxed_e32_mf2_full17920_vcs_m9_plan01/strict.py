"""SoC RVFI observer. No Spike vector/log effects are synthesized as evidence."""
from collections import Counter
from specification import source, specification, model, csr, vector, offload, helper_owner
from scope import *

MASK=source.MASK
word=source.word

class Strict(source.Checker):
    def __init__(self,s=None,gold=None):
        s=dict(specification() if s is None else s)
        s['code']={int(k):v for k,v in s['code'].items()}
        super().__init__(s,model() if gold is None else gold)
        self.rows=0;self.cycle=-1;self.offloads=[];self.spilled=set()
        self.fpr_writebacks=0

    def helper(self,r,pair):
        op,i=pair;g=self.current();delta=2 if op>=4 else 0
        require(op==g['op'] and i==self.step and self.cap==3 and self.pre==6, 'Actual original helper order')
        rd,val=r['rd'],r['value']
        def returned(n,v,label): require((rd,val)==(n,v),label)
        if i==0:
            require(self.active is None and self.fresh==49 and self.input_reads==16 and
                    self.record_index==g['record_index'],'Full fresh setup before helper')
            require([self.regs.get(x) for x in range(10,18)]==
                    [self.a['a'],self.a['b'],self.a['output']+1,g['vl'],16,self.a['mask'],0,g['sticky']],
                    'Eight original arguments')
            require(self.regs.get(22)==word(self.memory,self.a['oracle_records']+8*g['record_index'],8)
                    and self.regs.get(23)==g['sticky'],'Caller record/sticky preserved')
            returned(30,0,'Actual saved fflags0')
            for n,values,width in [('a',g['a'],4),('b',g['b'],4),('mask',[g['mask_byte']]*128,1),('output',[91]*130,1)]:
                require(all(word(self.memory,self.a[n]+j*width,width)==v for j,v in enumerate(values)), 'Full initialized '+n)
            require(all(self.memory.get(self.a[n]+j)==0 for n in ('a','b') for j in range(64,4096)),
                    'Unmodified unused backing BSS')
            self.active=dict(read=False,vstart=None,flags=None);self.saved_flags=0
        if i in (1,6+delta,14+delta):
            expected=g['vl'] if i==6+delta else 16
            returned(5,expected,'Actual vset returned VL')
            self.csr.update(vl=expected,vtype=23,vstart=0)
        if op>=4 and i==6: returned(7,g['b'][0],'Raw scalar LWU original b0')
        if op>=4 and i==7:
            require(r['insn']==0xf2038053 and self.regs.get(7)==g['b'][0], 'FMV opcode/t2 source')
            returned(0,g['b'][0],'FPR committed writeback full64 ft0, not x0')
            self.fp[0]=val;self.fpr_writebacks+=1;self.raw_scalar_seeds[g['seed']]+=1
        if i==7+delta:
            require(rd==0 and self.regs.get(17)==g['sticky'],'Sticky CSR source')
            self.csr['fflags']=g['sticky']
        if i==8+delta:
            require((self.csr.get('vl'),self.csr.get('vtype'),self.csr.get('vstart'))==(g['vl'],23,0),
                    'Target context')
            if op>=4: require(self.fp.get(0)==g['b'][0],'Last committed FPR payload')
        if i==9+delta:
            returned(10,0,'Actual returned vstart');self.active['vstart']=0
        if i==10+delta:
            returned(6,g['flags'],'Original complete flags oracle');self.active['flags']=val
        if i==11+delta: returned(6,g['flags']<<32,'Shifted flags return')
        if i==12+delta: returned(10,g['flags']<<32,'Packed return status')
        if i==13+delta:
            require(rd==0 and self.regs.get(30)==self.saved_flags, 'Saved fflags restore operand')
            self.csr['fflags']=self.saved_flags
        contract=helper_owner(self.s,op,i,g)
        if contract:
            self.offloads.append(dict(pc=r['pc'],insn=r['insn'],kind=contract[0],required=contract[1],
                                      call=self.calls,helper_index=i))
        self.helper_counts[op,i]+=1;self.step=(self.step+1)%len(self.s['helpers'][op])

    def consume(self,row):
        self.rows+=1
        require(int(row['trap'])==0,'Unexpected architectural trap')
        cyc=int(row['cycle']);require(cyc>=self.cycle,'Cycle reversal');self.cycle=cyc
        if row['event']!='retire':
            require(row['event'] in ('cvx_req','cvx_resp','arch_start','uop_alloc','uop_done'),'Unknown event')
            return
        pc,c=int(row['pc'],16),int(row['insn'],16)
        rd,val=int(row['rd']),int(row['rd_wdata'],16)
        address,rm,wm,wd=(int(row[k],16) for k in ('mem_addr','mem_rmask','mem_wmask','mem_wdata'))
        require(int(row['order'])==self.retired,'Retire continuity')
        self.retired+=1
        self.current_context=dict(row=self.rows,retire=self.retired,completed=self.calls,pc=hex(pc),step=self.step,fresh=self.fresh)
        require(pc in self.code and c==int(self.code[pc]['insn'],16),'Actual SoC PC/code')
        if self.exited:
            require(pc==self.s['park'] and c==0xa001 and rd==rm==wm==0,'Post-CTRL pure park')
            self.parks+=1;return
        require(pc==(0x80000000 if self.nextpc is None else self.nextpc),'Actual scalar/helper control flow')
        require(pc not in self.s['failure_pcs'],'Original failure/diagnostic path')
        pair=self.lookup.get(pc)
        if self.step: require(pair==(self.current()['op'],self.step),'Missing/repeated helper instruction')
        if 0<self.cap<3: require(pc==self.s['capacity'][self.cap]['pc'],'Capacity contiguous3')
        if pc==self.s['caller_record']:
            require(self.active is not None and self.regs.get(22)==word(self.memory,self.a['oracle_records']+8*self.current()['record_index'],8),'Caller record preserved')
        if pc==self.s['caller_flags']:
            require(self.active is not None and (rd,val)==(14,self.current()['flags']),'Caller flags sticky OR')
        if csr(c) and pair is None:
            require(self.pre<6 and pc==self.s['prelude'][self.pre] and not self.calls and self.cap==0,'Only exact bootstrap CSR')
            src=(c>>15)&31;operand=src if c&(1<<14) else self.regs.get(src)
            if self.pre<5:
                require(operand==[0,self.a['trap_entry'],0x6600,0,0][self.pre] and rd==0,'Bootstrap CSR operand')
                if self.pre==3: self.csr.update(fflags=0,frm=0)
                if self.pre==4: self.csr['vstart']=0
            else: require((rd,val)==(14,128),'Actual vlenb128')
            self.pre+=1
        if pc in self.capmap:
            i=self.capmap[pc];require(i==self.cap and self.pre==6 and not self.calls,'Capacity exactly once')
            if i==0: require((rd,val)==(5,MASK),'Capacity AVL')
            if i==1: require((rd,val)==(10,16),'Capacity actual16')
            self.cap+=1
        if vector(c): require(pair is not None or pc==self.s['capacity'][1]['pc'],'RVV outside original windows')
        if pair: self.helper(dict(pc=pc,insn=c,rd=rd,value=val),pair)
        elif offload(c): self.offloads.append(dict(pc=pc,insn=c,kind='configuration',required=False,call=None,helper_index=None))
        desc=source.base.memory_desc(c)
        if desc:
            width=desc['size'];low=(1<<(8*width))-1
            base=self.regs.get(desc['base'])
            require(base is not None and address==(base+desc['offset'])&MASK,'Scalar effective address')
            be=((1<<width)-1)<<(address%8)
            if desc['kind']=='write':
                require(wm==be and rm==0 and rd==0,'Scalar write BE/schema')
                value=wd&low;src=self.regs.get(desc['register'])
                if src is None:
                    require(pc in self.opaque and pc not in self.spilled and self.calls==self.fresh==0,
                            'Unknown store outside exact first ABI spill')
                    self.spilled.add(pc)
                else: require(value==src&low,'Scalar store source')
                if pc==self.s['bss_store']:
                    require(address==self.a['__bss_start']+8*self.bss and address+8<=self.a['__bss_end'] and
                            width==8 and value==0 and self.pre==5 and self.cap==0,'Exact ordered BSS zero')
                    self.bss+=1
                elif pc in self.freshmap: self.setup_store(pc,address,value,width)
                else:
                    areas=[(self.a[n],self.a[n]+size) for n,size in [('a',4096),('b',4096),('mask',128),('output',130)]]
                    require(not any(address<hi and address+width>lo for lo,hi in areas),'Unexpected original array write')
                if address==0xc0000000:
                    require(pc in self.s['uart_stores'] and width==1,'Actual UART byte site')
                    self.console.append(value)
                    require(not source.base.VETO.search(self.console.decode('ascii')),'Original raw failure veto')
                elif address==0xd0000000:
                    require(pc==self.s['exit_store'] and width==8 and value==0 and self.regs.get(10)==0,'Actual CTRL success0, not HTIF1')
                    self.validate_complete();self.exited=True;self.exit_count=self.retired
                else:
                    stack=self.a['__stack_top']
                    require(self.a['__bss_start']<=address and address+width<=self.a['__bss_end'] or
                            stack-65536<=address and address+width<=stack,'Store outside BSS/stack/MMIO')
                    for j in range(width): self.memory[address+j]=(value>>(8*j))&255
            else:
                require(rm==be and wm==0 and rd==desc['register'] and rd!=0,'Scalar read BE/destination')
                if pc==self.s['output_read']:
                    self.oracle(address,val,width)
                    # Only observed output bytes become shadow data, never invented vector effects.
                    for j in range(width): self.memory[address+j]=(val>>(8*j))&255
                else:
                    expected=word(self.memory,address,width)
                    f=(desc['expanded']>>12)&7
                    if f<4 and width<8 and expected>>(8*width-1): expected|=MASK^low
                    require(val==expected,'Actual scalar read vs initialized memory')
                    if pc in self.inputmap: self.input_load(pc,address,val,width)
                    elif pc==self.s['record_load']: self.record_load(address,val,width)
                    elif self.a['output']<=address<self.a['output']+130:
                        raise ValueError('Unexpected scalar output read')
        elif not vector(c): require(rm==wm==0,'Nonmemory scalar has memory side effect')
        if pc==self.s['main_call']: require(self.bss*8==self.s['BSS_bytes'],'Complete BSS before main')
        nxt=self.next_address(dict(pc=pc))
        if c==0xf2038053:
            require(pair is not None and pair[0]>=4 and pair[1]==7,'FPR move only original helper')
        elif rd: self.regs[rd]=val
        self.regs[0]=0;self.nextpc=nxt

    def validate_complete(self):
        require(self.calls==17920 and self.active is None and self.step==0 and self.fresh==self.input_reads==0,
                'Full17920 complete, not prefix')
        require(self.pre==6 and self.cap==3 and self.record_loads==2240,'Full bootstrap/capacity/records')
        require(self.counts==dict(fresh_stores=878080,input_LD=286720,output_LWU=17920),'Exact source access totals')
        require(all(self.helper_counts[op,i]==1792 for op in range(10) for i in range(len(self.s['helpers'][op]))),
                'All original185 helper instructions full multiplicity')
        require(sum(self.helper_counts.values())==326144 and self.raw_scalar_seeds=={i:336 for i in range(32)},
                'Full dynamic helper/raw scalar counts')
        expected='BOARD_CASE_BEGIN '+NAME+'\n'+MARKER+'\nBOARD_CASE_PASS '+NAME+'\nBOARD_REPLAY_PASS\n'
        require(self.console.decode('ascii')==expected,'Exact original success console')
        require(self.fpr_writebacks==10752,'All original FPR committed writes')

    def finish(self):
        require(self.exited,'EOF without full SoC CTRL success')
        self.validate_complete()
        return dict(status='FULL17920_RVFI_SOURCE_PARENT_ACCEPTED_NOT_LINUX',calls=self.calls,
            result_bits=286720,guards=35840,flags=17920,vstarts=17920,
            helper_instructions=sum(self.helper_counts.values()),capacity_instructions=self.cap,
            fresh_stores=self.counts['fresh_stores'],input_LD=self.counts['input_LD'],
            output_LWU=self.counts['output_LWU'],record_LD=self.record_loads,
            FPR_committed_writebacks=self.fpr_writebacks,raw_scalar_seed_counts=dict(self.raw_scalar_seeds),
            FPR_evidence='Committed writeback payload; not physical FPR readback or accelerator operand snapshot',
            rows=self.rows,retired=self.retired,last_cycle=self.cycle,firmware_to_CTRL=self.exit_count,
            console=self.console.decode('ascii'),park_rows=self.parks,full_parent=True,linux=False)
