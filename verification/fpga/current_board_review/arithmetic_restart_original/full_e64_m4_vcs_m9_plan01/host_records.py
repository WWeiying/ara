"""Constructed RVFI Host boundary rows, not captured execution or ISA proof."""
import struct
from pathlib import Path
import checker as c

class Builder:
    def __init__(self,spec):
        self.spec=spec;self.s=spec['backend']['symbols'];self.code={int(k):v for k,v in spec['backend']['code'].items()}
        self.memory={}
        self.linked=spec['source_lifecycle'];self.asm=self.linked['asm']
        for name,file in [('e64m4_dictionary','dictionary64.bin'),('e64m4_block_ids','indices_u16le.bin'),('fp_inputs','fp_inputs8_u64le.bin')]:
            path=c.REF.parents[1]/'full_e64_m4_source_model01/generated01'/file
            self.memory.update({self.s[name]+i:b for i,b in enumerate(path.read_bytes())})
        self.order=0;self.arch=0;self.regs={i:0 for i in range(32)}
        self.setters={}
        excluded=set(spec['failure_pcs'])|{spec['body_start'],self.s['main']}
        for path in list(self.linked['mask_paths'].values())+list(self.linked['FP_paths'].values()):excluded.update(path['pcs'])
        excluded.update(self.linked['comparator']['all_equal_pcs'])
        excluded.update(e['li'] for e in self.linked['comparator']['sites'])
        self.excluded=excluded
        for pc,insn in self.code.items():
            if pc not in excluded and insn&3==3 and insn&127 in (0x13,0x1b,0x17,0x37,0x33,0x3b):
                rd=(insn>>7)&31
                if rd:self.setters.setdefault(rd,pc)

        self.stores={}
        for pc,insn in self.code.items():
            desc=c.memory_op(insn)
            if pc not in excluded and spec['body_start']<pc<spec['body_end'] and pc not in {x[0] for x in spec['init_stores']} and desc and desc['kind']=='write' and desc['base']!=desc['register']:
                if desc['base'] in self.setters and desc['register'] in self.setters:
                    self.stores.setdefault(desc['size'],(pc,desc))

    def row(self,pc,rd=0,result=0,addr=0,rm=0,wm=0,data=0):
        row=dict(cycle=str(self.order+1),event='retire',order=str(self.order),port='0',trans_id='-1',pc=f'{pc:016x}',
            insn=f'{self.code[pc]:08x}',rd=str(rd),rd_wdata=f'{result&c.MASK64:016x}',mem_addr=f'{addr:016x}',
            mem_rmask=f'{rm:02x}',mem_wmask=f'{wm:02x}',mem_wdata=f'{data&c.MASK64:016x}',trap='0')
        if wm:
            size=c.memory_op(self.code[pc])['size']
            self.memory.update({addr+i:(data>>(8*i))&255 for i in range(size)})
        self.order+=1
        if rd:self.regs[rd]=result&c.MASK64
        return row

    def setreg(self,reg,value):return self.row(self.setters[reg],reg,value)

    def register_rows(self,reg,value):
        c.require(reg in self.setters,'No arbitrary unknown Host GPR setter')
        yield self.setreg(reg,value)

    def write(self,address,value,size,pc=None):
        if pc is None:pc,desc=self.stores[size]
        else:desc=c.memory_op(self.code[pc])
        yield self.setreg(desc['base'],address-desc['offset'])
        if desc['register']:yield from self.register_rows(desc['register'],value)
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
        body=self.spec['body_start'];assert code[body]==0x7129 and code[body+2]==0xfa22 and code[body+4]==0xfe06
        yield self.row(body,2,s['__stack_top']-320)
        for pc0 in (body+2,body+4):
            desc=c.memory_op(code[pc0]);address=self.regs[2]+desc['offset']
            yield self.row(pc0,addr=address,wm=255,data=self.regs[desc['register']])
        yield self.row(body+6,1,body+10)

    def phase(self,pcs):
        names={n:i for i,n in enumerate('zero ra sp gp tp t0 t1 t2 s0 s1 a0 a1 a2 a3 a4 a5 a6 a7 s2 s3 s4 s5 s6 s7 s8 s9 s10 s11 t3 t4 t5 t6'.split())}
        for pc in pcs:
            x=self.asm[str(pc)];op=x['op'];args=[a.strip() for a in x['args'].split(',')]
            desc=c.memory_op(self.code[pc])
            if desc:
                address=(self.regs[desc['base']]+desc['offset'])&c.MASK64;size=desc['size'];enable=((1<<size)-1)<<(address%8)
                if desc['kind']=='write':
                    yield self.row(pc,addr=address,wm=enable,data=self.regs[desc['register']])
                else:
                    c.require(all(address+i in self.memory for i in range(size)),'Host phase unknown actual memory '+hex(pc)+' '+hex(address))
                    value=sum(self.memory[address+i]<<(8*i) for i in range(size))
                    yield self.row(pc,desc['register'],c.loaded_value(value,size,desc['signed']),addr=address,rm=enable)
            elif op in ('beq','bnez','j'):
                yield self.row(pc)
            else:
                rd=names[args[0]]
                if op=='auipc':
                    imm=int(args[1],0)<<12;imm-=1<<32 if imm&(1<<31) else 0;value=pc+imm
                elif op=='addi':value=self.regs[names[args[1]]]+int(args[2],0)
                elif op=='add':value=self.regs[names[args[1]]]+self.regs[names[args[2]]]
                elif op=='slli':value=self.regs[names[args[1]]]<<int(args[2],0)
                elif op=='ori':value=self.regs[names[args[1]]]|int(args[2],0)
                elif op=='li':value=int(args[1],0)
                else:raise ValueError('Unmodeled Host scalar phase '+str(x))
                yield self.row(pc,rd,value)

    def records(self):
        yield from self.abi();s=self.s
        for j,x in enumerate(self.spec['backend']['helpers']['capacity']):
            yield self.row(x['pc'],5 if j==0 else 10 if j==1 else 0,c.MASK64 if j==0 else 64 if j==1 else 0)
        previous=None;seed_cursor=0;seed_events=c.source_lifecycle.seed_schedule(self.linked['seed_pc'])
        for g in c.model():
            seed_first=previous is None or previous['seed']!=g['seed']
            group_first=previous is None or any(previous[k]!=g[k] for k in ('seed','op','li','mode'))
            if seed_first:
                while seed_cursor<184*(g['seed']+1):
                    _,pc,key,offset,value=seed_events[seed_cursor]
                    yield from self.write(s[key]+offset,value,8,pc);seed_cursor+=1
            if group_first:
                yield self.setreg(20,s['mask'])
                yield from self.phase(self.linked['mask_paths'][str(g['mode'])]['pcs'])
            if g['op']>=25:
                yield from self.write(s['__stack_top']-320+144,g['seed'],8,0x80001b04)
                yield self.setreg(21,s['a']);yield self.setreg(22,s['b'])
                yield from self.phase(self.linked['FP_paths'][str(g['seed'])]['pcs'])
            for pc,_,size,offset in self.spec['init_stores']:yield from self.write(s['out']+offset,91,8,pc)
            args=[s['a'],s['b'],s['out']+8,g['vl'],64,s['mask'],g['vstart']]
            for reg,value in enumerate(args,10):yield self.setreg(reg,value)
            for j,x in enumerate(self.spec['backend']['helpers'][f'op_{g["op"]}']):
                rd,value=0,0
                if j in (0,5,10):rd,value=5,g['vl'] if j==5 else 64
                elif j==6:rd,value=28,7
                elif j==9:rd,value=10,0
                yield self.row(x['pc'],rd,value)
            # Synthetic Host expected vector writeback, not a claim of executed ISA.
            self.memory.update({s['out']+i:b for i,b in enumerate(g['raw'])})
            yield self.setreg(8,s['out'])
            yield from self.phase(self.linked['comparator']['all_equal_pcs'])
            for name,value in (('checks',g['ordinal']+1),('elements',(g['ordinal']+1)*64)):
                yield from self.write(s[name],value,8)
            previous=g
        for byte in (c.marker()+'\n').encode():yield from self.write(self.spec['uart'],byte,1,0x80002372)
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
                required=bool(site and site[0]!='capacity' and (site[1] in (1,2,3,4,11) or site[1]==8 and c.target_required(insn,gold[calls])))
                if required:
                    yield dict(event,event='uop_alloc',port='0');yield dict(event,event='uop_done',port='0')
                yield dict(event,event='cvx_resp');self.arch+=1
            yield row
