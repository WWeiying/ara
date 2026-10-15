"""Linked scalar positive-path cost only; not firmware/reference/Host execution."""
from collections import Counter
import hashlib,importlib.util,json,re,struct,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;A=HERE.parent;OLD=A/'full_e16_m8_block_unrolled01'
MASK=(1<<64)-1
def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def sign(v,n):return v-(1<<n) if v&(1<<(n-1)) else v
def parse(path):
    funcs={};name=None
    for line in path.read_text().splitlines():
        m=re.match(r'^([0-9a-f]+) <([^>]+)>:',line)
        if m:name=m[2];funcs[name]=[];continue
        m=re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([^\s]+)\s*(.*)',line)
        if m and name:funcs[name].append(dict(pc=int(m[1],16),insn=int(m[2],16),op=m[3],args=m[4].split('#')[0].strip()))
    return funcs
class Machine:
    def __init__(self,root):
        self.root=root;self.functions=parse(root/'program.dis');self.s=read(root/'symbols.json')
        self.raw=(root/'program.elf').read_bytes();h=struct.unpack_from('<16sHHIQQQIHHHHHH',self.raw)
        self.segments=[]
        for n in range(h[10]):
            kind,flags,off,va,pa,fs,ms,align=struct.unpack_from('<IIQQQQQQ',self.raw,h[5]+n*h[9])
            if kind==1:self.segments.append((va,self.raw[off:off+fs],ms,flags))
        for fn,rows in self.functions.items():
            for x in rows:
                n=4 if x['insn']&3==3 else 2
                require(self.initial(x['pc'],n)==x['insn'],'Actual linked instruction bytes '+hex(x['pc']))
        self.gp=self.s['__global_pointer$']
    def initial(self,address,size):
        for va,data,length,flags in self.segments:
            if va<=address and address+size<=va+length:return int.from_bytes(data[address-va:address-va+size].ljust(size,b'\0'),'little')
        raise ValueError('Unknown mapped ELF address '+hex(address))
