"""Synthetic Host rows at actual SoC PCs; not execution evidence."""
import checker as c

FIELDS=('cycle','event','order','port','trans_id','pc','insn','rd','rd_wdata','mem_addr','mem_rmask','mem_wmask','mem_wdata','trap')

def records(spec,mutation=None,limit=None):
    s=spec['backend']['symbols'];code={int(k):v for k,v in spec['backend']['code'].items()}
    windows=spec['backend']['helpers'];helperpcs={x['pc'] for w in windows.values() for x in w}
    gold=c.read(c.REF/'tuples.json')['cases'];assign={};stores={};loads={}
    special=set(s.values())|helperpcs|set(spec['capacity_pcs'])|set(spec['csr_prelude'])|{spec['exit_store'],spec['park'],spec['bss_store']}
    for pc,ins in code.items():
        if pc not in special and ins&3==3 and ins&127 in (0x13,0x1b,0x17,0x37,0x33,0x3b,0x6f):
            assign.setdefault((ins>>7)&31,pc)
    for pc,ins in code.items():
        d=c.memory_op(ins)
        if pc not in special and d and d['base'] and d['register'] and d['base']!=d['register'] and d['base'] in assign and d['register'] in assign:
            (stores if d['kind']=='write' else loads).setdefault(d['size'],(pc,d))
    regs={i:0 for i in range(32)};order=0
    def row(pc,rd=0,value=0,addr=0,rm=0,wm=0,data=0,required=False):
        nonlocal order
        result=dict(cycle=str(order+1),event='retire',order=str(order),port='0',trans_id='-1',pc=f'{pc:016x}',
            insn=f'{code[pc]:08x}',rd=str(rd),rd_wdata=f'{value&c.MASK64:016x}',mem_addr=f'{addr:016x}',
            mem_rmask=f'{rm:02x}',mem_wmask=f'{wm:02x}',mem_wdata=f'{data&c.MASK64:016x}',trap='0',_required=required)
        order+=1
        if rd:regs[rd]=value&c.MASK64
        return result
    def setreg(reg,value):return row(assign[reg],reg,value)
    def write(addr,value,size,pc=None):
        pc,d=(pc,c.memory_op(code[pc])) if pc is not None else stores[size]
        yield setreg(d['base'],addr-d['offset'])
        if d['register']:yield setreg(d['register'],value)
        yield row(pc,addr=addr,wm=((1<<size)-1)<<(addr%8),data=value)
    # Actual four reset ABI instructions and values, no observed-wdata defaults.
    yield row(s['_start'],3,s['_start']+0x2000)
    yield row(s['_start']+4,3,s['__global_pointer$'])
    yield row(s['_start']+8,2,s['_start']+8+0x100000)
    yield row(s['_start']+12,2,s['__stack_top'])
    for pc in spec['csr_prelude']:yield row(pc)
    yield setreg(6,s['__bss_end'])
    for addr in range(s['__bss_start'],s['__bss_end'],8):
        yield setreg(5,addr);yield row(spec['bss_store'],addr=addr,wm=255)
    yield row(s['main'])
    # Wrapper capacity first, then actual original-main entry/capacity.
    for pc in sorted(spec['capacity_pcs'],reverse=True)[:1]:yield row(pc,(code[pc]>>7)&31,128)
    yield row(s['whole_original_main'])
    pc=min(spec['capacity_pcs']);yield row(pc,(code[pc]>>7)&31,128)
    for ordinal,g in enumerate(gold[:limit]):
        if not (mutation=='fresh_interval' and ordinal==1):
            for offset in range(0,1024,8):
                value=sum(((offset+j)*37+g['seed']*71+3&255)<<(8*j) for j in range(8))
                if mutation=='input' and ordinal==0 and offset==0:value^=1
                yield from write(s['input']+offset,value,8)
            for offset in range(0,1088,8):yield from write(s['output']+offset,0x5b5b5b5b5b5b5b5b,8)
        for reg,value in enumerate([s['input'],s['output']+32,g['start'],g['mode']],10):yield setreg(reg,value)
        yield setreg(1,assign[10]);pc=s['op_'+str(g['op'])]
        while True:
            ins=code[pc];nextpc=c.reference.next_helper_pc(pc,ins,regs);rd=value=0
            if ins&3!=3:
                if ins&3==1 and ins>>13==2:
                    rd=(ins>>7)&31;value=((ins>>2)&31)|((ins>>12)&1)<<5
                    if value&32:value-=64
                elif ins&3==2 and ins>>13==0:
                    rd=(ins>>7)&31;value=regs[rd]<<(((ins>>2)&31)|((ins>>12)&1)<<5)
            elif ins==0x00802e73:rd,value=28,g['start']
            elif ins==0x00802573:rd,value=10,1 if mutation=='vstart' and ordinal==0 else 0
            elif ins==0x01c56533:rd,value=10,regs[10]|regs[28]
            if mutation=='status' and ordinal==0 and ins==0x01c56533:value^=1
            required=ins&127 in (7,39) or pc==spec['targets'][g['op']]
            if pc==spec['targets'][g['op']]:required=g['start']<g['evl']
            yield row(pc,rd,value,required=required)
            if ins==0x8082:break
            pc=nextpc
        pc,d=loads[8]
        for offset in range(0,1088,8):
            if mutation=='missing_word' and ordinal==0 and offset==1080:continue
            value=0
            for j in range(8):
                i=offset+j;byte=(((i-32)*37+g['seed']*71+3)&255 if 32+g['start']*g['bytes']<=i<32+g['registers']*128 else 91)
                value|=byte<<(8*j)
            if mutation=='guard' and ordinal==0 and offset==1080:value^=1
            if mutation=='result' and ordinal==0 and offset==32:value^=1
            addr=s['output']+offset;yield setreg(d['base'],addr-d['offset'])
            yield row(pc,d['register'],value,addr=addr,rm=255)
    if limit is not None:return
    for value in (1134,366,0):
        yield setreg(10,value);yield row(s['num'])
    for byte in c.EXPECTED_TEXT.encode():yield from write(spec['uart'],byte,1)
    yield setreg(10,0);yield row(s['replay_exit'],5,13)
    yield from write(spec['ctrl'],1 if mutation=='exit' else 0,8,spec['exit_store'])
    yield row(spec['park'])

def protocol(rows,mutation=None):
    arch=cycle=0;mutated=False
    for raw in rows:
        row=dict(raw);required=row.pop('_required');ins=int(row['insn'],16)
        offload=c.is_vector(ins) or c.is_csr(ins) and ins>>20 in (8,9,10,15,0xc20,0xc21,0xc22)
        if offload:
            base=dict(row,rd='0',rd_wdata='0',mem_addr='0',mem_rmask='0',mem_wmask='0',mem_wdata='0',trans_id='0')
            events=['cvx_req','arch_start']
            omit=mutation=='owner_pair' and required and not mutated
            if omit:mutated=True
            if required and not omit:events+=['uop_alloc','uop_done']
            events+=['cvx_resp']
            for event in events:
                cycle+=1;x=dict(base,event=event,order=str(arch),cycle=str(cycle))
                if mutation=='wrong_id' and required and event=='uop_done' and not mutated:
                    x['trans_id']='1';mutated=True
                yield x
            arch+=1
        cycle+=1;row['cycle']=str(cycle);yield row
