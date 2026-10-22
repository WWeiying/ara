"""Static actual-ELF path proof/cost only; no firmware/reference execution."""
from collections import Counter
import copy
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;S=H.parent/'software02';OLD=H.parent/'software01';A=H.parents[1]
M=A/'full_e64_m4_source_model01/generated01'
spec=importlib.util.spec_from_file_location('frozen_inspection_utilities',H.parent/'compiled_audit01/inspect.py')
u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)
need,sha,read,save=u.need,u.sha,u.read,u.save
assembly,args,nxt,region,mem,target=u.assembly,u.args,u.nxt,u.region,u.mem,u.target


def finite(c,start,end,kind,index,sym):
    # Register bindings below are independently checked against linked symbol setup.
    regs={'zero':0,'gp':sym['__global_pointer$'],'s4':sym['mask'],'s11':index,
          's5':sym['a'],'s6':sym['b'],'s7':2}
    pc=start;pcs=[];clears=[];bits=[];fp=[];loads=[]
    while pc!=end:
        need(pc not in pcs and len(pcs)<600,'Acyclic finite path')
        pcs.append(pc);x=c[pc];op=x['op'];a=args(x);np=nxt(c,pc)
        if op=='auipc':regs[a[0]]=pc+u.signed(x['insn']&0xfffff000,32)
        elif op=='addi':regs[a[0]]=regs[a[1]]+int(a[2])
        elif op=='li':regs[a[0]]=int(a[1])
        elif op in ('ld','lbu'):
            off,base=mem(a[1])
            if kind=='fp' and base=='sp':
                need(op=='ld' and off==144 and a[0]=='t3','Seed stack binding');regs[a[0]]=index
            else:
                address=regs[base]+off
                if kind=='fp':
                    need(op=='ld' and sym['fp_inputs']<=address<sym['fp_inputs']+64 and address%8==0,'Eight actual FP LD')
                    slot=(address-sym['fp_inputs'])//8;regs[a[0]]=('fp',slot);loads.append(dict(pc=hex(pc),slot=slot))
                else:
                    need(op=='lbu' and sym['mask']<=address<sym['mask']+8,'Actual mask LBU');regs[a[0]]=('mask',address)
        elif op=='ori':
            previous=regs[a[1]];need(kind=='mask' and previous[0]=='mask','Mask load/OR')
            regs[a[0]]=('bit',previous[1],int(a[2])&255)
        elif op in ('sd','sb'):
            off,base=mem(a[1]);address=regs[base]+off;value=regs[a[0]]
            if kind=='mask' and op=='sd':
                need(value==0 and not bits,'All mask clear before bits');clears.append(address)
            elif kind=='mask':
                need(op=='sb' and len(clears)==16 and value[0]=='bit' and value[1]==address,'Actual same-byte RMW')
                bit=value[2];need(bit in [1<<n for n in range(8)],'One selected bit')
                bits.append((address-sym['mask'])*8+bit.bit_length()-1)
            else:
                need(op=='sd' and value[0]=='fp','FP SD')
                i,bank=divmod(len(fp),2);name='b' if bank else 'a'
                need(address==sym[name]+8*i and value[1]==((3*i if bank else i)+index)%8,'Full FP order/content')
                fp.append(dict(pc=hex(pc),bank=name,index=i,input_slot=value[1]))
        elif op=='j':np=target(x)
        elif op=='bnez':np=target(x) if regs[a[0]] else np
        elif op=='beq':np=target(x) if regs[a[0]]==regs[a[1]] else np
        else:raise ValueError('Unexpected finite path '+hex(pc)+' '+op)
        pc=np
    if kind=='mask':
        wanted=list(range(64)) if index==0 else list(range(1,64,2)) if index==1 else list(range(2,64,7))
        need(clears==list(range(sym['mask'],sym['mask']+128,8)) and bits==wanted,'Full original mask event order')
    else:need(len(fp)==128 and [x['slot'] for x in loads]==list(range(8)),'128 FP SD and8 LD')
    return dict(pcs=list(map(hex,pcs)),instructions=len(pcs),clears=clears,bits=bits,FP_writes=fp,FP_inputs=loads)


def linear(constant,coefficient=0):return ('linear',constant,coefficient)
def plus(x,y):
    if x[0]==y[0]=='linear':return linear(x[1]+y[1],x[2]+y[2])
    if x[0]=='id_offset' and y[0]=='linear' and not y[2]:return ('gold_pointer',x[1],y[1])
    if y[0]=='id_offset' and x[0]=='linear' and not x[2]:return ('gold_pointer',y[1],x[1])
    raise ValueError('Unexpected symbolic add '+repr((x,y)))


