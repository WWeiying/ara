"""Read linked instructions and finite source-qualified paths; no ISA run."""
import hashlib
import json
from pathlib import Path
import re
import struct

H=Path(__file__).resolve().parent
S=H.parent/'software01'
A=H.parents[1]
M=A/'full_e64_m4_source_model01/generated01'

def need(ok,why):
    if not ok: raise ValueError(why)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def save(p,data):
    with Path(p).open('x') as f:json.dump(data,f,indent=2);f.write('\n')
def assembly(p):
    return {int(m[1],16):dict(insn=int(m[2],16),op=m[3],args=m[4].strip()) for m in
        re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([a-z0-9.]+)\s*([^\n]*)',Path(p).read_text(),re.M)}
def nxt(c,p):return p+(4 if c[p]['insn']&3==3 else 2)
def args(x):return x['args'].split('#')[0].strip().split(',')
def target(x):return int(args(x)[-1].split()[0],16)
def signed(x,n):return x-(1<<n) if x&(1<<(n-1)) else x
def region(c,lo,hi):
    result=[]
    while lo<hi:need(lo in c,'Instruction boundary');result.append(lo);lo=nxt(c,lo)
    need(lo==hi,'Region endpoint');return result
def mem(s):
    m=re.fullmatch(r'(-?\d+)\((\w+)\)',s);need(m is not None,'Address operand '+s)
    return int(m[1]),m[2]
def filebytes(raw,va,count):
    ph=struct.unpack_from('<Q',raw,32)[0];size,n=struct.unpack_from('<HH',raw,54);found=[]
    for i in range(n):
        k,f,o,v,p,fs,ms,al=struct.unpack_from('<IIQQQQQQ',raw,ph+i*size)
        if k==1 and v<=va and va+count<=v+fs:found.append(raw[o+va-v:o+va-v+count])
    need(len(found)==1,'Unique file-backed range');return found[0]
def base_binding(c,body,symbol,register,syms):
    hits=[p for p in body if c[p]['op']=='addi' and c[p]['args'].startswith(register+','+register+',') and '<'+symbol+'>' in c[p]['args']]
    need(len(hits)>=1,'Bound symbol '+symbol)
    for p in hits:
        old=c[p-4];need(old['op']=='auipc' and args(old)[0]==register,'Actual AUIPC base')
        need(p-4+signed(old['insn']&0xfffff000,32)+int(args(c[p])[2])==syms[symbol],'Actual linked symbol base')

def finite_path(c,start,end,kind,index,syms):
    regs={'zero':0,'gp':syms['__global_pointer$'],'s4':syms['mask'],'s7':index,
          's6':syms['a'],'s5':syms['b'],'s9':2}
    pc=start;pcs=[];clears=[];bits=[];fp=[];loads=[]
    while pc!=end:
        need(pc not in pcs and len(pcs)<600,'Acyclic finite path')
        pcs.append(pc);x=c[pc];op=x['op'];a=args(x);nextpc=nxt(c,pc)
        if op=='auipc':regs[a[0]]=pc+signed(x['insn']&0xfffff000,32)
        elif op=='addi':regs[a[0]]=regs[a[1]]+int(a[2])
        elif op=='li':regs[a[0]]=int(a[1])
        elif op in ('ld','lbu'):
            off,base=mem(a[1])
            if kind=='fp' and base=='sp':
                need(op=='ld' and off==144 and a[0]=='t3','Original per-seed stack slot')
                regs[a[0]]=index
            else:
                address=regs[base]+off
                if kind=='fp':
                    need(op=='ld' and syms['fp_inputs']<=address<syms['fp_inputs']+64 and address%8==0,'Eight actual input LD')
                    slot=(address-syms['fp_inputs'])//8;regs[a[0]]=('fp',slot);loads.append(dict(pc=hex(pc),slot=slot,address=hex(address)))
                else:
                    need(op=='lbu' and syms['mask']<=address<syms['mask']+8,'Actual mask LBU')
                    regs[a[0]]=('mask',address)
        elif op=='ori':
            previous=regs[a[1]];need(kind=='mask' and previous[0]=='mask','Mask read/OR chain')
            regs[a[0]]=('bit',previous[1],int(a[2])&255)
        elif op in ('sd','sb'):
            off,base=mem(a[1]);address=regs[base]+off;value=regs[a[0]]
            if kind=='mask' and op=='sd':
                need(value==0 and not bits,'All clear SD before selected byte stores');clears.append(dict(pc=hex(pc),address=hex(address)))
            elif kind=='mask':
                need(op=='sb' and len(clears)==16 and value[0]=='bit' and value[1]==address,'Cumulative same-byte LBU/ORI/SB')
                bit=value[2];need(bit in [1<<n for n in range(8)],'One original selected bit')
                bits.append(dict(pc=hex(pc),index=(address-syms['mask'])*8+bit.bit_length()-1,address=hex(address),bit=bit))
            else:
                need(op=='sd' and value[0]=='fp','FP scalar64 store')
                n=len(fp);i,bank=divmod(n,2);symbol='b' if bank else 'a'
                need(address==syms[symbol]+8*i and value[1]==((3*i if bank else i)+index)%8,'Actual128 FP SD order and original slot')
                fp.append(dict(pc=hex(pc),bank=symbol,index=i,input_slot=value[1],address=hex(address)))
        elif op=='j':nextpc=target(x)
        elif op=='bnez':nextpc=target(x) if regs[a[0]] else nextpc
        elif op=='beq':nextpc=target(x) if regs[a[0]]==regs[a[1]] else nextpc
        else:raise ValueError('Unexpected finite-path instruction '+op+' '+hex(pc))
        pc=nextpc
    if kind=='mask':
        need([int(x['address'],16) for x in clears]==list(range(syms['mask'],syms['mask']+128,8)),'Full16 SD clear')
        wanted=list(range(64)) if index==0 else list(range(1,64,2)) if index==1 else list(range(2,64,7))
        need([x['index'] for x in bits]==wanted,'Exact ordered selected SB events')
    else:need(len(fp)==128 and [x['slot'] for x in loads]==list(range(8)),'Full per-call FP refresh')
    return dict(pcs=list(map(hex,pcs)),instructions=len(pcs),clear=clears,bits=bits,FP_stores=fp,FP_input_loads=loads)

def comparator(c,loop,tail):
    # Symbolic XOR/OR expression proof, no data execution or successful-data assumption.
    expressions={'a2':frozenset()};observed=[];gold=[]
    def consume(p,block,is_tail):
        x=c[p];a=args(x)
        if x['op']=='ld':
            off,base=mem(a[1])
            if not is_tail:
                need(base in ('a4','a6'),'Only actual/dictionary loads inside comparator')
                which='out' if base=='a4' else 'gold';index=block*8+off//8
            else:
                need(base in ('s0','a4'),'Tail actual/dictionary loads')
                which='out' if base=='s0' else 'gold';index=off//8 if base=='s0' else 64+off//8
            need(off%8==0 and 0<=index<66,'No padded tail read')
            expressions[a[0]]=(which,index)
            (observed if which=='out' else gold).append(index)
        elif x['op']=='xor':
            left,right=expressions[a[1]],expressions[a[2]]
            need(isinstance(left,tuple) and isinstance(right,tuple) and left[1]==right[1] and {left[0],right[0]}=={'out','gold'},'Only same-word actual XOR expected')
            expressions[a[0]]=frozenset([left[1]])
        elif x['op']=='or':
            left,right=expressions[a[1]],expressions[a[2]]
            need(isinstance(left,frozenset) and isinstance(right,frozenset),'OR accumulation, not cancellable checksum')
            expressions[a[0]]=left|right
    for block in range(8):
        for p in loop:consume(p,block,False)
    for p in tail:consume(p,8,True)
    need(observed==gold==list(range(66)),'Every actual/gold word exactly once')
    need(expressions['a5']==frozenset(range(66)),'Final flag includes all66 XOR terms')
    return dict(actual_words=observed,gold_words=gold,flag_terms=sorted(expressions['a5']),tail_bytes=16)

def main():
    pins=read(S/'pins.json');receipt=read(S/'execution_receipt.json');proof=read(S/'proof.json')
    need(receipt['returncode']==0 and type(receipt['returncode']) is int and not receipt['timed_out'],'Actual Host/GCC wait0')
    for p,h in pins.items():need(sha(p)==h,'Preflight unchanged '+p)
    need(len(proof['host'])==41,'41 outcomes')
    for row in proof['host']:
        need(type(row['returncode']) is int and row['returncode']==row['expected_returncode'] and not row['timed_out'] and sha(row['log'])==row['sha256'],'Durable Host outcome')
    dictionary=(M/'dictionary64.bin').read_bytes();indices=(M/'indices_u16le.bin').read_bytes()
    fp=(M/'fp_expected640_u64le.bin').read_bytes();inputs=(M/'fp_inputs8_u64le.bin').read_bytes()
    compiled={}
    for backend in ('soc','spike'):
        root=S/backend;c=assembly(root/'program.dis');sym=read(root/'symbols.json');raw=(root/'program.elf').read_bytes()
        need(sha(root/'program.elf')==proof['backends'][backend]['sha256'],'Actual ELF')
        for symbol,data in [('e64m4_dictionary',dictionary),('e64m4_block_ids',indices),('fp_expected',fp),('fp_inputs',inputs)]:
            need(filebytes(raw,sym[symbol],len(data))==data,'Exact linked bytes '+symbol)
        body=[p for p in c if sym['arithmetic_main']<=p<sym['capacity']]
        for symbol,reg in [('out','s0'),('a','s6'),('b','s5'),('mask','s4')]:base_binding(c,body,symbol,reg,sym)
        stores=[p for p in body if c[p]['op']=='sd' and re.fullmatch(r'a5,\d+\(s0\)',c[p]['args'])]
        need([mem(args(c[p])[1])[0] for p in stores]==list(range(0,528,8)),'Actual66 output SD including guards')
        init=stores[0]-4;need(c[init]['op']=='li' and args(c[init])==['a5','91'],'Typed u64 sentinel')
        zeros=[p for p in body if c[p]['op']=='sd' and c[p]['args'].startswith('zero,') and re.search(r'<mask(?:\+0x[0-9a-f]+)?>',c[p]['args'])]
        need(len(zeros)==16,'16 static clear SD')
        mask_start=zeros[0]-4;need(c[mask_start]['op']=='auipc','Actual clear entry')
        mask_end=next(p for p in body if p>zeros[-1] and c[p]['op']=='ld' and args(c[p])==['a5','136(sp)'])
        mask_paths={str(m):finite_path(c,mask_start,mask_end,'mask',m,sym) for m in range(3)}
        fp_addr=next(p for p in body if c[p]['op']=='addi' and '<fp_inputs>' in c[p]['args'])
        fp_start=fp_addr-4
        fp_paths={str(seed):finite_path(c,fp_start,init,'fp',seed,sym) for seed in range(3)}
        # Source op gate is independent of VL/start and all later trials reenter it.
        gates=[p for p in body if c[p]['op']=='bltu' and target(c[p])==fp_start]
        need(len(gates)==1 and args(c[gates[0]-2])==['a5','24'] and args(c[gates[0]-4])==['a4','72(sp)'],'Actual op>24 gate')
        third=[p for p in body if c[p]['op']=='bgeu' and target(c[p])==init and args(c[p])[:2]==['a5','a4']]
        need(len(third)==1 and nxt(c,third[0])==fp_start,'Third-trial gate falls into FP refresh')
        need(sum(c[p]['op']=='j' and target(c[p])==gates[0]-4 for p in body)==2,'Other two restart paths return to same FP gate')
        need(any(c[p]['op']=='sd' and args(c[p])==['zero','144(sp)'] for p in body) and
             any(c[p]['op']=='sd' and args(c[p])==['a5','144(sp)'] for p in body),'Seed stack slot initializer and increment retained')
        loop_start=next(p for p in body if c[p]['op']=='lhu' and args(c[p])==['a6','0(a3)'])
        loop_branch=next(p for p in body if c[p]['op']=='bne' and target(c[p])==loop_start)
        loop_end=nxt(c,loop_branch);loop=region(c,loop_start,loop_end)
        need(len(loop)==42 and c[loop_branch]['args'].startswith('a5,a4,'),'Actual42-instruction full-block loop')
        need(any(c[p]['op']=='addi' and args(c[p])==['a4','a4','64'] for p in loop) and
             any(c[p]['op']=='addi' and args(c[p])==['a3','a3','2'] for p in loop) and
             any('<out+0x200>' in c[p]['args'] for p in loop),'8 blocks,64B actual pointer stride,2B ID stride')
        tail_branch=next(p for p in body if p>loop_end and c[p]['op']=='bnez' and args(c[p])[0]=='a5')
        tail_end=nxt(c,tail_branch);tail=region(c,loop_end,tail_end)
        need(sum(c[p]['op']=='lhu' and args(c[p])[1]=='16(a5)' for p in tail)==1,'Ninth ID at byte16')
        comp=comparator(c,loop,tail)
        trial_end=next(p for p in body if p>tail_end and c[p]['op']=='beq' and args(c[p])[:2]==['a4','a5'])
        core_end=nxt(c,trial_end)
        check_start=next(p for p in body if p>stores[-1] and c[p]['op']=='addi' and '<checks>' in c[p]['args'])
        frames=[dict(pc=hex(p),bytes=-int(args(x)[2])) for p,x in c.items() if x['op']=='addi' and x['args'].startswith('sp,sp,-')]
        need(args(c[sym['arithmetic_main']])==['sp','sp','-320'],'Actual main320 frame')
        gap=sym['__stack_top']-sym['__bss_end'];need(gap>=65536 and sum(x['bytes'] for x in frames)<65536,'Stack reserve/nonrecursive frame sum')
        core_count=len(region(c,init,loop_start))+8*len(loop)+len(region(c,loop_end,core_end))+13
        comparator_count=len(region(c,check_start,loop_start))+8*len(loop)+len(tail)
        compiled[backend]=dict(elf_sha256=sha(root/'program.elf'),helper_instructions=458,extra_RVV=0,
            output_store_pcs=list(map(hex,stores)),output_store_count=66,comparator=comp,
            comparator_regions=dict(start=hex(check_start),loop_start=hex(loop_start),loop_end=hex(loop_end),tail_end=hex(tail_end)),
            comparator_instructions_each=comparator_count,core_instructions_each=core_count,
            core_full=core_count*5985,FP_paths=fp_paths,mask_paths=mask_paths,
            core_plus_FP_SD_only_lower=core_count*5985+241920,
            positive_core_with_mask_and_FP=core_count*5985+sum(p['instructions']*630 for p in fp_paths.values())+sum(p['instructions']*735 for p in mask_paths.values()),
            main_frame=320,all_static_frame_sum=sum(x['bytes'] for x in frames),frames=frames,stack_gap=gap,
            dictionary_bytes=len(dictionary),index_bytes=len(indices),FP_expected_bytes=len(fp),
            init_entry=hex(init),mask_entry=hex(mask_start),mask_end=hex(mask_end),FP_entry=hex(fp_start),core_end=hex(core_end))
    # Whole successful CFG upper: union alternatives deliberately overcount.
    c=assembly(S/'spike/program.dis');terms=[]
    def R(lo,hi):return region(c,int(lo,16),int(hi,16))
    def add(name,pcs,visits,kind='upper_union'):
        terms.append(dict(name=name,pcs=list(map(hex,pcs)),instructions_each=len(pcs),visits=visits,total=len(pcs)*visits,kind=kind))
    b=compiled['spike'];mandatory=b['positive_core_with_mask_and_FP']
    add('all_trials_op_gate',R('8000093e','80000946'),5985)
    add('later_trials_start_selection_union',R('80000b5c','80000b72')+R('80001088','80001090')+R('80001122','8000112c'),3780)
    add('group_trial_setup_and_end',R('80000926','8000093e')+R('80000d9c','80000da6'),2205)
    add('VL_setup_and_end_union',R('8000048e','800004c6')+R('80000da6','80000db0'),735)
    add('op_setup_and_end_union',R('80000456','8000048e')+R('80000db0','80000dc8'),105)
    add('seed_setup_and_end_union',R('800003c8','800003fc')+R('80000440','80000456')+R('800018a0','800018b6'),3)
    add('RNG_all_overrides_union',R('800003fc','80000440')+R('8000181a','80001828')+R('80001830','8000184c'),64*3)
    add('main_prologue_union',R('80000352','800003c8'),1)
    add('capacity_leaf',region(c,read(S/'spike/symbols.json')['capacity'],read(S/'spike/symbols.json')['op_0']),1,'exact')
    sym=read(S/'spike/symbols.json');bss=4*((sym['__bss_end']-sym['__bss_start']+7)//8)+1
    success_tail=20000
    upper=mandatory+sum(t['total'] for t in terms)+bss+success_tail
    need(b['core_plus_FP_SD_only_lower']>3000000,'Expected decisive actual cost HOLD')
    for p,h in pins.items():need(sha(p)==h,'Postflight unchanged '+p)
    evidence={str(p):sha(p) for p in [H/'inspect.py',S/'execution_receipt.json',S/'software_status.json',S/'pins.json',S/'proof.json',S/'source_entry.json']}
    result=dict(status='HOST_COMPILED_ACTUAL_LOWERING_PASS_COST_HOLD_NO_REFERENCE_NO_DUT',
        execution=receipt,host_runs=41,full_scope_Host_runs=26,UB_trap_negative_runs=2,setup_negative_runs=13,
        compiled=compiled,positive_mandatory_core=mandatory,positive_CFG_upper=upper,
        core_plus_FP_SD_only_lower=b['core_plus_FP_SD_only_lower'],cost_gate=3000000,
        terms=terms,BSS_instructions=bss,success_runtime_tail_allowance=success_tail,
        tail_bound='Success strings/digits <256 bytes,<=6 number conversions <=20 digits; 20000 covers startup/exit and printing excluding separately counted BSS. Parking after completion excluded.',
        cost_is_static_not_measured_retired=True,failure_path_cost_bound_claimed=False,
        no_retry=True,no_reference=True,no_DUT=True,pins_unchanged=True,input_pin_count=len(pins),evidence=evidence)
    save(H/'RESULT.json',result)
    print(json.dumps({k:result[k] for k in ('status','positive_mandatory_core','positive_CFG_upper','core_plus_FP_SD_only_lower')}))

if __name__=='__main__':main()
