"""Readonly linked CFG inventory and successful-path conservative count; no ISA execution."""
import hashlib
import json
from pathlib import Path
import re
import struct
H=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def require(b,s):
    if not b:raise ValueError(s)
def save(p,x):
    with p.open('x') as f:json.dump(x,f,indent=2);f.write('\n')
def assembly(p):
    return {int(m[1],16):dict(insn=int(m[2],16),op=m[3],args=m[4].strip()) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([a-z0-9.]+)\s*([^\n]*)',p.read_text(),re.M)}
def region(code,lo,hi):
    result=[];pc=lo
    while pc<hi:
        require(pc in code,'Actual instruction boundary '+hex(pc));result.append(pc)
        pc+=4 if code[pc]['insn']&3==3 else 2
    require(pc==hi,'Actual region endpoint');return result
def signed(x,n):return x-(1<<n) if x&(1<<(n-1)) else x
def filebytes(raw,va,n):
    ph=struct.unpack_from('<Q',raw,32)[0];size,count=struct.unpack_from('<HH',raw,54)
    hits=[]
    for i in range(count):
        kind,flags,off,v,p,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',raw,ph+i*size)
        if kind==1 and v<=va and va+n<=v+filesz:hits.append(raw[off+va-v:off+va-v+n])
    require(len(hits)==1,'File-backed symbol range');return hits[0]
def main():
    pins=read(H/'pins.json');proof=read(H/'proof.json');execution=read(H/'execution_receipt.json')
    for p,h in pins.items():require(sha(p)==h,'Pre pins '+p)
    require(type(execution['returncode']) is int and execution['returncode']==0 and not execution['timed_out'],'Actual software wait0')
    require(len(proof['host'])==31,'31 actual Host outcomes')
    for r in proof['host']:require(type(r['returncode']) is int and r['returncode']==r['expected_returncode'] and not r['timed_out'] and sha(r['log'])==r['sha256'],'Actual Host receipt/log')
    static=read(H.parent/'full_e64_m2_static_feasibility01/ANALYSIS.json')
    header=(H/'original/operations.h').read_text()
    constants=lambda t:[int(x,16) for x in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)',t)]
    fp=constants(header.split('fp_expected[10][64]')[1].split('};')[0]);inputs=constants(header.split('fp_inputs[8]')[1].split('};')[0])
    require(len(fp)==640 and len(inputs)==8,'Actual FP dimensions')
    expected=b''.join(struct.pack('<Q',v) for v in fp);inputbytes=b''.join(struct.pack('<Q',v) for v in inputs)
    dictionary=b''.join(struct.pack('<Q',v) for v in constants((H/'dictionary.h').read_text()))
    indices=b''.join(struct.pack('<5H',*r['indices']) for r in read(H/'sequence.json'))
    compiled={}
    for backend in ('soc','spike'):
        root=H/backend;symbols=read(root/'symbols.json');code=assembly(root/'program.dis');raw=(root/'program.elf').read_bytes()
        require(sha(root/'program.elf')==proof['backends'][backend]['sha256'],'Actual ELF pin')
        require(raw.count(expected)==1 and filebytes(raw,symbols['fp_expected'],5120)==expected,'FP640 unique exact ELF bits')
        require(filebytes(raw,symbols['fp_inputs'],64)==inputbytes,'Actual ELF input symbol bits')
        require(filebytes(raw,symbols['expected_dictionary'],len(dictionary))==dictionary and raw.count(dictionary)==1,'Complete dictionary exact linked')
        require(filebytes(raw,symbols['expected_indices'],len(indices))==indices,'All5985x5 exact indices')
        body={pc:x for pc,x in code.items() if symbols['arithmetic_main']<=pc<symbols['capacity']}
        zeros=[pc for pc,x in body.items() if x['op']=='sd' and x['args'].startswith('zero,') and re.search(r'<mask(?:\+0x[0-9a-f]+)?>$',x['args'])]
        require(len(zeros)==16 and symbols['mask']%8==0,'Actual mask16SD/alignment')
        zr=region(code,zeros[0]-4,zeros[-1]+4);regs={3:symbols['__global_pointer$']};addresses=[]
        for pc in zr:
            x=code[pc]['insn'];opcode=x&127
            if opcode==0x17:regs[(x>>7)&31]=(pc+signed(x&0xfffff000,32))&((1<<64)-1)
            else:
                require(opcode==0x23 and (x>>12)&7==3 and (x>>20)&31==0,'No mask branch/call/fence/RVV')
                rs1=(x>>15)&31;require(rs1 in regs,'Known linked clear base')
                addresses.append(regs[rs1]+signed((x>>25<<5)|((x>>7)&31),12))
        require(addresses==list(range(symbols['mask'],symbols['mask']+128,8)),'Actual full128 mask address coverage')
        writes=[(pc,x) for pc,x in body.items() if x['op']=='sd' and re.fullmatch(r's2,\d+\(s1\)',x['args'])]
        require([int(x['args'].split(',')[1].split('(')[0]) for _,x in writes]==list(range(0,272,8)),'34 complete SD fresh output')
        first_compare=[pc for pc,x in body.items() if x['op']=='beq' and x['args'].startswith('a1,a2,') and '<arithmetic_main' in x['args']]
        require(len(first_compare)==1,'Unique first packed equality branch')
        first=first_compare[0];resume=int(code[first]['args'].split(',')[-1].split()[0],16)
        end=[pc for pc,x in body.items() if pc>resume and x['op']=='ld' and x['args']=='a5,0(s10)'][0]
        compare=region(code,first-12,first+4)+region(code,resume,end)
        reads=[(pc,code[pc]) for pc in compare if code[pc]['op']=='ld' and re.fullmatch(r'\w+,\d+\(s1\)',code[pc]['args'])]
        require([int(x['args'].split(',')[1].split('(')[0]) for _,x in reads]==list(range(0,272,8)),'34 whole LD exact272 no padded48B')
        require(not any(code[pc]['op'] in ('lw','lwu') for pc in compare),'No typed16/32 tail inherited')
        fpa=[pc for pc,x in body.items() if x['op']=='sd' and x['args']=='a4,-8(a3)'];fpb=[pc for pc,x in body.items() if x['op']=='sd' and x['args']=='a5,0(a0)']
        require(len(fpa)==len(fpb)==1,'Actual a/b FP store sites')
        lo=fpa[0]-22;hi=fpb[0]+12;loop=region(code,lo,hi)
        require([code[pc]['op'] for pc in loop]==['andi','andi','slli','slli','add','add','ld','ld','addi','sd','sd','addiw','addiw','addi','bne'],'Actual FP15 scalar instructions and a-before-b')
        require(int(code[loop[-1]]['args'].split(',')[-1].split()[0],16)==lo,'Actual FP backedge')
        setup=region(code,lo-36,lo)
        for name in ('<a+0x100>','<a>','<b>','<fp_inputs>'):require(any(name in code[pc]['args'] for pc in setup),'Full32 uint64 FP range '+name)
        gate=[pc for pc,x in body.items() if x['op']=='bltu' and x['args'].startswith('a4,a5,') and int(x['args'].split(',')[-1].split()[0],16)==lo-36]
        require(len(gate)==1 and code[gate[0]-2]['args']=='a4,24','FP op-only gate, no VL/start bypass')
        require(sum(x['op']=='j' and int(x['args'].split()[0],16)==gate[0]-4 for x in body.values())==3,'Every later trial re-enters FP gate')
        require(code[hi]['op']=='j' and int(code[hi]['args'].split()[0],16)==writes[0][0]-2,'Refresh returns before every fresh output')
        frames=[dict(pc=hex(pc),bytes=-int(x['args'].split(',')[-1].split()[0])) for pc,x in code.items() if x['op']=='addi' and x['args'].startswith('sp,sp,-')]
        require(code[symbols['arithmetic_main']]['args']=='sp,sp,-288','Actual main frame288')
        require(sum(f['bytes'] for f in frames)<65536 and symbols['__stack_top']-symbols['__bss_end']>=65536,'Actual frame/map reserve')
        require(proof['backends'][backend]['helper_instructions']==458 and not proof['backends'][backend]['extra_vector'],'Original helper/no extraRVV')
        compiled[backend]=dict(elf_sha256=sha(root/'program.elf'),mask_clear_region=[hex(pc) for pc in zr],mask_clear_instructions=len(zr),mask_addresses=[hex(a) for a in addresses],output_store_pcs=[hex(pc) for pc,_ in writes],output_read_pcs=[hex(pc) for pc,_ in reads],FP_loop_pcs=[hex(pc) for pc in loop],FP_setup_pcs=[hex(pc) for pc in setup],FP_gate=hex(gate[0]),FP_input_address=hex(symbols['fp_inputs']),FP_gold_address=hex(symbols['fp_expected']),FP_word_stores=120960,FP_calls=1890,FP_table_unique=True,main_frame=288,frames=frames,stack_gap=symbols['__stack_top']-symbols['__bss_end'],dictionary_bytes=len(dictionary),indices_bytes=len(indices),helper_instructions=458,extra_RVV=0)
    code=assembly(H/'spike/program.dis');R=lambda lo,hi:region(code,int(lo,16),int(hi,16));terms=[]
    def add(name,pcs,n,kind='mandatory'):
        terms.append(dict(name=name,pcs=[hex(p) for p in pcs],instructions_per_visit=len(pcs),visits=n,instructions=len(pcs)*n,kind=kind))
    add('mask_clear_address_included',R('800004aa','80000506'),2205)
    add('mask_mode0',R('8000051e','80000540'),32*735)
    add('mask_mode1_even',[0x8000051e,0x8000072c]+R('80000748','80000756'),16*735)
    add('mask_mode1_odd',R('80000748','80000750')+R('80000522','80000540'),16*735)
    add('mask_mode2_dispatch',[0x8000051e,0x8000072c],6*735)
    add('mask_mode2_predicate',R('80000730','8000073e'),32*735)
    add('mask_mode2_selected',R('80000522','80000540'),5*735)
    add('mask_mode2_skip',R('8000073e','80000744'),27*735)
    add('mask_mode2_skip_backedge',[0x80000744],26*735)
    add('FP_setup_and_return',R('80000ad0','80000af4')+[0x80000b1a],1890)
    add('FP_loop',R('80000af4','80000b1a'),32*1890)
    add('call_gate_fresh_helper_dispatch_firstcompare',R('8000056a','8000065e'),5985)
    add('remaining33_word_compare_counters',R('80000912','80000a7a'),5985)
    add('original_helper_leaf13',list(range(13)),5985)
    core=sum(x['instructions'] for x in terms)
    add('later_start_selection_union',R('80000b78','80000b9c'),3780,'upper')
    add('mask_group_setup_end_union',R('80000506','8000051e')+R('80000540','8000056a')+R('80000a7a','80000a86')+R('80000756','8000075c'),2205,'upper')
    add('VL_setup_end_union',R('8000047c','800004aa')+R('80000a86','80000a90'),735,'upper')
    add('op_setup_end_union',R('80000440','8000047c')+R('80000a90','80000aa4'),105,'upper')
    add('seed_setup_end_union',R('800003c0','800003f6')+R('80000432','80000440')+R('80000cb8','80000cc8'),3,'upper')
    add('seed_RNG_all_corner_union',R('800003f6','80000432')+R('80000c62','80000c6e')+R('80000c82','80000ca0'),96,'upper')
    add('main_prologue',R('80000352','800003c0'),1,'upper')
    sym=read(H/'spike/symbols.json');bss=4*((sym['__bss_end']-sym['__bss_start']+7)//8)+1;tail=20000
    upper=sum(x['instructions'] for x in terms)+bss+tail
    for p,h in pins.items():require(sha(p)==h,'Post pins '+p)
    result=dict(status='HOST_COMPILED_STATIC_COST_HOLD' if upper>3000000 else 'HOST_COMPILED_STATIC_COST_ELIGIBLE_NO_REFERENCE_AUTHORIZATION',execution=execution,Host_runs=31,compiled=compiled,terms=terms,mandatory_core=core,positive_path_conservative_upper=upper,BSS_instructions=bss,terminal_runtime_allowance=tail,cost_target=3000000,static_CFG_not_retired_measurement=True,actual_firmware_instruction_count=None,pins_pre_post_unchanged=True,fflags_oracle=False,reference_started=False,DUT_started=False)
    save(H/'compiled_review.json',result)
    print(json.dumps({k:result[k] for k in ('status','mandatory_core','positive_path_conservative_upper','actual_firmware_instruction_count')}),flush=True)
if __name__=='__main__':main()