def sticky(c,start,end,sym):
    """One generic ordinal, arbitrary word values, all equal/unequal flag states."""
    regs={'zero':linear(0),'gp':linear(sym['__global_pointer$']),'s0':linear(sym['out'])}
    pc=start;pcs=[];loads=[];ids=[];sites=[];initial=[];word=0
    while pc!=end:
        need(pc not in pcs and len(pcs)<500,'Acyclic full comparator')
        pcs.append(pc);x=c[pc];op=x['op'];a=args(x);np=nxt(c,pc)
        if op=='auipc':regs[a[0]]=linear(pc+u.signed(x['insn']&0xfffff000,32))
        elif op=='addi':regs[a[0]]=plus(regs[a[1]],linear(int(a[2])))
        elif op=='add':regs[a[0]]=plus(regs[a[1]],regs[a[2]])
        elif op=='slli':
            v=regs[a[1]];n=int(a[2],0)
            if v[0]=='linear':regs[a[0]]=linear(v[1]<<n,v[2]<<n)
            else:
                need(v[0]=='id' and n==6,'64-byte dictionary block');regs[a[0]]=('id_offset',v[1])
        elif op=='li':
            need(a==['a5','0'] and word==0,'Only one initial flag zero')
            initial.append(pc);regs[a[0]]=('sticky',frozenset())
        elif op=='lhu':
            off,base=mem(a[1]);v=plus(regs[base],linear(off))
            need(v[0]=='linear' and v[2]==18,'Actual row stride9 uint16')
            offset=v[1]-sym['e64m4_block_ids'];need(offset==2*len(ids) and offset<=16,'Exact nine ID addresses')
            block=offset//2;ids.append(dict(pc=hex(pc),block=block));regs[a[0]]=('id',block)
        elif op=='ld':
            off,base=mem(a[1]);v=regs[base]
            if v==linear(sym['checks']) and off==0:regs[a[0]]=linear(0,1);continue_pc=False
            elif v[0]=='linear':
                need(v[2]==0 and v[1]+off-sym['out']==8*word,'Exact next actual word')
                need(len(loads)==2*word,'Actual before expected');regs[a[0]]=('actual',word);loads.append(dict(pc=hex(pc),kind='actual',word=word))
            else:
                need(v[0]=='gold_pointer' and v[2]==sym['e64m4_dictionary'],'Dictionary base retained')
                need(v[1]*8+off//8==word and off%8==0 and 0<=off<=56,'Exact expected word including two-word tail')
                need(len(loads)==2*word+1,'Expected after actual');regs[a[0]]=('expected',word);loads.append(dict(pc=hex(pc),kind='expected',word=word))
        elif op=='beq':
            need({regs[a[0]],regs[a[1]]}=={('actual',word),('expected',word)},'BEQ compares same actual/expected word')
            need(x['insn']&127==0x63 and (x['insn']>>12)&7==0,'Actual BEQ encoding')
            need(len(loads)==2*(word+1),'Both loads completed before branch')
            li=c[np];need(li['op']=='li' and args(li)==['a5','1'],'Unequal sets one, not toggles')
            join=nxt(c,np);need(target(x)==join,'Equal skips only LI; both paths rejoin immediately')
            need(regs['a5']==('sticky',frozenset(range(word))),'No clearing/overwriting accumulated mismatch')
            transitions=[]
            for flag in (0,1):
                for equal in (True,False):
                    after=flag if equal else int(args(li)[1]);need(after==(flag or not equal),'All four local transitions')
                    transitions.append(dict(before=flag,equal=equal,after=after))
            sites.append(dict(word=word,beq=hex(pc),li=hex(np),join=hex(join),transitions=transitions))
            regs['a5']=('sticky',frozenset(range(word+1)));word+=1;np=join
        elif op=='bnez':
            need(np==end and a[0]=='a5' and word==66 and regs['a5']==('sticky',frozenset(range(66))),'Only final decision after full132 loads')
        else:raise ValueError('Unexpected comparator op (including spill/call/CSR) '+hex(pc)+' '+op)
        pc=np
    need(word==66 and len(initial)==1 and len(loads)==132 and len(ids)==9,'Complete generic comparator proof')
    return dict(all_equal_instructions=len(pcs),unequal_extra_per_word=1,all_equal_pcs=list(map(hex,pcs)),
        loads=loads,ids=ids,sites=sites,initial_zero=hex(initial[0]),spill_instructions=0,
        arbitrary_mismatch_patterns_proved_by_induction=True,full_reads_after_error=True)


def main():
    pins=read(S/'pins.json');receipt=read(S/'execution_receipt.json');proof=read(S/'proof.json')
    for p,h in pins.items():need(sha(p)==h,'Preflight drift '+p)
    need(type(receipt['returncode']) is int and receipt['returncode']==0 and not receipt['timed_out'],'Actual bounded Host/GCC wait0')
    need(len(proof['host'])==41,'41 preserved outcomes')
    for row in proof['host']:
        need(type(row['returncode']) is int and row['returncode']==row['expected_returncode'] and not row['timed_out'] and sha(row['log'])==row['sha256'],'Actual Host expected outcome')
    for name in ['case.c','original_case.c','dictionary.h','mask_setup.h','fp_period.h','original/scenario.S','original/operations.h']:
        need(sha(S/name)==sha(OLD/name),'Only comparator changed '+name)
    results={};negative=[]
    for backend in ('soc','spike'):
        root=S/backend;c=assembly(root/'program.dis');sym=read(root/'symbols.json');raw=(root/'program.elf').read_bytes()
        need(sha(root/'program.elf')==proof['backends'][backend]['sha256'],'Actual ELF pin')
        for pc,x in c.items():
            n=nxt(c,pc)-pc;need(u.filebytes(raw,pc,n)==x['insn'].to_bytes(n,'little'),'Disassembly/actual ELF byte '+hex(pc))
        for symbol,file in [('e64m4_dictionary','dictionary64.bin'),('e64m4_block_ids','indices_u16le.bin'),('fp_inputs','fp_inputs8_u64le.bin'),('fp_expected','fp_expected640_u64le.bin')]:
            data=(M/file).read_bytes();need(u.filebytes(raw,sym[symbol],len(data))==data,'Linked table '+symbol)
        body=[p for p in c if sym['arithmetic_main']<=p<sym['capacity']]
        for name,reg in [('out','s0'),('mask','s4'),('a','s5'),('b','s6')]:u.base_binding(c,body,name,reg,sym)
        stores=[p for p in body if c[p]['op']=='sd' and re.fullmatch(r'a5,\d+\(s0\)',c[p]['args'])]
        need([mem(args(c[p])[1])[0] for p in stores]==list(range(0,528,8)),'Actual66 output SD with both guards')
        init=stores[0]-4;need(c[init]['op']=='li' and args(c[init])==['a5','91'],'Typed005b sentinel')
        start=next(p for p in body if p>stores[-1] and '<checks>' in c[p]['args'])
        decision=next(p for p in body if p>start and c[p]['op']=='bnez' and args(c[p])[0]=='a5')
        end=nxt(c,decision);cmp=sticky(c,start,end,sym)
        # Short corruption checks of the actual linked symbolic proof, not another Host/RVV run.
        for name in ('set_zero','delete_tail_load','reset_after_error','wrong_expected','early_exit'):
            bad=copy.deepcopy(c)
            if name=='set_zero':bad[int(cmp['sites'][0]['li'],16)]['args']='a5,0'
            elif name=='delete_tail_load':bad[int(cmp['loads'][-1]['pc'],16)].update(op='li',args='a4,0')
            elif name=='reset_after_error':bad[int(cmp['loads'][4]['pc'],16)].update(op='li',args='a5,0')
            elif name=='wrong_expected':
                pc=int(cmp['loads'][-1]['pc'],16);bad[pc]['args']='a4,0(a4)'
            else:bad[int(cmp['sites'][0]['beq'],16)]['args']='a2,a1,'+format(end,'x')
            try:sticky(bad,start,end,sym)
            except (ValueError,KeyError):negative.append(dict(backend=backend,name=name,rejected=True))
            else:raise ValueError('Symbolic negative accepted '+name)
        zeros=[p for p in body if c[p]['op']=='sd' and c[p]['args'].startswith('zero,') and re.search(r'<mask(?:\+0x[0-9a-f]+)?>',c[p]['args'])]
        need(len(zeros)==16,'16 actual mask clear SD')
        mask_start=zeros[0]-4;mask_end=next(p for p in body if p>zeros[-1] and c[p]['op']=='ld' and args(c[p])==['a5','136(sp)'])
        mask_paths={str(i):finite(c,mask_start,mask_end,'mask',i,sym) for i in range(3)}
        fp_start=next(p for p in body if c[p]['op']=='addi' and '<fp_inputs>' in c[p]['args'])-4
        fp_paths={str(i):finite(c,fp_start,init,'fp',i,sym) for i in range(3)}
        gates=[p for p in body if c[p]['op']=='bltu' and target(c[p])==fp_start]
        need(len(gates)==1 and args(c[gates[0]-2])==['a5','24'] and args(c[gates[0]-4])==['a4','72(sp)'],'Original op>24 FP gate')
        need(sum(c[p]['op']=='j' and target(c[p])==gates[0]-4 for p in body)==2,'Two later-trial paths retain FP gate')
        need(any(c[p]['op']=='bgeu' and target(c[p])==init and nxt(c,p)==fp_start for p in body),'Third-trial FP gate')
        trial=next(p for p in body if p>end and c[p]['op']=='beq' and args(c[p])[:2]==['a5','a4']);core_end=nxt(c,trial)
        core=len(region(c,init,start))+cmp['all_equal_instructions']+len(region(c,end,core_end))+13
        prior=assembly(OLD/backend/'program.dis')
        for opcodes,label in [({0x73},'CSR/system'),({0x0f},'fence'),({0x53,0x43,0x47,0x4b,0x4f},'scalar FP')]:
            now=Counter(x['insn'] for x in c.values() if x['insn']&3==3 and x['insn']&127 in opcodes)
            before=Counter(x['insn'] for x in prior.values() if x['insn']&3==3 and x['insn']&127 in opcodes)
            need(now==before,'No new/changed '+label+' instruction')
        frames=[-int(args(x)[2]) for x in c.values() if x['op']=='addi' and x['args'].startswith('sp,sp,-')]
        need(args(c[sym['arithmetic_main']])==['sp','sp','-320'],'Same main320 frame')
        need(sum(frames)<65536 and sym['__stack_top']-sym['__bss_end']>=65536,'Actual stack bounds')
        results[backend]=dict(elf_sha256=sha(root/'program.elf'),comparator=cmp,comparator_start=hex(start),comparator_end=hex(end),
             core_each=core,core_full=core*5985,core_end=hex(core_end),output66_stores=list(map(hex,stores)),
             FP_paths=fp_paths,mask_paths=mask_paths,main_frame=320,all_static_frame_sum=sum(frames),stack_gap=sym['__stack_top']-sym['__bss_end'],
             mandatory=core*5985+sum(x['instructions']*630 for x in fp_paths.values())+sum(x['instructions']*735 for x in mask_paths.values()))
    c=assembly(S/'spike/program.dis');terms=[]
    def R(a,b):return region(c,int(a,16),int(b,16))
    def add(name,pcs,n):terms.append(dict(name=name,pcs=list(map(hex,pcs)),instructions_each=len(pcs),visits=n,total=len(pcs)*n))
    add('all_trials_op_gate',R('80000940','80000948'),5985)
    add('later_trials_selection_union',R('80000dac','80000dc2')+R('800012d2','800012dc')+R('8000136e','80001378'),3780)
    add('group_setup_end_union',R('80000928','80000940')+R('80000fec','80000ff6'),2205)
    add('VL_setup_end_union',R('80000490','800004c8')+R('80000ff6','80001000'),735)
    add('op_setup_end_union',R('80000458','80000490')+R('80001000','80001018'),105)
    add('seed_setup_end_union',R('800003c8','800003fe')+R('80000442','80000458')+R('80001aec','80001b02'),3)
    add('RNG_overrides_union',R('800003fe','80000442')+R('80001a66','80001a74')+R('80001a7c','80001a98'),192)
    add('main_prologue_union',R('80000352','800003c8'),1)
    sym=read(S/'spike/symbols.json');add('capacity',region(c,sym['capacity'],sym['op_0']),1)
    bss=4*((sym['__bss_end']-sym['__bss_start']+7)//8)+1
    upper=results['spike']['mandatory']+sum(x['total'] for x in terms)+bss+20000
    for p,h in pins.items():need(sha(p)==h,'Postflight drift '+p)
    evidence={str(p):sha(p) for p in [H/'inspect.py',H.parent/'compiled_audit01/inspect.py',S/'pins.json',S/'proof.json',S/'execution_receipt.json',S/'host_extra.h']}
    result=dict(status='ACTUAL_LINKED_SYMBOLIC_AND_HOST_PASS_COST_'+('WITHIN_3M' if upper<=3000000 else 'HOLD'),
        reference=False,DUT=False,compile_attempts_per_backend=1,execution=receipt,host_outcomes=41,
        host_new_load_probes_per_completed_run=1072,host_C_not_RV64_execution=True,compiled=results,
        symbolic_negative=negative,terms=terms,BSS_instructions=bss,success_runtime_allowance=20000,
        all_equal_whole_CFG_upper=upper,headroom=3000000-upper,cost_is_static_not_retired=True,
        failure_path_cost_bound_claimed=False,independent_review_pending=True,pins_unchanged=True,input_pin_count=len(pins),evidence=evidence)
    save(H/'RESULT.json',result)
    print(json.dumps({k:result[k] for k in ['status','all_equal_whole_CFG_upper','headroom','host_outcomes','pins_unchanged']}))


if __name__=='__main__':main()