def walk(machine,name,arguments,callback=None,output=None,maxsteps=1500000):
    code={x['pc']:x for x in machine.functions[name]};pc=min(code)
    regs={'zero':0,'sp':machine.s['__stack_top'],'gp':machine.gp,'ra':'caller:ra'}
    regs.update(arguments);writes={};opaque={};visits=Counter();events=[];branches=[];count=0
    def value(r):
        require(r in regs and type(regs[r]) is int,'Known CFG register '+r+' at '+hex(pc))
        return regs[r]
    def put(r,v):
        if r!='zero':regs[r]=v&MASK
    def address(expr):
        m=re.fullmatch(r'(-?\d+)\((\w+)\)',expr);require(m is not None,'Address operand '+expr)
        return (value(m[2])+int(m[1]))&MASK
    def load(a,n):
        if (a,n) in opaque:return opaque[(a,n)]
        if output is not None and machine.s['out']<=a and a+n<=machine.s['out']+1028:
            return int.from_bytes(output[a-machine.s['out']:a-machine.s['out']+n],'little')
        return sum((writes[a+i] if a+i in writes else machine.initial(a+i,1))<<(8*i) for i in range(n))
    def store(a,n,v):
        if type(v) is not int:
            require(machine.s['__stack_top']-4096<=a< machine.s['__stack_top'] and n==8,'Opaque only ABI save')
            opaque[(a,n)]=v;return
        opaque.pop((a,n),None)
        for i in range(n):writes[a+i]=(v>>(8*i))&255
    while True:
        require(pc in code and count<maxsteps,'Finite actual CFG '+name+' '+hex(pc))
        x=code[pc];op=x['op'];args=[v.strip() for v in x['args'].split(',')] if x['args'] else []
        count+=1;visits[pc]+=1;nextpc=pc+(4 if x['insn']&3==3 else 2)
        if op=='ret':break
        if op in ('ld','lw','lwu','lh','lhu','lbu','lb'):
            n={'ld':8,'lw':4,'lwu':4,'lh':2,'lhu':2,'lbu':1,'lb':1}[op]
            a=address(args[1]);v=load(a,n)
            if type(v)is int and op in ('lw','lh','lb'):v=sign(v,n*8)&MASK
            regs[args[0]]=v
            if output is not None:events.append(dict(pc=pc,op=op,address=a,size=n,value=v))
        elif op in ('sd','sw','sh','sb'):
            if args[0] not in regs:
                require(re.fullmatch(r's\d+|ra',args[0]) is not None,'Only unknown ABI entry saves')
                regs[args[0]]='caller:'+args[0]
            a=address(args[1]);n={'sd':8,'sw':4,'sh':2,'sb':1}[op];v=regs[args[0]]
            store(a,n,v)
            if callback is not None:callback('store',dict(pc=pc,address=a,size=n,value=v),regs,load)
        elif op in ('jal','jalr'):
            require(callback is not None,'Leaf cannot call')
            dest=int(args[-1].split()[0],16) if op=='jal' else value(args[-1])
            answer=callback('call',dict(pc=pc,dest=dest),regs,load)
            for r in ['ra']+['a'+str(i) for i in range(8)]+['t'+str(i) for i in range(7)]:regs.pop(r,None)
            if answer is not None:regs['a0']=answer
        elif op=='j':nextpc=int(args[0].split()[0],16)
        elif op in ('beq','bne','beqz','bnez','bltu','bgeu','blt','bge'):
            a=value(args[0]);b=0 if op in ('beqz','bnez') else value(args[1])
            taken=a==b if op in ('beq','beqz') else a!=b if op in ('bne','bnez') else a<b if op=='bltu' else a>=b if op=='bgeu' else sign(a,64)<sign(b,64) if op=='blt' else sign(a,64)>=sign(b,64)
            if taken:nextpc=int(args[-1].split()[0],16)
            if output is not None:branches.append(dict(pc=pc,op=op,taken=taken))
        elif op=='li':put(args[0],int(args[1],0))
        elif op in ('lui','auipc'):
            v=sign((int(args[1],0)<<12)&0xffffffff,32);put(args[0],v+(pc if op=='auipc' else 0))
        elif op=='mv':regs[args[0]]=regs[args[1]]
        elif op in ('sext.w','snez','seqz','zext.h','zext.b'):
            v=value(args[1]);put(args[0],sign(v&0xffffffff,32) if op=='sext.w' else int(v!=0) if op=='snez' else int(v==0) if op=='seqz' else v&65535 if op=='zext.h' else v&255)
        elif op in ('addi','addiw','slli','srli','srliw','andi','ori'):
            v=value(args[1]);i=int(args[2],0)
            z=v+i if op in ('addi','addiw') else v<<i if op=='slli' else v>>i if op=='srli' else (v&0xffffffff)>>i if op=='srliw' else v&i if op=='andi' else v|i
            put(args[0],sign(z&0xffffffff,32) if op in ('addiw','srliw') else z)
        elif op in ('add','addw','sub','subw','xor','or','and','mul','mulw'):
            a=value(args[1]);b=value(args[2])
            z=a+b if op in ('add','addw') else a-b if op in ('sub','subw') else a^b if op=='xor' else a|b if op=='or' else a&b if op=='and' else a*b
            put(args[0],sign(z&0xffffffff,32) if op in ('addw','subw','mulw') else z)
        else:raise ValueError('Unsupported actual positive CFG opcode '+op+' '+hex(pc))
        pc=nextpc
    return dict(instructions=count,visits=visits,events=events,branches=branches,return_value=regs.get('a0'))
