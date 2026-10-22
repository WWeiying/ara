"""Constructed RVFI Host boundary rows, not captured execution or ISA proof."""
import checker as c

class Builder:
    def __init__(self,spec):
        self.spec=spec;self.s=spec['backend']['symbols'];self.code={int(k):v for k,v in spec['backend']['code'].items()}
        self.order=0;self.arch=0;self.regs={i:0 for i in range(32)}
        self.setters={}
        excluded=set(spec['failure_pcs'])|{spec['body_start'],self.s['main']}
        for pc,insn in self.code.items():
            if pc not in excluded and insn&3==3 and insn&127 in (0x13,0x1b,0x17,0x37,0x33,0x3b):
                rd=(insn>>7)&31
                if rd:self.setters.setdefault(rd,pc)
        self.stores={}
        for pc,insn in self.code.items():
            desc=c.memory_op(insn)
            if spec['body_start']<pc<spec['body_end'] and pc not in {x[0] for x in spec['init_stores']} and desc and desc['kind']=='write' and desc['base']!=desc['register']:
                if desc['base'] in self.setters and desc['register'] in self.setters:
                    self.stores.setdefault(desc['size'],(pc,desc))

    def row(self,pc,rd=0,result=0,addr=0,rm=0,wm=0,data=0):
        row=dict(cycle=str(self.order+1),event='retire',order=str(self.order),port='0',trans_id='-1',pc=f'{pc:016x}',
            insn=f'{self.code[pc]:08x}',rd=str(rd),rd_wdata=f'{result&c.MASK64:016x}',mem_addr=f'{addr:016x}',
            mem_rmask=f'{rm:02x}',mem_wmask=f'{wm:02x}',mem_wdata=f'{data&c.MASK64:016x}',trap='0')
        self.order+=1
        if rd:self.regs[rd]=result&c.MASK64
        return row

    def setreg(self,reg,value):return self.row(self.setters[reg],reg,value)

    def write(self,address,value,size,pc=None):
        if pc is None:pc,desc=self.stores[size]
        else:desc=c.memory_op(self.code[pc])
        yield self.setreg(desc['base'],address-desc['offset'])
        if desc['register']:yield self.setreg(desc['register'],value)
        yield self.row(pc,addr=address,wm=((1<<size)-1)<<(address%8),data=value)

    def read(self,address,value,size,pc):
        desc=c.memory_op(self.code[pc]);assert desc['size']==size
        yield self.setreg(desc['base'],address-desc['offset'])
        yield self.row(pc,desc['register'],value,addr=address,rm=((1<<size)-1)<<(address%8))

    def abi(self):
        # This exact compiled bootstrap and first arithmetic ABI save has
        # independently decoded immediates/results, not arbitrary setter rows.
        pc=self.s['_start'];code=self.code;s=self.s
        for address in (pc,pc+4,pc+8,pc+12,pc+16,pc+20,pc+24,pc+28,pc+32,pc+34,pc+38,pc+42,pc+46,pc+50,pc+54,pc+58,pc+62):
            insn=code[address];rd=(insn>>7)&31;opcode=insn&127
            if opcode==0x17:value=address+((insn&0xfffff000)-(1<<32) if insn&0x80000000 else insn&0xfffff000)
            elif opcode in (0x13,0x1b):
                immediate=insn>>20;immediate-=4096 if immediate&2048 else 0
                value=self.regs[(insn>>15)&31]+immediate
                if opcode==0x1b:value=(value&0xffffffff)-(1<<32 if value&0x80000000 else 0)
            elif opcode==0x73:rd=(insn>>7)&31;value=0xa00000000 if insn==0x3002a073 else 0
            elif insn==0x6299:rd=5;value=0x6000
            else:raise ValueError('Unexpected actual startup ABI instruction')
            yield self.row(address,rd,value)
        assert self.regs[3]==s['__global_pointer$'] and self.regs[2]==s['__stack_top']
        assert self.regs[5]==s['__bss_start'] and self.regs[6]==s['__bss_end']
        for address in range(s['__bss_start'],s['__bss_end'],8):
            yield self.row(pc+66)
            yield self.row(pc+70,addr=address,wm=255,data=0)
            yield self.row(pc+74,5,address+8)
            yield self.row(pc+76)
        yield self.row(pc+66);yield self.row(pc+78,1,pc+82)
        yield self.row(s['main'])
        body=self.spec['body_start'];assert code[body]==0x714d and code[body+2]==0xe686
        yield self.row(body,2,s['__stack_top']-336)
        for pc in (body+2,):
            desc=c.memory_op(code[pc]);address=self.regs[2]+desc['offset']
            yield self.row(pc,addr=address,wm=255,data=self.regs[desc['register']])
        yield self.row(body+4,1,body+8)

    def records(self):
        yield from self.abi();s=self.s
        for j,x in enumerate(self.spec['backend']['helpers']['capacity']):
            yield self.row(x['pc'],5 if j==0 else 10 if j==1 else 0,c.MASK64 if j==0 else 64 if j==1 else 0)
        previous=None
        for g in c.model():
            seed_first=previous is None or previous['seed']!=g['seed']
            group_first=previous is None or any(previous[k]!=g[k] for k in ('seed','op','li','mode'))
            if seed_first:
                for seed,pc,bank,offset,value in c.lifecycle.seed_schedule():
                    if seed==g['seed']:yield from self.write(s[bank]+offset,value,4,pc)
                cache=s['__stack_top']-336+192
                for k in range(8):
                    value=c.lifecycle.FP_INPUTS[(g['seed']+k)%8]
                    yield from self.read(s['fp_inputs']+4*((g['seed']+k)%8),c.lifecycle.lw_value(value),4,c.lifecycle.CACHE_LOAD_PC)
                    yield from self.write(cache+4*k,value,4,c.lifecycle.CACHE_STORE_PC)
            if group_first:
                previous_mask={}
                for pc,offset,size,value,load in c.lifecycle.mask_schedule(g['mode']):
                    if load is not None:
                        yield from self.read(s['mask']+offset,previous_mask.get(offset,0),1,load)
                    yield from self.write(s['mask']+offset,value,size,pc)
                    if size==1:previous_mask[offset]=value
            if g['op']>=25:
                cache=s['__stack_top']-336+192
                for j,pc in enumerate(c.lifecycle.FP_PC):
                    i,bank=divmod(j,2);key=('a','b')[bank];slot=(3*i if bank else i)%8
                    yield from self.read(cache+4*slot,c.lifecycle.lw_value(g[key][i]),4,c.lifecycle.FP_LOAD_PC[j])
                    yield from self.write(s[key]+i*4,g[key][i],4,pc)
            for pc,_,size,offset in self.spec['init_stores']:
                yield from self.write(s['out']+offset,c.lifecycle.SENTINEL,size,pc)
            args=[s['a'],s['b'],s['out']+4,g['vl'],64,s['mask'],g['vstart']]
            for reg,value in enumerate(args,10):yield self.setreg(reg,value)
            for j,x in enumerate(self.spec['backend']['helpers'][f'op_{g["op"]}']):
                rd,value=0,0
                if j in (0,5,10):rd,value=5,g['vl'] if j==5 else 64
                elif j==6:rd,value=28,7
                elif j==9:rd,value=10,0
                yield self.row(x['pc'],rd,value)
            for pc,_,size,offset in self.spec['oracle_reads']:
                yield from self.read(s['out']+offset,int.from_bytes(g['raw'][offset:offset+size],'little'),size,pc)
            for name,value in (('checks',g['ordinal']+1),('elements',(g['ordinal']+1)*64)):
                yield from self.write(s[name],value,8)
            previous=g
        for byte in (c.marker()+'\n').encode():yield from self.write(self.spec['uart'],byte,1,self.spec['uart_store'])
        yield from self.write(self.spec['ctrl'],0,8,self.spec['exit_store'])
        yield self.row(self.spec['park'])

    def protocol_rows(self,rows):
        gold=c.model();calls=-1;lookup={x['pc']:(name,j) for name,w in self.spec['backend']['helpers'].items() for j,x in enumerate(w)}
        for row in rows:
            insn=int(row['insn'],16);site=lookup.get(int(row['pc'],16))
            if site and site[0]!='capacity' and site[1]==0:calls+=1
            if c.mature.transport.transport.vector(insn):
                event=dict(row,order=str(self.arch),port='-1',trans_id='0',rd='0',rd_wdata='0000000000000000',
                    pc='0000000000000000',mem_addr='0000000000000000',mem_rmask='00',mem_wmask='00',mem_wdata='0000000000000000')
                yield dict(event,event='cvx_req');yield dict(event,event='arch_start')
                required=bool(site and site[0]!='capacity' and (site[1] in (1,2,3,4,11) or site[1]==8 and c.target_required(insn,gold[calls],self.spec)))
                if required:
                    yield dict(event,event='uop_alloc',port='0');yield dict(event,event='uop_done',port='0')
                yield dict(event,event='cvx_resp');self.arch+=1
            yield row
