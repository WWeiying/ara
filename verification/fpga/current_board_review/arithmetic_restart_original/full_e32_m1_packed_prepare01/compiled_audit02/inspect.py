#!/usr/bin/env python3
"""Inspect the sole mask-clear compile and bound its actual positive CFG."""
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
SOFT=HERE.parent/'software02'
OLD=HERE.parent/'software01'
spec=importlib.util.spec_from_file_location('immutable_static_reader',HERE.parent/'compiled_audit01/inspect03.py')
reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
read,save,sha,require,assembly=reader.read,reader.save,reader.sha,reader.require,reader.assembly
def region(code,lo,hi):
    lo=int(lo,16) if isinstance(lo,str) else lo;hi=int(hi,16) if isinstance(hi,str) else hi
    result=[];pc=lo
    while pc<hi:
        require(pc in code,'Actual instruction boundary '+hex(pc));result.append(pc)
        pc+=4 if code[pc]['insn']&3==3 else 2
    require(pc==hi,'Actual region end '+hex(hi));return result
def signed(x,b):return x-(1<<b) if x&(1<<(b-1)) else x
def main():
    pins=read(SOFT/'pins.json')
    for p,h in pins.items():require(sha(p)==h,'Pinned input drift '+p)
    execution=read(SOFT/'execution_receipt.json');proof=read(SOFT/'proof.json')
    require(type(execution['returncode']) is int and execution['returncode']==0 and not execution['timed_out'],'Host compile actual0')
    require(len(proof['new_host_runs'])==14 and len(proof['reused_original_host_runs'])==12,'14 new/12 reused Host')
    for r in proof['new_host_runs']+proof['reused_original_host_runs']:
        require(type(r['returncode']) is int and r['returncode']==r['expected_returncode'] and not r['timed_out'],'Host receipt')
        require(sha(r['log'])==r['sha256'],'Host log unchanged')
    candidate=(SOFT/'case.c').read_text()
    require(candidate.replace('#include "mask_clear.h"\n','').replace('                initialize_mask_zero(mask);',
        '                for(unsigned i=0;i<128;++i)mask[i]=0;')==(OLD/'case.c').read_text(),'One source delta')
    rows=read(SOFT/'sequence.json')
    require(len(rows)==5985 and sum(r['op']>=25 for r in rows)==1890,'Full source count')
    expected=b''.join(struct.pack('<Q',w) for r in rows for w in r['words'])
    require(len(expected)==813960,'Full expected ROM')
    header=(SOFT/'original/operations.h').read_text()
    fp=b''.join(struct.pack('<I',int(x,16)) for x in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)',header.split('fp_expected[10][64] = {')[1].split('};')[0]))
    require(len(fp)==2560,'Original640 uint32 table')
    compiled={}
    for backend in ('soc','spike'):
        root=SOFT/backend;symbols=read(root/'symbols.json');code=assembly(root/'program.dis')
        raw=(root/'program.elf').read_bytes()
        require(sha(root/'program.elf')==proof['backends'][backend]['sha256'],'Actual ELF bound')
        require(raw.count(fp)==raw.count(expected)==1,'Exact source FP and complete expected ROM linked once')
        body={pc:x for pc,x in code.items() if symbols['arithmetic_main']<=pc<symbols['capacity']}
        zeros=[pc for pc,x in body.items() if x['op']=='sd' and x['args'].startswith('zero,') and re.search(r'<mask(?:\+0x[0-9a-f]+)?>$',x['args'])]
        require(len(zeros)==16 and symbols['mask']%8==0,'Actual16 SD and alignment')
        zero_region=region(code,zeros[0]-4,zeros[-1]+4)
        regs={3:symbols['__global_pointer$']};addresses=[]
        for pc in zero_region:
            x=code[pc]['insn'];opcode=x&127
            if opcode==0x17:
                regs[(x>>7)&31]=(pc+signed(x&0xfffff000,32))&((1<<64)-1)
            else:
                require(opcode==0x23 and ((x>>12)&7)==3 and ((x>>20)&31)==0,'Clear path only AUIPC or SD zero, no memset/loop/fence/vector')
                rs1=(x>>15)&31;require(rs1 in regs,'Known actual clear address base')
                imm=signed(((x>>25)<<5)|((x>>7)&31),12)
                addresses.append(regs[rs1]+imm)
        require(addresses==list(range(symbols['mask'],symbols['mask']+128,8)),'Decoded actual clear covers exactly0..127')
        writes=[(pc,x) for pc,x in body.items() if x['op']=='sd' and re.fullmatch(r's4,\d+\(s6\)',x['args'])]
        loads=[(pc,x) for pc,x in body.items() if x['op']=='ld' and re.fullmatch(r'a[2357],\d+\(s6\)',x['args'])]
        for events in (writes,loads):require([int(x['args'].split(',')[1].split('(')[0]) for _,x in events]==list(range(0,136,8)),'All17 output words exact')
        fpa=[pc for pc,x in body.items() if x['op']=='sw' and x['args']=='a4,-4(a3)']
        fpb=[pc for pc,x in body.items() if x['op']=='sw' and x['args']=='a5,0(a0)']
        require(len(fpa)==len(fpb)==1,'Both FP store sites')
        loopstart=fpa[0]-22;loopend=fpb[0]+12
        loop=region(code,loopstart,loopend)
        require([code[pc]['op'] for pc in loop]==['andi','andi','slli','slli','add','add','lw','lw','addi','sw','sw','addiw','addiw','addi','bne'],'Same FP15 instruction loop')
        require(f'{loopstart:x}' in code[loop[-1]]['args'],'Actual FP backedge')
        setup=region(code,loopstart-36,loopstart)
        for symbol in ('<a+0x80>','<a>','<b>','<fp_inputs>'):
            require(any(symbol in code[pc]['args'] for pc in setup),'Full32word FP setup '+symbol)
        gate=[pc for pc,x in body.items() if x['op']=='bltu' and x['args'].startswith('a4,a5,') and int(x['args'].split(',')[-1].split()[0],16)==loopstart-36]
        require(len(gate)==1 and code[gate[0]-2]['args']=='a4,24','op>24 gate independent of VL/start')
        require(sum(x['op']=='j' and f'{gate[0]-4:x}' in x['args'] for x in body.values())==3,'Each nonfinal trial re-enters FP gate')
        require(code[symbols['arithmetic_main']]['args']=='sp,sp,-304','Actual frame304')
        frames=[-int(x['args'].split(',')[-1].split()[0]) for pc,x in code.items() if pc>=symbols['number'] and x['op']=='addi' and x['args'].startswith('sp,sp,-')]
        gap=symbols['__stack_top']-symbols['__bss_end']
        require(gap>=65536 and sum(frames)<65536,'Map and static call-frame reserve')
        require(proof['backends'][backend]['helper_instructions']==458 and not proof['backends'][backend]['extra_vector'],'Preserved36 helper routines/no added RVV')
        compiled[backend]=dict(elf_sha256=sha(root/'program.elf'),mask_address=hex(symbols['mask']),
            mask_clear_pcs=[hex(pc) for pc in zeros],mask_clear_region=[hex(pc) for pc in zero_region],
            mask_clear_instructions_per_group=len(zero_region),decoded_clear_addresses=[hex(a) for a in addresses],
            fp_gate=hex(gate[0]),fp_a_store=hex(fpa[0]),fp_b_store=hex(fpb[0]),fp_loop_start=hex(loopstart),
            fp_loop_instructions=15,fp_word_stores_predicted=120960,FP_calls=1890,
            output_store_pcs=[hex(pc) for pc,_ in writes],output_read_pcs=[hex(pc) for pc,_ in loads],
            main_frame=304,sum_all_static_frame_allocations=sum(frames),stack_gap=gap,
            helper_instructions=458,extra_vector=0,expected_ROM_bytes=813960)
    code=assembly(SOFT/'spike/program.dis')
    def R(lo,hi):return region(code,lo,hi)
    terms=[]
    def add(name,pcs,n):terms.append(dict(name=name,per_visit=len(pcs),visits=n,instructions=len(pcs)*n,pcs=[hex(pc) for pc in pcs]))
    add('mask_clear_with_address_formation',R('800004b2','8000050e'),2205)
    add('mask_mode0',R('8000051e','80000540'),32*735)
    add('mask_mode1_even',[0x8000051e,0x800006ba]+R('800006d8','800006e6'),16*735)
    add('mask_mode1_odd',R('800006d8','800006e0')+R('80000522','80000540'),16*735)
    add('mask_mode2_dispatch',[0x8000051e,0x800006ba],6*735)
    add('mask_mode2_predicate',R('800006be','800006ce'),32*735)
    add('mask_mode2_selected',R('80000522','80000540'),5*735)
    add('mask_mode2_skip',R('800006ce','800006d4'),27*735)
    add('mask_mode2_skip_loop',[0x800006d4],26*735)
    add('FP_setup',R('8000098e','800009b2')+[0x800009d8],1890)
    add('FP_loop',R('800009b2','800009d8'),32*1890)
    add('call_gate_init_compare0',R('80000564','800005fe'),5985)
    add('remaining16_compares_counters',R('8000087a','8000093e'),5985)
    add('original_helpers',list(range(13)),5985)
    core=sum(x['instructions'] for x in terms)
    overhead=[]
    def upper(name,pcs,n):
        overhead.append(dict(name=name,unique_instructions=len(set(pcs)),visits_upper=n,instructions_upper=len(set(pcs))*n,pcs=[hex(pc) for pc in sorted(set(pcs))]))
    upper('trial_start_selection',R('80000a40','80000a5e'),5985)
    upper('mask_group_setup_end',R('8000050e','8000051e')+R('80000540','80000564')+R('8000093e','8000094c')+R('800006e6','800006ea'),2205)
    upper('VL_setup_end',R('8000047c','800004b2')+R('8000094c','80000956'),735)
    upper('op_setup_end',R('80000442','8000047c')+R('80000956','80000966'),105)
    upper('seed_setup_end',R('800003c2','800003f2')+R('8000042e','80000442')+R('80000bd4','80000be6'),3)
    upper('seed_RNG_case_union',R('800003f2','8000042e')+R('80000b66','80000b6e')+R('80000b7a','80000b94'),96)
    upper('main_prologue',R('80000352','800003c2'),1)
    symbols=read(SOFT/'spike/symbols.json');bss=4*((symbols['__bss_end']-symbols['__bss_start']+7)//8)+1
    tail=20000
    total=core+sum(x['instructions_upper'] for x in overhead)+bss+tail
    oldcost=read(HERE.parent/'compiled_audit01/RESULT.json')
    require(total<=3000000,'Actual static net upper still exceeds reference budget; HOLD')
    for p,h in pins.items():require(sha(p)==h,'Pre/post unchanged '+p)
    result=dict(status='HOST_COMPILED_ACTUAL_MASK_LOWERING_AND_STATIC_COST_PASS_REFERENCE_NOT_AUTHORIZED',
        execution=execution,new_host_runs=14,reused_original_host_runs=12,compiled=compiled,terms=terms,
        overhead_upper=overhead,mandatory_core=core,positive_path_upper=total,old_positive_path_upper=oldcost['positive_path_upper'],
        conservative_upper_reduction=oldcost['positive_path_upper']-total,bss_instructions=bss,tail_allowance=tail,
        static_not_retired_measurement=True,failure_fallback_budget_not_claimed=True,pins_count=len(pins),pins_unchanged=True,
        reference_executed=False,DUT_executed=False,fflags_oracle=False)
    save(HERE/'RESULT.json',result)
    print(json.dumps({k:result[k] for k in ('status','mandatory_core','positive_path_upper','conservative_upper_reduction','pins_count')}),flush=True)
if __name__=='__main__':main()
