"""Positive scalar main CFG; vector/leaf calls use separately proved summaries.

No vector instructions are executed or validated by this cost analysis. Capacity
128 and successful helper/oracle returns are explicit positive-path hypotheses.
"""
import collections
import re
from leaf_cfg import require,sign,MASK

def main_bound(machine,functions,symbols,rows,cache_cost,leaf_cost,seeds):
    code={x['pc']:x for x in functions['arithmetic_main']};pc=min(code)
    regs={'zero':0,'sp':symbols['__stack_top'],'gp':machine.gp,'ra':'caller:ra'}
    writes={};opaque={};visits=collections.Counter();calls=collections.Counter();terms=collections.Counter()
    index=0;cache_index=0;init_index=0;mask_index=0;fp_index=0
    groups=[r for r in rows if r['trial']==0];fp_rows=[r for r in rows if r['op']>=25]
    names={symbols[n]:n for n in functions};argument_log=[];strings=[];step=0
    def value(r):
        require(r in regs and type(regs[r]) is int,'Known scalar CFG register '+r+' at '+hex(pc))
        return regs[r]
    def setreg(r,v):
        if r!='zero':regs[r]=v&MASK
    def addr(expr):
        m=re.fullmatch(r'(-?\d+)\((\w+)\)',expr);require(m is not None,'Known address expression')
        return (value(m[2])+int(m[1]))&MASK
    def load(a,n):
        if (a,n) in opaque:return opaque[(a,n)]
        return sum((writes[a+i] if a+i in writes else machine.initial(a+i,1))<<(8*i) for i in range(n))
    def store(a,n,v):
        if type(v) is not int:
            require(symbols['__stack_top']-4096<=a<symbols['__stack_top'] and n==8,'Opaque only saved caller stack')
            opaque[(a,n)]=v;return
        opaque.pop((a,n),None)
        for i in range(n):writes[a+i]=(v>>(8*i))&255
    def callback(dest):
        nonlocal index,cache_index,init_index,mask_index,fp_index
        require(dest in names,'Resolved actual call target');name=names[dest];calls[name]+=1;answer=None
        if name=='capacity':terms['capacity']+=3;answer=128
        elif name.startswith('op_'):
            require(index<len(rows),'No extra target call');r=rows[index]
            expected=[symbols['a'],symbols['b'],symbols['out']+4,r['vl'],128,symbols['mask'],r['start']]
            require(name=='op_'+str(r['op']) and [value('a'+str(i)) for i in range(7)]==expected,'Exact original target/setup/history')
            require(init_index==index+1 and cache_index==index,'Exactly one initializer and prior completed comparator')
            if r['op']>=25:require(fp_index==sum(x['op']>=25 for x in rows[:index+1]),'Per-call FP freshness control')
            argument_log.append(dict(ordinal=index+1,pc=hex(pc),helper=name,arguments=expected))
            index+=1;terms['original_helper_bodies']+=13;answer=0
        elif name.startswith('e32m4_packed'):
            require(cache_index+1==index and value('a0')==symbols['e32m4_expected_ids']+18*cache_index,'Exact per-call cache IDs pointer/order')
            terms['cache']+=cache_cost[cache_index];cache_index+=1;answer=0
        elif name.startswith('e32m4_initialize_output'):
            require(init_index==index,'No skipped or duplicate output initialization')
            init_index+=1;terms['output_init']+=leaf_cost['output']
        elif name.startswith('e32m4_refresh_fp'):
            require(fp_index<len(fp_rows) and value('a0')==fp_rows[fp_index]['seed'] and rows[index]==fp_rows[fp_index],'Actual FP call order/seed')
            terms['FP']+=leaf_cost['FP'][value('a0')];fp_index+=1
        elif name.startswith('e32m4_initialize_mask'):
            require(mask_index<len(groups) and groups[mask_index]==rows[index] and value('a0')==groups[mask_index]['mode'],'Exact group mask call order')
            r=rows[index]
            if r['op']==0 and r['li']==0 and r['mode']==0:
                for bank in ('a','b'):
                    require([load(symbols[bank]+4*i,4) for i in range(128)]==seeds[r['seed']][bank],'Actual full seed RNG assignments '+bank)
            terms['mask']+=leaf_cost['mask'][value('a0')];mask_index+=1
        elif name=='number':
            v=value('a0');digits=len(str(v));require(digits<=20,'uint64 decimal bound')
            # Count every static number instruction once for each iteration of
            # both bounded loops plus pro/epilogue, and every replay_write PC
            # once per printed digit plus its entry/exit. Deliberate overcount.
            terms['number_and_nested_write_upper']+=len(functions['number'])*(2*digits+1)+len(functions['replay_write'])*(digits+1)
        elif name=='replay_write':
            require(value('a0')==64 and value('a1')==1 and value('a3')<=256,'Successful fixed runtime write contract')
            n=value('a3');text=bytes(load(value('a2')+i,1) for i in range(n));strings.append(text.decode('ascii'))
            terms['direct_replay_write_upper']+=len(functions[name])*(n+1);answer=n
        else:raise ValueError('Unexpected positive-path call '+name)
        # The linked helpers have no undocumented callee-saved modifications.
        # Caller-saved values become unknown, not zero, at the summary boundary.
        for r in ['ra']+['a'+str(i) for i in range(8)]+['t'+str(i) for i in range(7)]:regs.pop(r,None)
        if answer is not None:regs['a0']=answer
    while True:
        require(pc in code and step<1000000,'Bounded actual main CFG');step+=1;visits[pc]+=1
        x=code[pc];op=x['op'];args=x['args'].split('#')[0].strip();p=[v.strip() for v in args.split(',')] if args else []
        nxt=pc+(4 if x['insn']&3==3 else 2)
        if op=='ret':require(value('a0')==0,'Positive main return0');break
        if op in ('ld','lw','lwu','lbu'):
            n={'ld':8,'lw':4,'lwu':4,'lbu':1}[op];v=load(addr(p[1]),n)
            regs[p[0]]=sign(v,32)&MASK if op=='lw' else v
        elif op in ('sd','sw','sb'):
            if p[0] not in regs:
                require(re.fullmatch(r's\d+|ra',p[0]),'Only unknown caller saves');regs[p[0]]='caller:'+p[0]
            store(addr(p[1]),{'sd':8,'sw':4,'sb':1}[op],regs[p[0]])
        elif op in ('jal','jalr'):
            callback(int(p[-1].split()[0],16) if op=='jal' else value(p[-1]))
        elif op=='j':nxt=int(p[0].split()[0],16)
        elif op in ('beq','bne','bltu','bgeu','beqz','bnez'):
            a=value(p[0]);b=0 if op in ('beqz','bnez') else value(p[1]);target=int(p[-1].split()[0],16)
            taken=(a==b) if op in ('beq','beqz') else (a!=b) if op in ('bne','bnez') else (a<b) if op=='bltu' else (a>=b)
            if taken:nxt=target
        elif op=='li':setreg(p[0],int(p[1],0))
        elif op in ('lui','auipc'):
            imm=sign((int(p[1],0)<<12)&0xffffffff,32);setreg(p[0],imm+(pc if op=='auipc' else 0))
        elif op=='mv':regs[p[0]]=regs[p[1]]
        elif op in ('sext.w','snez'):
            v=value(p[1]);setreg(p[0],sign(v&0xffffffff,32) if op=='sext.w' else int(v!=0))
        elif op in ('addi','addiw','slli','srli','srliw','andi'):
            v=value(p[1]);i=int(p[2],0)
            z=v+i if op in ('addi','addiw') else v<<i if op=='slli' else v>>i if op=='srli' else (v&0xffffffff)>>i if op=='srliw' else v&i
            if op in ('addiw','srliw'):z=sign(z&0xffffffff,32)
            setreg(p[0],z)
        elif op in ('add','addw','sub','xor'):
            a=value(p[1]);b=value(p[2]);z=a+b if op in ('add','addw') else a-b if op=='sub' else a^b
            setreg(p[0],sign(z&0xffffffff,32) if op=='addw' else z)
        else:raise ValueError('Unexpected main opcode '+op+' '+hex(pc))
        pc=nxt
    require((index,cache_index,init_index,mask_index,fp_index)==(5985,5985,5985,2205,1890),'Whole actual source call counts')
    require([load(symbols[n],8) for n in ('checks','elements','errors')]==[5985,766080,0],'Actual positive scalar counter endpoints')
    terms['main_including_all_caller_code']=step
    return dict(terms=dict(terms),calls=dict(calls),main_PC_visits={hex(k):v for k,v in sorted(visits.items())},
        target_arguments=argument_log,strings=strings,positive_success_assumptions=['capacity=128','helper vstart=0','all actual outputs equal pinned oracle'],
        cost_not_architectural_reference=True)