def inspect(root,rows):
    m=Machine(root);oldm=Machine(OLD/root.name)
    for symbol,size in [('expected_dictionary',3598*64),('expected_indices',4095*17*2),('physical_masks',384)]:
        require(all(m.initial(m.s[symbol]+i,1)==oldm.initial(oldm.s[symbol]+i,1) for i in range(size)),'Immutable linked table '+symbol)
    helpernames=['capacity']+['op_'+str(i) for i in range(25)]
    helpers={}
    for name in helpernames:
        now=[x['insn'] for x in m.functions[name]];before=[x['insn'] for x in oldm.functions[name]]
        require(now==before and len(now)==(3 if name=='capacity' else 13),'Original complete helper '+name)
        helpers[name]=now
    helperpcs={x['pc'] for name in helpernames for x in m.functions[name]}
    extra=[x['pc'] for fn in m.functions.values() for x in fn if x['insn']&3==3 and (x['insn']&127==87 or x['insn']&127 in (7,39) and x['insn']>>12&7 in (0,5,6,7)) and x['pc'] not in helperpcs]
    require(not extra,'No extra RVV')
    for opcodes in ({0x73},{0x0f},{0x53,0x43,0x47,0x4b,0x4f}):
        require(Counter(x['insn'] for fn in m.functions.values() for x in fn if x['insn']&127 in opcodes)==Counter(x['insn'] for fn in oldm.functions.values() for x in fn if x['insn']&127 in opcodes),'No changed CSR/fence/scalarFP code')
    cmpname=next(n for n in m.functions if n.startswith('packed_mismatch'))
    costs=[];metrics=Counter();by_pc=Counter();samples=[]
    for row in rows:
        ordinal=row['ordinal']-1
        require([m.initial(m.s['expected_indices']+ordinal*34+2*i,2) for i in range(17)]==row['indices'],'Exact linked ID row')
        output=b''.join(m.initial(m.s['expected_dictionary']+64*bid,64).to_bytes(64,'little') for bid in row['indices'][:16])
        output+=m.initial(m.s['expected_dictionary']+64*row['indices'][16],4).to_bytes(4,'little')
        result=walk(m,cmpname,{'a0':ordinal},output=output,maxsteps=1500)
        require(result['return_value']==0,'Equal comparator return0')
        actual=[e for e in result['events'] if m.s['out']<=e['address']<m.s['out']+1028]
        require(sorted((e['address']-m.s['out'],e['size']) for e in actual)==[(i,8) for i in range(0,1024,8)]+[(1024,4)],'Every actual128LD/LW exactly once')
        gold=[e for e in result['events'] if m.s['expected_dictionary']<=e['address']<m.s['expected_dictionary']+3598*64]
        expected_gold=sum(8 for bid in row['indices'][:16] if bid!=0)+1
        require(len(gold)==expected_gold,'ID0 no goldLD; nonzero8 loads and tail separate')
        metrics['actual_reads']+=len(actual);metrics['gold_reads']+=len(gold);metrics['comparator_instructions']+=result['instructions'];by_pc.update(result['visits']);costs.append(result['instructions'])
        if ordinal in (0,9,45,1365,2730,4094):
            samples.append(dict(ordinal=ordinal+1,IDs=row['indices'],instructions=result['instructions'],gold_reads=len(gold),path=list(map(hex,result['visits']))))
    names={m.s[n]:n for n in m.functions};terms=Counter();calls=Counter();index=0;completed=0;fresh=[];mask=[];maskgroups=0;argument_log=[]
    def cb(kind,event,regs,load):
        nonlocal index,completed,maskgroups,fresh,mask
        if kind=='store':
            a=event['address']
            if m.s['out']<=a<m.s['out']+2052:fresh.append(event)
            if m.s['mask']<=a<m.s['mask']+128:mask.append(event)
            return
        name=names[event['dest']];calls[name]+=1
        if name=='capacity':terms['capacity']+=3;return 512
        if name.startswith('op_'):
            row=rows[index];want=[m.s['a'],m.s['b'],m.s['out']+2,row['vl'],512,m.s['mask'],row['start']]
            require(name=='op_'+str(row['op']) and [regs['a'+str(i)] for i in range(7)]==want,'Exact original source/helper history')
            require(sorted((e['address']-m.s['out'],e['size']) for e in fresh)==[(i,8) for i in range(0,1024,8)]+[(1024,4)],'All fresh SD/SW, actual order allowed')
            require(all(e['value']==(0x005b005b005b005b if e['size']==8 else 0x005b005b) for e in fresh),'Typed initializer values')
            if row['si']==0:
                require(sorted((e['address']-m.s['mask'],e['size']) for e in mask)==[(i,8) for i in range(0,128,8)],'Full same-phase16 mask SD, no overlap/duplicate/OOB')
                require(all(type(e['value']) is int and e['value']==m.initial(m.s['physical_masks']+128*row['mode']+e['address']-m.s['mask'],8) for e in mask),'Each actual store GPR value matches source table at exact offset')
                require(all(load(m.s['mask']+i,1)==m.initial(m.s['physical_masks']+128*row['mode']+i,1) for i in range(128)),'Mask table state at helper')
                maskgroups+=1;mask=[]
            else:require(not mask,'No repeated mode setup')
            argument_log.append(dict(ordinal=index+1,arguments=want,setup_pc=hex(event['pc'])))
            fresh=[];terms['original_helper']+=13;index+=1;return 0
        if name.startswith('packed_mismatch'):
            require(index==completed+1 and regs['a0']==completed,'Per-call comparator ordinal')
            terms['comparator']+=costs[completed];completed+=1;return 0
        if name=='number':
            digits=len(str(regs['a0']));terms['number_and_nested_write_upper']+=len(m.functions[name])*(2*digits+1)+len(m.functions['replay_write'])*(digits+1);return None
        if name=='replay_write':
            n=regs['a3'];require(n<=256,'Finite runtime write')
            terms['direct_write_upper']+=len(m.functions[name])*(n+1);return n
        raise ValueError('Unexpected positive-path call '+name)
    main=walk(m,'arithmetic_main',{},callback=cb)
    require(index==completed==4095 and maskgroups==1575 and not fresh and not mask and main['return_value']==0,'All4095 main history/fresh/mask/return')
    terms['main_all_setup_branch_join_spill']=main['instructions']
    bss=4*((m.s['__bss_end']-m.s['__bss_start']+7)//8)+1
    terms['startup_BSS_loop']=bss;terms['startup_return_success_allowance']=20000
    upper=sum(terms.values())
    frame=-int(m.functions['arithmetic_main'][0]['args'].split(',')[-1])
    constants=[hex(pc) for pc in by_pc if m.functions[cmpname] and next(x for x in m.functions[cmpname] if x['pc']==pc)['op']=='lui']
    constant_visits=sum(by_pc[int(p,16)] for p in constants)
    return dict(elf_sha256=sha(root/'program.elf'),terms=dict(terms),whole_positive_CFG_upper=upper,
        comparator_cost_min=min(costs),comparator_cost_max=max(costs),comparator_metrics=dict(metrics),comparator_PC_visits={hex(k):v for k,v in sorted(by_pc.items())},
        sentinel_constant_LUI_sites=constants,sentinel_constant_materializations=constant_visits,
        comparator_samples=samples,all_target_arguments=argument_log,calls=dict(calls),mask_groups=maskgroups,
        main_frame_bytes=frame,stack_gap=m.s['__stack_top']-m.s['__bss_end'],original_helper_static_instructions=328,
        extra_RVV=extra,main_PC_visits={hex(k):v for k,v in sorted(main['visits'].items())},
        positive_hypotheses=['original helper returns vstart0','actual outputs equal original immutable gold'],
        not_architectural_reference=True,failure_cost_bound_claimed=False)
def main():
    started=time.monotonic();pins=read(HERE/'INPUT_PINS.json')
    for p,h in pins.items():require(sha(p)==h,'Input drift')
    rows=read(OLD/'sequence.json');result={}
    try:
        for backend in ('soc','spike'):
            print('PHASE STATIC_CFG '+backend+' START',flush=True)
            result[backend]=inspect(HERE/backend,rows)
            print('PHASE STATIC_CFG '+backend+' UPPER '+str(result[backend]['whole_positive_CFG_upper']),flush=True)
        for p,h in pins.items():require(sha(p)==h,'Post input drift')
        save(HERE/'LINKED_COST02.json',dict(status='ACTUAL_LINKED_FULL_POSITIVE_CFG_COMPLETE_NO_REFERENCE_NO_DUT',
            compiled=result,source_pins_unchanged=True,reference_runs=0,DUT_runs=0,Host_fullstream_runs=0,
            static_only=True,elapsed_s=time.monotonic()-started,independent_review_pending=True))
    except BaseException as error:
        save(HERE/'CFG_STOPPED02.json',dict(status='STATIC_COST_OBSERVER_STOP_NOT_DUT',firstcause=type(error).__name__+': '+str(error),compiled=result))
        raise
if __name__=='__main__':main()
