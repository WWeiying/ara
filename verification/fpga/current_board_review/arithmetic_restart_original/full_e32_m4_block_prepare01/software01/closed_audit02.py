"""Closed-artifact identity and finite acyclic scalar CFG analysis, no ISA run.

Only four linked scalar leaf routines are traversed. Actual output bytes are
assumed equal to the pinned source oracle for positive cost; this is NOT an
architectural execution/reference. Branch/address taints additionally prove
cache read coverage does not depend on actual result values.
"""
import collections
import hashlib
import json
from pathlib import Path
import re
import struct
import time

HERE=Path(__file__).resolve().parent
A=HERE.parents[1]
MODEL=A/'full_e32_m4_source_model01/generated01'
SOURCE=A/'full_e32_m4_integrated_source_proposal01'
MASK=(1<<64)-1
ARCH=Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04')
def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def save(p,obj):
    with p.open('x') as f:json.dump(obj,f,indent=2);f.write('\n')
def sign(v,n):return v-(1<<n) if v&(1<<(n-1)) else v

def executable_bytes(elf,pc,size):
    h=struct.unpack_from('<16sHHIQQQIHHHHHH',elf)
    require(h[0][:6]==b'\x7fELF\x02\x01' and h[2]==243,'RV64 little-endian ELF')
    matches=[]
    for n in range(h[10]):
        kind,flags,off,va,pa,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',elf,h[5]+n*h[9])
        if kind==1 and flags&1 and va<=pc and pc+size<=va+filesz:
            matches.append(elf[off+pc-va:off+pc-va+size])
    require(len(matches)==1,'Unique file-backed executable address '+hex(pc))
    return matches[0]

def instruction_bytes(x):return x['insn'].to_bytes(4 if x['insn']&3==3 else 2,'little')

