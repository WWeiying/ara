"""Closed artifact observer successor; no compile, Host or ISA execution."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
sys.dont_write_bytecode=True
F=Path(__file__).resolve().parent
H=F.parent
OLD=H.parent/'full_e64_m2_block_software01'
s=importlib.util.spec_from_file_location('immutable_compile_utilities',H/'prepare.py');u=importlib.util.module_from_spec(s);s.loader.exec_module(u)
s=importlib.util.spec_from_file_location('immutable_binary_reader',OLD/'inspect_compiled.py');r=importlib.util.module_from_spec(s);s.loader.exec_module(r)
sha,require,save=u.sha,u.require,u.save
def read(p):return json.loads(Path(p).read_text())
def assembly(p):
    result={}
    for line in p.read_text().splitlines():
        m=re.match(r'^[ \t]*([0-9a-f]+):[ \t]+([0-9a-f]{4,8})[ \t]+([a-z0-9.]+)[ \t]*(.*)$',line)
        if m:result[int(m[1],16)]=dict(insn=int(m[2],16),op=m[3],args=m[4].strip())
    return result
def branch_target(x):return int(x['args'].split('#')[0].split(',')[-1].split()[0],16)
def region(code,lo,hi):return r.region(code,lo,hi)
def fp_path(code,symbols,seed):
    pc=symbols['refresh_fp_period.constprop.0'];lo=pc;hi=symbols['number']
    regs={'zero':0,'gp':symbols['__global_pointer$'],'a0':seed};path=[];stores=[];loads=[]
    while True:
        require(lo<=pc<hi and pc not in path and len(path)<120,'Finite actual FP clone path')
        path.append(pc);x=code[pc];op=x['op'];arg=x['args'].split('#')[0].strip();a=[v.strip() for v in arg.split(',')]
        nxt=pc+(4 if x['insn']&3==3 else 2)
        if op=='ret':break
        if op=='auipc':regs[a[0]]=(pc+r.signed(int(a[1],0)<<12,32))&((1<<64)-1)
        elif op=='addi':require(a[1] in regs and type(regs[a[1]]) is int,'Known FP address base');regs[a[0]]=regs[a[1]]+int(a[2],0)
        elif op=='li':regs[a[0]]=int(a[1],0)
        elif op in ('ld','sd'):
            m=re.fullmatch(r'(-?\d+)\((\w+)\)',a[1]);require(m and m[2] in regs,'Decoded exact FP access base')
            addr=regs[m[2]]+int(m[1]);require(type(addr) is int,'Actual linked FP address')
            if op=='ld':
                off=addr-symbols['fp_inputs'];require(0<=off<64 and off%8==0,'Only original FP8 table loads')
                regs[a[0]]=('input',off//8);loads.append(dict(pc=hex(pc),table_index=off//8))
            else:
                banks=[(bank,(addr-symbols[bank])//8) for bank in ('a','b') if 0<=addr-symbols[bank]<256 and (addr-symbols[bank])%8==0]
                require(len(banks)==1 and a[0] in regs and isinstance(regs[a[0]],tuple),'Exact FP destination/value provenance')
                stores.append(dict(pc=hex(pc),bank=banks[0][0],index=banks[0][1],input_index=regs[a[0]][1],address=hex(addr)))
        elif op=='beq':require(a[0] in regs and a[1] in regs,'Known FP seed compare');nxt=branch_target(x) if regs[a[0]]==regs[a[1]] else nxt
        else:raise ValueError('Unexpected actual FP clone operation '+hex(pc)+' '+op)
        pc=nxt
    expected=[(b,i,((i if b=='a' else 3*i)+seed)%8) for i in range(32) for b in ('a','b')]
    require([(e['bank'],e['index'],e['input_index']) for e in stores]==expected,'All64 SD exactly ordered and source bits per seed')
    require([e['table_index'] for e in loads]==list(range(8)),'Eight table values freshly loaded on every entry')
    return dict(seed=seed,actual_instruction_count=len(path),pcs=[hex(p) for p in path],loads=loads,stores=stores)
def main():
    require(not (F/'preflight.json').exists(),'One closed artifact audit')
    initial=read(H/'source_entry.json')['pins']
    for p,h in initial.items():require(sha(p)==h,'Sealed source input '+p)
    for p in H.rglob('*'):
        if p.is_file() and F not in p.parents and p.suffix!='.pyc':initial[str(p)]=sha(p)
    initial[str(F/'audit.py')]=sha(F/'audit.py');initial[str(F/'execute.py')]=sha(F/'execute.py')
    save(F/'preflight.json',dict(status='READONLY_CONSTPROP_AND_LINE_PARSER_SUCCESSOR',pins=initial,original_ERROR=read(H/'execution_receipt.json'),completion_ERROR=read(H/'finish_artifacts01/execution_receipt.json')))
    for backend in ('soc','spike'):
        ex=read(H/backend/'compile.log.exit.json');require(ex['returncode']==0 and not ex['timed_out'],'Actual single GCC0')
    host=[]
    for directory in sorted(H.glob('host_*')):
        if directory.is_dir():
            for log in sorted(directory.glob('case*.log')):
                ex=read(str(log)+'.exit.json');require(type(ex['returncode']) is int and ex['returncode']==ex['expected_returncode'] and not ex['timed_out'],'Actual Host outcome')
                host.append(dict(variant=directory.name[5:],log=str(log),sha256=sha(log),**ex))
    require(len(host)==35,'All35 original/new/source-negative Host outcomes')
    for n in range(12):require((H/'host_original'/f'case{n}.log').read_bytes()==(H/'host_packed'/f'case{n}.log').read_bytes(),'All original/new transcripts identical')
    orig={pc:x['insn'] for pc,x in assembly(H/'original/program.dis').items()}
    require(orig[0x10898]==0x8082 and orig[0x1089a]==0x019772d7,'ret/next-helper both retained, not crossline swallowed')
    header=(H/'original/operations.h').read_text();constants=lambda t:[int(x,16) for x in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)',t)]
    fp=constants(header.split('fp_expected[10][64]')[1].split('};')[0]);inputs=constants(header.split('fp_inputs[8]')[1].split('};')[0])
    expected=b''.join(struct.pack('<Q',x) for x in fp);inputbytes=b''.join(struct.pack('<Q',x) for x in inputs)
    dictionary=b''.join(struct.pack('<Q',x) for x in constants((H/'dictionary.h').read_text()))
    rows=read(H/'sequence.json');indices=b''.join(struct.pack('<5H',*row['indices']) for row in rows)
    require(len(rows)==5985 and sum(row['op']>=25 for row in rows)==1890,'Full original source scope')
    compiled={}
    for backend in ('soc','spike'):
        root=H/backend;symbols=read(root/'symbols.json');code=assembly(root/'program.dis');raw=(root/'program.elf').read_bytes()
        names=[n for n in symbols if n=='refresh_fp_period' or n.startswith('refresh_fp_period.')]
        require(names==['refresh_fp_period.constprop.0'],'Exact sole observed clone, reject any extra clone')
        helpers={n:u.base.routine({pc:x['insn'] for pc,x in code.items()},symbols,n) for n in ['capacity']+[f'op_{i}' for i in range(35)]}
        for n,w in helpers.items():u.base.archived_window(orig,w);require(len(w)==(3 if n=='capacity' else 13),'Exact unique archived helper bytes')
        require(sum(map(len,helpers.values()))==458,'Helper458')
        allowed={x['pc'] for w in helpers.values() for x in w}
        extra=[pc for pc,x in code.items() if x['insn']&3==3 and ((x['insn']&127)==0x57 or ((x['insn']&127) in (7,39) and ((x['insn']>>12)&7) in (0,5,6,7))) and pc not in allowed]
        require(not extra,'No extra RVV')
        for name,data in [('fp_expected',expected),('fp_inputs',inputbytes),('expected_dictionary',dictionary),('expected_indices',indices)]:require(r.filebytes(raw,symbols[name],len(data))==data,'Exact linked bits '+name)
        require(raw.count(expected)==1 and raw.count(dictionary)==1,'Unique FP6405120B and complete dictionary')
        paths=[fp_path(code,symbols,seed) for seed in range(3)]
        target=symbols[names[0]];body={pc:x for pc,x in code.items() if symbols['arithmetic_main']<=pc<symbols['capacity']}
        calls=[pc for pc,x in body.items() if x['op']=='jal' and int(x['args'].split()[0],16)==target]
        require(len(calls)==1,'Only actual main call target')
        call=calls[0];caller=region(code,call-6,call+10)
        require([code[p]['op'] for p in caller]==['ld','sd','sd','jal','ld','ld','j'],'All actual caller argument/spills/return counted')
        require(code[caller[0]]['args']=='a0,32(sp)','Actual seed-only ABI argument')
        zeros=[pc for pc,x in body.items() if x['op']=='sd' and x['args'].startswith('zero,') and re.search(r'<mask(?:\+0x[0-9a-f]+)?>$',x['args'])]
        require(len(zeros)==16,'Actual16 mask SD')
        zr=region(code,zeros[0]-4,zeros[-1]+4);regs={3:symbols['__global_pointer$']};addresses=[]
        for pc in zr:
            x=code[pc]['insn'];op=x&127
            if op==0x17:regs[(x>>7)&31]=(pc+r.signed(x&0xfffff000,32))&((1<<64)-1)
            else:
                require(op==0x23 and (x>>12)&7==3 and (x>>20)&31==0,'Mask region no call/fence/RVV/branch')
                require((x>>15)&31 in regs,'Known mask base');addresses.append(regs[(x>>15)&31]+r.signed((x>>25<<5)|((x>>7)&31),12))
        require(addresses==list(range(symbols['mask'],symbols['mask']+128,8)),'Full mask offsets0..120')
        writes=[pc for pc,x in body.items() if x['op']=='sd' and re.fullmatch(r's2,\d+\(s1\)',x['args'])]
        require([int(code[p]['args'].split(',')[1].split('(')[0]) for p in writes]==list(range(0,272,8)),'All34 fresh SD')
        gate=[pc for pc,x in body.items() if x['op']=='bltu' and x['args'].startswith('a4,a5,') and branch_target(x)==caller[0]]
        require(len(gate)==1 and code[gate[0]-2]['args']=='a4,24','Refresh op>24 only, no VL/start/equality bypass')
        require(sum(x['op']=='j' and int(x['args'].split()[0],16)==gate[0]-4 for x in body.values())==3,'Every later original trial returns to FP gate')
        require(branch_target(code[caller[-1]])==writes[0]-2,'Refresh before fresh output on allFP calls')
        require(any(x['op']=='sd' and x['args']=='a5,32(sp)' for x in body.values()),'Actual original seed materialization')
        first=[pc for pc,x in body.items() if x['op']=='beq' and x['args'].startswith('a1,a2,')];require(len(first)==1,'First word equality')
        first=first[0];resume=branch_target(code[first]);tailguard=[pc for pc,x in body.items() if pc>=resume and x['op']=='ld' and x['args']=='a5,264(s1)'][0]
        compare=region(code,first-12,first+4)+region(code,resume,tailguard+4)
        reads=[pc for pc in compare if code[pc]['op']=='ld' and re.fullmatch(r'\w+,\d+\(s1\)',code[pc]['args'])]
        require([int(code[p]['args'].split(',')[1].split('(')[0]) for p in reads]==list(range(0,272,8)),'All34 LD including final16B, no padded read')
        frames=[dict(pc=hex(pc),bytes=-int(x['args'].split(',')[-1].split()[0])) for pc,x in code.items() if x['op']=='addi' and x['args'].startswith('sp,sp,-')]
        gap=symbols['__stack_top']-symbols['__bss_end'];require(gap>=65536 and sum(x['bytes'] for x in frames)<65536,'Actual map/frames bound')
        require(code[symbols['arithmetic_main']]['args']=='sp,sp,-288','Actual caller frame')
        compiled[backend]=dict(elf_sha256=sha(root/'program.elf'),refresh_symbol=names[0],refresh_pc=hex(target),refresh_extent_end=hex(symbols['number']),paths=paths,caller_pcs=[hex(p) for p in caller],caller_instruction_count=len(caller),FP_gate=hex(gate[0]),mask_clear_instruction_count=len(zr),mask_addresses=[hex(a) for a in addresses],output_store_pcs=[hex(p) for p in writes],output_read_pcs=[hex(p) for p in reads],stack_gap=gap,frames=frames,helper_instructions=458,helper_windows=helpers,extra_RVV=0,FP_expected_unique_bytes=5120,dictionary_bytes=len(dictionary),indices_bytes=len(indices))
    code=assembly(H/'spike/program.dis');R=lambda lo,hi:region(code,int(lo,16),int(hi,16));terms=[]
    def add(name,pcs,n,kind='mandatory'):
        terms.append(dict(name=name,pcs=[hex(p) if isinstance(p,int) else p for p in pcs],instructions_per_visit=len(pcs),visits=n,instructions=len(pcs)*n,kind=kind))
    add('mask_clear',R('80000788','800007e4'),2205)
    add('mask_mode0',R('800007f0','80000812'),32*735)
    add('mask_mode1_even',[0x800007f0,0x800009f0]+R('80000a0e','80000a1c'),16*735)
    add('mask_mode1_odd',R('80000a0e','80000a16')+R('800007f4','80000812'),16*735)
    add('mask_mode2_dispatch',[0x800007f0,0x800009f0],6*735)
    add('mask_mode2_predicate',R('800009f4','80000a04'),32*735)
    add('mask_mode2_selected',R('800007f4','80000812'),5*735)
    add('mask_mode2_skip',R('80000a04','80000a0a'),27*735)
    add('mask_mode2_backedge',[0x80000a0a],26*735)
    add('call_gate_fresh_dispatch_firstcompare',R('80000838','80000930'),5985)
    add('remaining33compares_counters',R('80000bca','80000d32'),5985)
    add('original_helper13',list(range(13)),5985)
    for path in compiled['spike']['paths']:add('FP_actual_seed'+str(path['seed']),path['pcs'],630)
    add('FP_actual_all_caller_spills_setup_return',compiled['spike']['caller_pcs'],1890)
    core=sum(t['instructions'] for t in terms)
    add('later_start_selection_union',R('80000df0','80000e16'),3780,'upper')
    add('mask_group_setup_end_union',R('800007e4','800007f0')+R('80000812','80000838')+R('80000d32','80000d3c')+R('80000a1c','80000a22'),2205,'upper')
    add('VL_setup_end_union',R('80000756','80000788')+R('80000d3c','80000d46'),735,'upper')
    add('op_setup_end_union',R('80000724','80000756')+R('80000d46','80000d5a'),105,'upper')
    add('seed_setup_end_union',R('80000694','800006cc')+R('80000708','80000724')+R('80000f36','80000f46'),3,'upper')
    add('seed_RNG_corner_union',R('800006cc','80000708')+R('80000ee0','80000eec')+R('80000f00','80000f1e'),96,'upper')
    add('main_prologue',R('8000061e','80000694'),1,'upper')
    symbols=read(H/'spike/symbols.json');bss=4*((symbols['__bss_end']-symbols['__bss_start']+7)//8)+1;allowance=20000
    upper=sum(t['instructions'] for t in terms)+bss+allowance;old=read(OLD/'compiled_review.json')['positive_path_conservative_upper'];saving=old-upper
    # Gate both actual compiled whole-CFG upper and its net change, not the witness.
    status='HOST_COMPILED_FULL_CFG_ELIGIBLE_REFERENCE_NOT_AUTHORIZED' if upper<=3000000 and saving>=75000 else 'HOST_COMPILED_FULL_CFG_COST_HOLD'
    for p,h in initial.items():require(sha(p)==h,'Pre/post artifacts unchanged '+p)
    result=dict(status=status,original_software_wrapper_ERROR=read(H/'execution_receipt.json'),first_completion_ERROR=read(H/'finish_artifacts01/execution_receipt.json'),Host_runs=35,host=host,compiled=compiled,terms=terms,mandatory_core=core,positive_path_conservative_upper=upper,old_upper=old,net_saving=saving,BSS_instructions=bss,terminal_runtime_allowance=allowance,static_CFG_not_retired_measurement=True,actual_firmware_instruction_count=None,helper_original_scope=458,old_HOLD_preserved=True,pins_pre_post_unchanged=True,reference_executed=False,DUT_executed=False,fflags_oracle=False)
    save(F/'RESULT.json',result);save(F/'pins.json',initial)
    print(json.dumps({k:result[k] for k in ('status','Host_runs','mandatory_core','positive_path_conservative_upper','net_saving')}),flush=True)
if __name__=='__main__':main()