class Leaf:
    def __init__(self,functions,symbols,elf):
        self.functions=functions;self.symbols=symbols;self.segments=[]
        startup=functions['_start'][:2]
        require([(x['op'],x['args'].split('#')[0].strip().split(',')[:2]) for x in startup]==[('auipc',['gp','0x42']),('addi',['gp','gp'])],'Exact linked startup GP setup')
        gp=startup[0]['pc']+sign((int(startup[0]['args'].split(',')[1],0)<<12)&0xffffffff,32)
        gp+=int(startup[1]['args'].split('#')[0].strip().split(',')[-1],0)
        require(gp==symbols['__global_pointer
        h=struct.unpack_from('<16sHHIQQQIHHHHHH',elf)
        for n in range(h[10]):
            kind,flags,off,va,pa,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',elf,h[5]+n*h[9])
            if kind==1:self.segments.append((va,elf[off:off+filesz],memsz))
    def initial(self,addr,size):
        for va,data,memsz in self.segments:
            if va<=addr and addr+size<=va+memsz:
                return int.from_bytes(data[addr-va:addr-va+size].ljust(size,b'\0'),'little')
        raise ValueError('Unknown ELF memory '+hex(addr))
    def walk(self,name,arg,output=None):
        code={x['pc']:x for x in self.functions[name]};pc=min(code);seen=set();regs={'zero':(0,set()),'a0':(arg,{'ARG'}),'sp':(0x90000000,{'SP'}),'gp':(self.gp,{'GP'})}
        stack={};writes={};events=[];branches=[];counts=collections.Counter()
        def get(r):
            require(r in regs,'Unknown leaf register '+r+' at '+hex(pc));return regs[r]
        def put(r,value,taints):
            if r!='zero':regs[r]=(value&MASK,taints)
        def address(expr):
            m=re.fullmatch(r'(-?\d+)\((\w+)\)',expr);require(m is not None,'Memory operand '+expr)
            base,t=get(m[2]);require(type(base) is int,'Opaque address');return (base+int(m[1]))&MASK,t
        def kind(addr,size):
            s=self.symbols
            if 0x8ffff000<=addr<0x90000100:return 'STACK'
            for tag,sym,length in [('OUT','out',520),('ID','e32m4_expected_ids',107730),('GOLD','e32m4_expected_blocks',144128),
                ('MASK','mask',128),('A','a',512),('B','b',512),('FP','fp_inputs',32)]:
                if s[sym]<=addr and addr+size<=s[sym]+length:return tag
            return 'ROM'
        while True:
            require(pc in code and pc not in seen and len(seen)<1000,'Finite acyclic scalar CFG '+name+' '+hex(pc));seen.add(pc)
            x=code[pc];op=x['op'];args=x['args'].split('#')[0].strip();parts=[v.strip() for v in args.split(',')] if args else []
            nxt=pc+(4 if x['insn']&3==3 else 2);counts[op]+=1
            if op=='ret':break
            if op in ('ld','lw','lwu','lhu','lbu'):
                rd,expr=parts;size={'ld':8,'lw':4,'lwu':4,'lhu':2,'lbu':1}[op];addr,taint=address(expr);k=kind(addr,size)
                require(not (name.startswith('e32m4_packed') and ('OUT' in taint or 'GOLD' in taint)),'Cache address depends on result data')
                if k=='STACK':require((addr,size) in stack,'Restore initialized stack slot');v,t=stack[(addr,size)]
                elif k=='OUT' and output is not None:
                    off=addr-self.symbols['out'];v=int.from_bytes(output[off:off+size],'little');t={'OUT'}
                else:
                    v=sum(writes.get(addr+i,(self.initial(addr+i,1)))<<(8*i) for i in range(size));t={k}
                if op=='lw':v=sign(v,32)&MASK
                regs[rd]=(v,t);events.append(dict(pc=hex(pc),op=op,kind=k,address=addr,size=size,value=v if type(v)is int else None))
            elif op in ('sd','sw','sb'):
                rs,expr=parts;size={'sd':8,'sw':4,'sb':1}[op];addr,taint=address(expr);k=kind(addr,size)
                if rs not in regs:
                    require(k=='STACK' and re.fullmatch(r's\d+',rs),'Only ABI saves may carry opaque entry values');regs[rs]=('caller:'+rs,{'CALLER'})
                v,t=get(rs)
                if k=='STACK':stack[(addr,size)]=(v,t)
                else:
                    require(type(v)is int,'Known business store value')
                    for i in range(size):writes[addr+i]=(v>>(8*i))&255
                events.append(dict(pc=hex(pc),op=op,kind=k,address=addr,size=size,value=(v&((1<<(8*size))-1)) if type(v)is int else None))
            elif op=='beq':
                left,right,target=parts;lv,lt=get(left);rv,rt=get(right)
                if name.startswith('e32m4_packed'):require(lt|rt=={'ID'},'Cache branch depends only on exact immutable IDs')
                taken=lv==rv;dest=int(target.split()[0],16);branches.append(dict(pc=hex(pc),taken=taken,taint=sorted(lt|rt)))
                if taken:nxt=dest
            elif op=='j':nxt=int(parts[0].split()[0],16)
            elif op=='li':put(parts[0],int(parts[1],0),set())
            elif op=='auipc':put(parts[0],pc+sign((int(parts[1],0)<<12)&0xffffffff,32),set())
            elif op=='mv':regs[parts[0]]=get(parts[1])
            elif op in ('addi','andi','slli'):
                rd,rs,imm=parts;v,t=get(rs);i=int(imm,0);put(rd,v+i if op=='addi' else v&i if op=='andi' else v<<i,t)
            elif op in ('add','sub','or'):
                rd,l,r=parts;lv,lt=get(l);rv,rt=get(r);put(rd,lv+rv if op=='add' else lv-rv if op=='sub' else lv|rv,lt|rt)
            elif op in ('snez','zext.b'):
                rd,rs=parts;v,t=get(rs);put(rd,int(v!=0) if op=='snez' else v&255,t)
            else:raise ValueError('Unsupported scalar leaf opcode '+op+' '+hex(pc))
            pc=nxt
        return dict(instructions=len(seen),pcs=sorted(seen),events=events,branches=branches,op_counts=dict(counts),return_value=regs.get('a0',(None,None))[0])

def main():
    start=time.monotonic();out=HERE/'closed_audit02';out.mkdir(exist_ok=False)
    pins=read(HERE/'preflight.json')['pins']
    for p,h in pins.items():require(sha(p)==h,'Preflight source/tool drift '+p)
    immutable={str(p):sha(p) for p in HERE.rglob('*') if p.is_file() and out not in p.parents and HERE/'finish_execution02' not in p.parents}
    immutable.update(pins)
    for p in MODEL.iterdir():
        if p.is_file():immutable[str(p)]=sha(p)
    save(out/'INPUT_PINS.json',immutable)
    host=read(HERE/'host_result.json');require(len(host['runs'])==46,'Full46 actual Host outcomes')
    for r in host['runs']:
        require(type(r['returncode'])is int and r['returncode']==r['expected_returncode'] and not r['timed_out'],'Host actual outcome')
        require(sha(r['log'])==r['sha256'],'Host log binding')
    failed=read(HERE/'execution_receipt.json');require(failed['returncode']==1 and not failed['timed_out'],'Preserve initial postprocess error')
    require("KeyError: 'capacity'" in (HERE/'execution.log').read_text(),'Exact stripped-symbol schema failure')
    root=HERE/'soc';compile_receipt=read(root/'compile.log.exit.json')
    require(type(compile_receipt['returncode'])is int and compile_receipt['returncode']==0 and not compile_receipt['timed_out'],'Actual SoC compile0')
    f=read(root/'functions.json');s=read(root/'symbols.json');raw=(root/'program.elf').read_bytes()
    orig=[x for rows in read(HERE/'original_disassembly/functions.json').values() for x in rows];orig.sort(key=lambda x:x['pc'])
    original_path=ARCH/'overlay/opt/ara-tests/rvv_matrix_e32_m4'
    assembly_path=ARCH/'rvv_matrix_e32_m4.S'
    require(sha(original_path)=='4e537be1270d607f847b8c7d3d4e7be76b9b7408d184effc33a9c066cb811cf9','Exact archived original ELF')
    require(sha(assembly_path)=='878be135cd439f7a481312e7afd4b2ce4203806ce5f92c453000918f75c7316b','Exact original assembly')
    original_raw=original_path.read_bytes();source_windows={};current=None
    for line in assembly_path.read_text().splitlines():
        line=line.split('#')[0].strip()
        if not line or line.startswith('.'):continue
        if line.endswith(':'):
            current=line[:-1];source_windows[current]=[]
        else:
            require(current is not None,'Assembly instruction owner')
            source_windows[current].append(re.sub(r'\s+','',line))
    order=['capacity']+[f'op_{i}' for i in range(35)]
    require(list(source_windows)==order,'Exact original source helper order')
    for x in orig:
        require(executable_bytes(original_raw,x['pc'],len(instruction_bytes(x)))==instruction_bytes(x),'Original disassembly/file code binding')
    for w in f.values():
        for x in w:require(executable_bytes(raw,x['pc'],len(instruction_bytes(x)))==instruction_bytes(x),'Compiled disassembly/file code binding')
    helpers={};helper_bytes=bytearray();helperpcs=set()
    original_end=0x10906;compiled_end=s['capacity'];whole_original=[]
    for name in order:
        w=f[name];require(len(w)==(3 if name=='capacity' else 13),'Actual original window length')
        require([re.sub(r'\s+','',x['op']+x['args'].split('#')[0]) for x in w]==source_windows[name],'Exact source assembly instruction window '+name)
        needle=[x['insn'] for x in w];matches=[i for i in range(len(orig)-len(w)+1) if [x['insn'] for x in orig[i:i+len(w)]]==needle]
        require(len(matches)==1,'Unique complete instruction window in stripped original '+name)
        matched=orig[matches[0]:matches[0]+len(w)]
        for original_x,compiled_x in zip(matched,w):
            require(original_x['pc']==original_end and compiled_x['pc']==compiled_end,'Contiguous full source-order windows '+name)
            original_end+=len(instruction_bytes(original_x));compiled_end+=len(instruction_bytes(compiled_x))
        whole_original.extend(matched)
        helpers[name]=dict(original_pc=hex(orig[matches[0]]['pc']),compiled_pc=hex(w[0]['pc']),instructions=len(w))
        for x in w:helper_bytes.extend(x['insn'].to_bytes(4 if x['insn']&3==3 else 2,'little'));helperpcs.add(x['pc'])
    require(hashlib.sha256(helper_bytes).hexdigest()=='d44dea9535d297c3c6dc1894db7086c82ca5fb1ec8c32a4f891450b7676c417e','Full458/1688 original helper bytes')
    require(original_end==0x10f9e and executable_bytes(original_raw,0x10906,1688)==helper_bytes,'Exact original full contiguous region')
    code={x['pc']:x for w in f.values() for x in w}
    extra=[x for pc,x in code.items() if pc not in helperpcs and x['insn']&3==3 and
        (x['insn']&127==0x57 or (x['insn']&127 in (7,39) and (x['insn']>>12)&7 in (0,5,6,7)))]
    require(not extra,'No extra RVV')
    own=[x for n,w in f.items() if n.startswith('e32m4_') or n in ('arithmetic_main','number','failure.part.0') for x in w]
    require(not [x for x in own if x['insn']&3==3 and (x['insn']&127==0x0f or (x['insn']&127==0x73 and (x['insn']>>12)&7))],'No additional scalar CSR/fence')
    require(s['out']%8==s['mask']%8==s['e32m4_expected_blocks']%8==0,'Actual8B alignment')
    gap=s['__stack_top']-s['__bss_end'];require(gap>=65536,'Actual stack reserve')
    for name in ('dictionary64.bin','indices_u16le.bin','fp_expected640_u32le.bin'):
        require(raw.count((MODEL/name).read_bytes())==1,'Unique exact immutable payload '+name)
    machine=Leaf(f,s,raw);rows=read(MODEL/'calls.json');gold=(MODEL/'gold_u32le.bin').read_bytes()
    names={key:next(n for n in f if n.startswith('e32m4_'+key)) for key in ('packed','initialize_output','refresh_fp','initialize_mask')}
    totals=collections.Counter();pc_visits=collections.Counter();per_call=[]
    for ordinal,row in enumerate(rows):
        cfg=machine.walk(names['packed'],s['e32m4_expected_ids']+18*ordinal,gold[ordinal*520:(ordinal+1)*520])
        require(cfg['return_value']==0,'Positive oracle cache expression')
        events=cfg['events'];actual=[e for e in events if e['kind']=='OUT'];expected=[e for e in events if e['kind']=='GOLD'];ids=[e for e in events if e['kind']=='ID']
        require([e['address']-s['out'] for e in actual]==list(range(0,520,8)) and all(e['op']=='ld' for e in actual),'Actual all65 output LD in order')
        require([e['value'] for e in ids]==row['ids'] and all(e['op']=='lhu' for e in ids),'All9 exact ID LHU')
        wanted=[];previous=None
        for n,block in enumerate(row['ids']):
            if n==8:wanted.append(s['e32m4_expected_blocks']+64*block)
            elif block!=previous:wanted.extend(s['e32m4_expected_blocks']+64*block+8*k for k in range(8))
            previous=block
        require([e['address'] for e in expected]==wanted and all(e['op']=='ld' for e in expected),'All miss/hit expected refresh addresses and tail8')
        require(len(cfg['branches'])==7,'All7 tag decisions')
        for i,b in enumerate(cfg['branches']):require(b['taken']==(row['ids'][i]==row['ids'][i+1]),'Exact adjacent tag decision')
        totals.update(cache_instructions=cfg['instructions'],actual_LD=len(actual),expected_LD=len(expected),ID_LHU=len(ids),
                      hit=sum(b['taken'] for b in cfg['branches']),miss=1+sum(not b['taken'] for b in cfg['branches']),
                      stack_store=sum(e['kind']=='STACK' and e['op']=='sd' for e in events),stack_load=sum(e['kind']=='STACK' and e['op']=='ld' for e in events))
        pc_visits.update(cfg['pcs']);per_call.append(dict(ordinal=ordinal+1,instructions=cfg['instructions'],expected_LD=len(expected)))
    require((totals['actual_LD'],totals['expected_LD'],totals['ID_LHU'],totals['hit'],totals['miss'])==(389025,124041,53865,33123,14757),'Full actual memory event scope')
    init=machine.walk(names['initialize_output'],0);ev=[e for e in init['events'] if e['kind']=='OUT']
    require([e['address']-s['out'] for e in ev]==list(range(0,520,8)) and all(e['op']=='sd' and e['value']==0x5b0000005b for e in ev),'All65 typed output SD')
    fp={};mask={};original_inputs=list(struct.unpack('<8I',(MODEL/'fp_inputs8_u32le.bin').read_bytes()))
    for seed in range(3):
        cfg=machine.walk(names['refresh_fp'],seed);stores=[e for e in cfg['events'] if e['kind'] in ('A','B')];loads=[e for e in cfg['events'] if e['kind']=='FP']
        wanted=[(s[bank]+4*i,original_inputs[((i if bank=='a' else 3*i)+seed)%8]) for i in range(128) for bank in ('a','b')]
        require([(e['address'],e['value']) for e in stores]==wanted and all(e['op']=='sw' for e in stores),'256 original ordered FP SW each call')
        require([e['address']-s['fp_inputs'] for e in loads]==list(range(0,32,4)) and all(e['op'] in ('lw','lwu') for e in loads),'8 fresh immutable FP input loads')
        fp[seed]=cfg
    for mode in range(3):
        cfg=machine.walk(names['initialize_mask'],mode);events=[e for e in cfg['events'] if e['kind']=='MASK'];clear=events[:16];selected=events[16:]
        require([e['address']-s['mask'] for e in clear]==list(range(0,128,8)) and all(e['op']=='sd' and e['value']==0 for e in clear),'16 actual ordered full clear SD')
        shadow=bytearray(128);wanted=[]
        for i in range(128):
            if mode==0 or (mode==1 and i%2) or (mode==2 and i%7==2):
                shadow[i//8]|=1<<(i%8);wanted.append((s['mask']+i//8,shadow[i//8]))
        require([(e['address'],e['value']) for e in selected]==wanted and all(e['op']=='sb' for e in selected),'Exact constant selected SB values/order, no LBU contract')
        mask[mode]=cfg
    core_terms=dict(cache=totals['cache_instructions'],output_init=init['instructions']*5985,
        FP=sum(v['instructions']*630 for v in fp.values()),mask=sum(v['instructions']*735 for v in mask.values()),original_helpers=77805)
    core=sum(core_terms.values())
    require(core>3000000,'Unexpected budget result: must complete full main CFG before any PASS')
    frames=[dict(pc=hex(x['pc']),bytes=-int(x['args'].split('#')[0].strip().split(',')[-1])) for x in code.values() if x['op']=='addi' and x['args'].startswith('sp,sp,-')]
    require(sum(x['bytes'] for x in frames)<65536,'Conservative sum of static frame allocations within reserve')
    for p,h in immutable.items():require(sha(p)==h,'Post input drift '+p)
    bound=immutable
    save(out/'PINS.json',bound);save(out/'per_call_cache.json',per_call);save(out/'cache_PC_visits.json',{hex(k):v for k,v in sorted(pc_visits.items())})
    save(out/'leaf_paths.json',dict(output=init,FP=fp,mask=mask))
    result=dict(status='HOST46_PASS_ACTUAL_SOC_COMPILE0_STATIC_COST_HOLD_NO_REFERENCE_NO_DUT',
        original_workflow_exit=failed,original_error_preserved="KeyError: capacity; stripped archive has .text label only",
        soc_compile=compile_receipt,elf_sha256=sha(root/'program.elf'),Host_runs=46,full_history_runs=30,structural_negatives=16,
        helpers=helpers,helper_instructions=458,helper_bytes=len(helper_bytes),extra_RVV=0,new_scalar_CSR_fence=0,
        original_elf_sha256=sha(original_path),original_assembly_sha256=sha(assembly_path),
        helper_region=dict(original_start='0x10906',original_end_exclusive=hex(original_end),compiled_start=hex(s['capacity']),compiled_end_exclusive=hex(compiled_end),
            source_order_contiguous=True,unique_individual_windows=36,file_backed_executable_bytes=True,sha256=hashlib.sha256(helper_bytes).hexdigest()),
        actual_cache_totals=dict(totals),full_FP_SW=483840,full_mask_SB=154350,full_output_SD=389025,
        mandatory_positive_core=core,core_terms=core_terms,
        whole_CFG_decision='Cannot meet3M: mandatory disjoint scalar leaves plus original helpers already exceed3M. Main/caller/RNG/startup add nonnegative cost; no invented exact whole-firmware count.',
        cache_control_result_independent=True,gp_from_actual_startup=hex(machine.gp),stack_gap=gap,actual_frames=frames,
        compiled_positive_CFG_not_retired_reference=True,original_C_has_fflags_oracle=False,
        spike_backend_not_compiled='Stopped after first fixed candidate already proves budget HOLD; no second variant',
        pins_unchanged=True,pin_count=len(bound),elapsed_seconds=time.monotonic()-start)
    save(out/'RESULT.json',result);print(json.dumps({k:result[k] for k in ('status','mandatory_positive_core','core_terms','actual_cache_totals','elapsed_seconds')}),flush=True)

if __name__=='__main__':main()
],'GP derived from actual startup instructions and linked symbol')
        gp_writers=[x['pc'] for rows in functions.values() for x in rows if x['args'].split(',')[0]=='gp' and x['op'] not in ('sd','sw','sb','beq','bne','blt','bge','bltu','bgeu')]
        require(gp_writers==[x['pc'] for x in startup],'No other compiled GP writers')
        self.gp=gp
        h=struct.unpack_from('<16sHHIQQQIHHHHHH',elf)
        for n in range(h[10]):
            kind,flags,off,va,pa,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',elf,h[5]+n*h[9])
            if kind==1:self.segments.append((va,elf[off:off+filesz],memsz))
    def initial(self,addr,size):
        for va,data,memsz in self.segments:
            if va<=addr and addr+size<=va+memsz:
                return int.from_bytes(data[addr-va:addr-va+size].ljust(size,b'\0'),'little')
        raise ValueError('Unknown ELF memory '+hex(addr))
    def walk(self,name,arg,output=None):
        code={x['pc']:x for x in self.functions[name]};pc=min(code);seen=set();regs={'zero':(0,set()),'a0':(arg,{'ARG'}),'sp':(0x90000000,{'SP'})}
        stack={};writes={};events=[];branches=[];counts=collections.Counter()
        def get(r):
            require(r in regs,'Unknown leaf register '+r+' at '+hex(pc));return regs[r]
        def put(r,value,taints):
            if r!='zero':regs[r]=(value&MASK,taints)
        def address(expr):
            m=re.fullmatch(r'(-?\d+)\((\w+)\)',expr);require(m is not None,'Memory operand '+expr)
            base,t=get(m[2]);require(type(base) is int,'Opaque address');return (base+int(m[1]))&MASK,t
        def kind(addr,size):
            s=self.symbols
            if 0x8ffff000<=addr<0x90000100:return 'STACK'
            for tag,sym,length in [('OUT','out',520),('ID','e32m4_expected_ids',107730),('GOLD','e32m4_expected_blocks',144128),
                ('MASK','mask',128),('A','a',512),('B','b',512),('FP','fp_inputs',32)]:
                if s[sym]<=addr and addr+size<=s[sym]+length:return tag
            return 'ROM'
        while True:
            require(pc in code and pc not in seen and len(seen)<1000,'Finite acyclic scalar CFG '+name+' '+hex(pc));seen.add(pc)
            x=code[pc];op=x['op'];args=x['args'].split('#')[0].strip();parts=[v.strip() for v in args.split(',')] if args else []
            nxt=pc+(4 if x['insn']&3==3 else 2);counts[op]+=1
            if op=='ret':break
            if op in ('ld','lw','lwu','lhu','lbu'):
                rd,expr=parts;size={'ld':8,'lw':4,'lwu':4,'lhu':2,'lbu':1}[op];addr,taint=address(expr);k=kind(addr,size)
                require(not (name.startswith('e32m4_packed') and ('OUT' in taint or 'GOLD' in taint)),'Cache address depends on result data')
                if k=='STACK':require((addr,size) in stack,'Restore initialized stack slot');v,t=stack[(addr,size)]
                elif k=='OUT' and output is not None:
                    off=addr-self.symbols['out'];v=int.from_bytes(output[off:off+size],'little');t={'OUT'}
                else:
                    v=sum(writes.get(addr+i,(self.initial(addr+i,1)))<<(8*i) for i in range(size));t={k}
                if op=='lw':v=sign(v,32)&MASK
                regs[rd]=(v,t);events.append(dict(pc=hex(pc),op=op,kind=k,address=addr,size=size,value=v if type(v)is int else None))
            elif op in ('sd','sw','sb'):
                rs,expr=parts;size={'sd':8,'sw':4,'sb':1}[op];addr,taint=address(expr);k=kind(addr,size)
                if rs not in regs:
                    require(k=='STACK' and re.fullmatch(r's\d+',rs),'Only ABI saves may carry opaque entry values');regs[rs]=('caller:'+rs,{'CALLER'})
                v,t=get(rs)
                if k=='STACK':stack[(addr,size)]=(v,t)
                else:
                    require(type(v)is int,'Known business store value')
                    for i in range(size):writes[addr+i]=(v>>(8*i))&255
                events.append(dict(pc=hex(pc),op=op,kind=k,address=addr,size=size,value=(v&((1<<(8*size))-1)) if type(v)is int else None))
            elif op=='beq':
                left,right,target=parts;lv,lt=get(left);rv,rt=get(right)
                if name.startswith('e32m4_packed'):require(lt|rt=={'ID'},'Cache branch depends only on exact immutable IDs')
                taken=lv==rv;dest=int(target.split()[0],16);branches.append(dict(pc=hex(pc),taken=taken,taint=sorted(lt|rt)))
                if taken:nxt=dest
            elif op=='j':nxt=int(parts[0].split()[0],16)
            elif op=='li':put(parts[0],int(parts[1],0),set())
            elif op=='auipc':put(parts[0],pc+sign((int(parts[1],0)<<12)&0xffffffff,32),set())
            elif op=='mv':regs[parts[0]]=get(parts[1])
            elif op in ('addi','andi','slli'):
                rd,rs,imm=parts;v,t=get(rs);i=int(imm,0);put(rd,v+i if op=='addi' else v&i if op=='andi' else v<<i,t)
            elif op in ('add','sub','or'):
                rd,l,r=parts;lv,lt=get(l);rv,rt=get(r);put(rd,lv+rv if op=='add' else lv-rv if op=='sub' else lv|rv,lt|rt)
            elif op in ('snez','zext.b'):
                rd,rs=parts;v,t=get(rs);put(rd,int(v!=0) if op=='snez' else v&255,t)
            else:raise ValueError('Unsupported scalar leaf opcode '+op+' '+hex(pc))
            pc=nxt
        return dict(instructions=len(seen),pcs=sorted(seen),events=events,branches=branches,op_counts=dict(counts),return_value=regs.get('a0',(None,None))[0])

def main():
    start=time.monotonic();out=HERE/'closed_audit02';out.mkdir(exist_ok=False)
    pins=read(HERE/'preflight.json')['pins']
    for p,h in pins.items():require(sha(p)==h,'Preflight source/tool drift '+p)
    immutable={str(p):sha(p) for p in HERE.rglob('*') if p.is_file() and out not in p.parents and HERE/'finish_execution02' not in p.parents}
    immutable.update(pins)
    for p in MODEL.iterdir():
        if p.is_file():immutable[str(p)]=sha(p)
    save(out/'INPUT_PINS.json',immutable)
    host=read(HERE/'host_result.json');require(len(host['runs'])==46,'Full46 actual Host outcomes')
    for r in host['runs']:
        require(type(r['returncode'])is int and r['returncode']==r['expected_returncode'] and not r['timed_out'],'Host actual outcome')
        require(sha(r['log'])==r['sha256'],'Host log binding')
    failed=read(HERE/'execution_receipt.json');require(failed['returncode']==1 and not failed['timed_out'],'Preserve initial postprocess error')
    require("KeyError: 'capacity'" in (HERE/'execution.log').read_text(),'Exact stripped-symbol schema failure')
    root=HERE/'soc';compile_receipt=read(root/'compile.log.exit.json')
    require(type(compile_receipt['returncode'])is int and compile_receipt['returncode']==0 and not compile_receipt['timed_out'],'Actual SoC compile0')
    f=read(root/'functions.json');s=read(root/'symbols.json');raw=(root/'program.elf').read_bytes()
    orig=[x for rows in read(HERE/'original_disassembly/functions.json').values() for x in rows];orig.sort(key=lambda x:x['pc'])
    original_path=ARCH/'overlay/opt/ara-tests/rvv_matrix_e32_m4'
    assembly_path=ARCH/'rvv_matrix_e32_m4.S'
    require(sha(original_path)=='4e537be1270d607f847b8c7d3d4e7be76b9b7408d184effc33a9c066cb811cf9','Exact archived original ELF')
    require(sha(assembly_path)=='878be135cd439f7a481312e7afd4b2ce4203806ce5f92c453000918f75c7316b','Exact original assembly')
    original_raw=original_path.read_bytes();source_windows={};current=None
    for line in assembly_path.read_text().splitlines():
        line=line.split('#')[0].strip()
        if not line or line.startswith('.'):continue
        if line.endswith(':'):
            current=line[:-1];source_windows[current]=[]
        else:
            require(current is not None,'Assembly instruction owner')
            source_windows[current].append(re.sub(r'\s+','',line))
    order=['capacity']+[f'op_{i}' for i in range(35)]
    require(list(source_windows)==order,'Exact original source helper order')
    for x in orig:
        require(executable_bytes(original_raw,x['pc'],len(instruction_bytes(x)))==instruction_bytes(x),'Original disassembly/file code binding')
    for w in f.values():
        for x in w:require(executable_bytes(raw,x['pc'],len(instruction_bytes(x)))==instruction_bytes(x),'Compiled disassembly/file code binding')
    helpers={};helper_bytes=bytearray();helperpcs=set()
    original_end=0x10906;compiled_end=s['capacity'];whole_original=[]
    for name in order:
        w=f[name];require(len(w)==(3 if name=='capacity' else 13),'Actual original window length')
        require([re.sub(r'\s+','',x['op']+x['args'].split('#')[0]) for x in w]==source_windows[name],'Exact source assembly instruction window '+name)
        needle=[x['insn'] for x in w];matches=[i for i in range(len(orig)-len(w)+1) if [x['insn'] for x in orig[i:i+len(w)]]==needle]
        require(len(matches)==1,'Unique complete instruction window in stripped original '+name)
        matched=orig[matches[0]:matches[0]+len(w)]
        for original_x,compiled_x in zip(matched,w):
            require(original_x['pc']==original_end and compiled_x['pc']==compiled_end,'Contiguous full source-order windows '+name)
            original_end+=len(instruction_bytes(original_x));compiled_end+=len(instruction_bytes(compiled_x))
        whole_original.extend(matched)
        helpers[name]=dict(original_pc=hex(orig[matches[0]]['pc']),compiled_pc=hex(w[0]['pc']),instructions=len(w))
        for x in w:helper_bytes.extend(x['insn'].to_bytes(4 if x['insn']&3==3 else 2,'little'));helperpcs.add(x['pc'])
    require(hashlib.sha256(helper_bytes).hexdigest()=='d44dea9535d297c3c6dc1894db7086c82ca5fb1ec8c32a4f891450b7676c417e','Full458/1688 original helper bytes')
    require(original_end==0x10f9e and executable_bytes(original_raw,0x10906,1688)==helper_bytes,'Exact original full contiguous region')
    code={x['pc']:x for w in f.values() for x in w}
    extra=[x for pc,x in code.items() if pc not in helperpcs and x['insn']&3==3 and
        (x['insn']&127==0x57 or (x['insn']&127 in (7,39) and (x['insn']>>12)&7 in (0,5,6,7)))]
    require(not extra,'No extra RVV')
    own=[x for n,w in f.items() if n.startswith('e32m4_') or n in ('arithmetic_main','number','failure.part.0') for x in w]
    require(not [x for x in own if x['insn']&3==3 and (x['insn']&127==0x0f or (x['insn']&127==0x73 and (x['insn']>>12)&7))],'No additional scalar CSR/fence')
    require(s['out']%8==s['mask']%8==s['e32m4_expected_blocks']%8==0,'Actual8B alignment')
    gap=s['__stack_top']-s['__bss_end'];require(gap>=65536,'Actual stack reserve')
    for name in ('dictionary64.bin','indices_u16le.bin','fp_expected640_u32le.bin'):
        require(raw.count((MODEL/name).read_bytes())==1,'Unique exact immutable payload '+name)
    machine=Leaf(f,s,raw);rows=read(MODEL/'calls.json');gold=(MODEL/'gold_u32le.bin').read_bytes()
    names={key:next(n for n in f if n.startswith('e32m4_'+key)) for key in ('packed','initialize_output','refresh_fp','initialize_mask')}
    totals=collections.Counter();pc_visits=collections.Counter();per_call=[]
    for ordinal,row in enumerate(rows):
        cfg=machine.walk(names['packed'],s['e32m4_expected_ids']+18*ordinal,gold[ordinal*520:(ordinal+1)*520])
        require(cfg['return_value']==0,'Positive oracle cache expression')
        events=cfg['events'];actual=[e for e in events if e['kind']=='OUT'];expected=[e for e in events if e['kind']=='GOLD'];ids=[e for e in events if e['kind']=='ID']
        require([e['address']-s['out'] for e in actual]==list(range(0,520,8)) and all(e['op']=='ld' for e in actual),'Actual all65 output LD in order')
        require([e['value'] for e in ids]==row['ids'] and all(e['op']=='lhu' for e in ids),'All9 exact ID LHU')
        wanted=[];previous=None
        for n,block in enumerate(row['ids']):
            if n==8:wanted.append(s['e32m4_expected_blocks']+64*block)
            elif block!=previous:wanted.extend(s['e32m4_expected_blocks']+64*block+8*k for k in range(8))
            previous=block
        require([e['address'] for e in expected]==wanted and all(e['op']=='ld' for e in expected),'All miss/hit expected refresh addresses and tail8')
        require(len(cfg['branches'])==7,'All7 tag decisions')
        for i,b in enumerate(cfg['branches']):require(b['taken']==(row['ids'][i]==row['ids'][i+1]),'Exact adjacent tag decision')
        totals.update(cache_instructions=cfg['instructions'],actual_LD=len(actual),expected_LD=len(expected),ID_LHU=len(ids),
                      hit=sum(b['taken'] for b in cfg['branches']),miss=1+sum(not b['taken'] for b in cfg['branches']),
                      stack_store=sum(e['kind']=='STACK' and e['op']=='sd' for e in events),stack_load=sum(e['kind']=='STACK' and e['op']=='ld' for e in events))
        pc_visits.update(cfg['pcs']);per_call.append(dict(ordinal=ordinal+1,instructions=cfg['instructions'],expected_LD=len(expected)))
    require((totals['actual_LD'],totals['expected_LD'],totals['ID_LHU'],totals['hit'],totals['miss'])==(389025,124041,53865,33123,14757),'Full actual memory event scope')
    init=machine.walk(names['initialize_output'],0);ev=[e for e in init['events'] if e['kind']=='OUT']
    require([e['address']-s['out'] for e in ev]==list(range(0,520,8)) and all(e['op']=='sd' and e['value']==0x5b0000005b for e in ev),'All65 typed output SD')
    fp={};mask={};original_inputs=list(struct.unpack('<8I',(MODEL/'fp_inputs8_u32le.bin').read_bytes()))
    for seed in range(3):
        cfg=machine.walk(names['refresh_fp'],seed);stores=[e for e in cfg['events'] if e['kind'] in ('A','B')];loads=[e for e in cfg['events'] if e['kind']=='FP']
        wanted=[(s[bank]+4*i,original_inputs[((i if bank=='a' else 3*i)+seed)%8]) for i in range(128) for bank in ('a','b')]
        require([(e['address'],e['value']) for e in stores]==wanted and all(e['op']=='sw' for e in stores),'256 original ordered FP SW each call')
        require([e['address']-s['fp_inputs'] for e in loads]==list(range(0,32,4)) and all(e['op'] in ('lw','lwu') for e in loads),'8 fresh immutable FP input loads')
        fp[seed]=cfg
    for mode in range(3):
        cfg=machine.walk(names['initialize_mask'],mode);events=[e for e in cfg['events'] if e['kind']=='MASK'];clear=events[:16];selected=events[16:]
        require([e['address']-s['mask'] for e in clear]==list(range(0,128,8)) and all(e['op']=='sd' and e['value']==0 for e in clear),'16 actual ordered full clear SD')
        shadow=bytearray(128);wanted=[]
        for i in range(128):
            if mode==0 or (mode==1 and i%2) or (mode==2 and i%7==2):
                shadow[i//8]|=1<<(i%8);wanted.append((s['mask']+i//8,shadow[i//8]))
        require([(e['address'],e['value']) for e in selected]==wanted and all(e['op']=='sb' for e in selected),'Exact constant selected SB values/order, no LBU contract')
        mask[mode]=cfg
    core_terms=dict(cache=totals['cache_instructions'],output_init=init['instructions']*5985,
        FP=sum(v['instructions']*630 for v in fp.values()),mask=sum(v['instructions']*735 for v in mask.values()),original_helpers=77805)
    core=sum(core_terms.values())
    require(core>3000000,'Unexpected budget result: must complete full main CFG before any PASS')
    frames=[dict(pc=hex(x['pc']),bytes=-int(x['args'].split('#')[0].strip().split(',')[-1])) for x in code.values() if x['op']=='addi' and x['args'].startswith('sp,sp,-')]
    require(sum(x['bytes'] for x in frames)<65536,'Conservative sum of static frame allocations within reserve')
    for p,h in immutable.items():require(sha(p)==h,'Post input drift '+p)
    bound=immutable
    save(out/'PINS.json',bound);save(out/'per_call_cache.json',per_call);save(out/'cache_PC_visits.json',{hex(k):v for k,v in sorted(pc_visits.items())})
    save(out/'leaf_paths.json',dict(output=init,FP=fp,mask=mask))
    result=dict(status='HOST46_PASS_ACTUAL_SOC_COMPILE0_STATIC_COST_HOLD_NO_REFERENCE_NO_DUT',
        original_workflow_exit=failed,original_error_preserved="KeyError: capacity; stripped archive has .text label only",
        soc_compile=compile_receipt,elf_sha256=sha(root/'program.elf'),Host_runs=46,full_history_runs=30,structural_negatives=16,
        helpers=helpers,helper_instructions=458,helper_bytes=len(helper_bytes),extra_RVV=0,new_scalar_CSR_fence=0,
        original_elf_sha256=sha(original_path),original_assembly_sha256=sha(assembly_path),
        helper_region=dict(original_start='0x10906',original_end_exclusive=hex(original_end),compiled_start=hex(s['capacity']),compiled_end_exclusive=hex(compiled_end),
            source_order_contiguous=True,unique_individual_windows=36,file_backed_executable_bytes=True,sha256=hashlib.sha256(helper_bytes).hexdigest()),
        actual_cache_totals=dict(totals),full_FP_SW=483840,full_mask_SB=154350,full_output_SD=389025,
        mandatory_positive_core=core,core_terms=core_terms,
        whole_CFG_decision='Cannot meet3M: mandatory disjoint scalar leaves plus original helpers already exceed3M. Main/caller/RNG/startup add nonnegative cost; no invented exact whole-firmware count.',
        cache_control_result_independent=True,stack_gap=gap,actual_frames=frames,
        compiled_positive_CFG_not_retired_reference=True,original_C_has_fflags_oracle=False,
        spike_backend_not_compiled='Stopped after first fixed candidate already proves budget HOLD; no second variant',
        pins_unchanged=True,pin_count=len(bound),elapsed_seconds=time.monotonic()-start)
    save(out/'RESULT.json',result);print(json.dumps({k:result[k] for k in ('status','mandatory_positive_core','core_terms','actual_cache_totals','elapsed_seconds')}),flush=True)

if __name__=='__main__':main()

