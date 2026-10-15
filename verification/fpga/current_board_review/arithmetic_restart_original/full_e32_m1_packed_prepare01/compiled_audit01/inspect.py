#!/usr/bin/env python3
"""Static linked-code inspection and positive-path CFG count, not ISA execution."""
import hashlib
import json
from pathlib import Path
import re
import struct
HERE=Path(__file__).resolve().parent
SOFT=HERE.parent/'software01'
def require(ok,why):
    if not ok:raise ValueError(why)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def save(p,obj):
    with p.open('x') as f:json.dump(obj,f,indent=2);f.write('\n')
def assembly(p):
    result={}
    for line in p.read_text().splitlines():
        m=re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([a-z0-9.]+)\s*(.*)',line)
        if m:result[int(m[1],16)]=dict(insn=int(m[2],16),op=m[3],args=m[4].strip())
    return result
def main():
    pins=read(SOFT/'pins.json')
    for p,h in pins.items():require(sha(p)==h,'Pinned input changed '+p)
    proof=read(SOFT/'proof.json');execution=read(SOFT/'execution_receipt.json')
    require(execution['returncode']==0 and execution['timed_out'] is False,'Real Host/compile exit')
    require(len(proof['host'])==26 and all(type(x['returncode']) is int and x['returncode']==x['expected_returncode'] and not x['timed_out'] for x in proof['host']),'All actual Host receipts')
    header=(SOFT/'original/operations.h').read_text()
    table=[int(x,16) for x in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)',header.split('fp_expected[10][64] = {')[1].split('};')[0])]
    require(len(table)==640,'Exact original640 table')
    raw=b''.join(struct.pack('<I',x) for x in table)
    original=Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04/overlay/opt/ara-tests/rvv_matrix_e32_m1')
    require(original.read_bytes().count(raw)==1,'Original ELF unique exact table')
    compiled={}
    for backend in ('soc','spike'):
        root=SOFT/backend;symbols=read(root/'symbols.json');code=assembly(root/'program.dis')
        require(sha(root/'program.elf')==proof['backends'][backend]['sha256'],'ELF identity')
        require((root/'program.elf').read_bytes().count(raw)==1,'Compiled exact FP golden table')
        body={pc:x for pc,x in code.items() if symbols['arithmetic_main']<=pc<symbols['capacity']}
        writes=[(pc,x) for pc,x in body.items() if x['op']=='sd' and re.fullmatch(r's5,\d+\(s3\)',x['args'])]
        reads=[(pc,x) for pc,x in body.items() if x['op']=='ld' and re.fullmatch(r'a[2357],\d+\(s3\)',x['args'])]
        for events in (writes,reads):
            require([int(x['args'].split(',')[1].split('(')[0]) for _,x in events]==list(range(0,136,8)),'Exact17 actual output accesses')
        fpa=[pc for pc,x in body.items() if x['op']=='sw' and x['args']=='a4,-4(a3)']
        fpb=[pc for pc,x in body.items() if x['op']=='sw' and x['args']=='a5,0(a0)']
        require(len(fpa)==len(fpb)==1,'Unique FP bank store sites')
        aloop=fpa[0]-22;loopend=fpb[0]+10
        expected_ops=['andi','andi','slli','slli','add','add','lw','lw','addi','sw','sw','addiw','addiw','addi','bne']
        loop=[(pc,x) for pc,x in body.items() if aloop<=pc<=loopend]
        require([x['op'] for _,x in loop]==expected_ops,'Actual FP loop15 instructions')
        require(f'{aloop:x}' in loop[-1][1]['args'],'FP backedge actual target')
        before=[x for pc,x in body.items() if aloop-36<=pc<aloop]
        require(any('<a+0x80>' in x['args'] for x in before) and any('<a>' in x['args'] for x in before) and
                any('<b>' in x['args'] for x in before) and any('<fp_inputs>' in x['args'] for x in before),'FP pointer range exactly32 words')
        # Gate is op>24 before output setup, not VL or start. The call iteration
        # backedge returns to this gate; no equal-input shortcut exists.
        gate=[(pc,x) for pc,x in body.items() if x['op']=='bltu' and x['args'].startswith('a4,a5,') and
              int(re.search(r',([0-9a-f]+)',x['args'])[1],16)==aloop-36]
        require(len(gate)==1,'Original op>24 FP gate')
        gatepc=gate[0][0]
        require(code[gatepc-2]['op']=='li' and code[gatepc-2]['args']=='a4,24','Gate actual op threshold24')
        require(sum(x['op']=='j' and f'{gatepc-4:x}' in x['args'] for x in body.values())==3,'All nonfinal start iterations re-enter FP gate')
        frame=code[symbols['arithmetic_main']]
        require(frame['op']=='addi' and frame['args']=='sp,sp,-320','Actual main frame320')
        frames=[-int(x['args'].split(',')[-1]) for x in code.values() if x['op']=='addi' and x['args'].startswith('sp,sp,-')]
        require(max(frames)==320 and sum(frames)<65536,'All explicit stack-frame reserve')
        require(proof['backends'][backend]['helper_instructions']==458 and not proof['backends'][backend]['extra_vector'],'Original36 routines / no extra vector')
        compiled[backend]=dict(elf_sha256=sha(root/'program.elf'),disassembly_sha256=sha(root/'program.dis'),
            fp_a_store=hex(fpa[0]),fp_b_store=hex(fpb[0]),fp_loop_start=hex(aloop),fp_loop_instructions=15,
            fp_gate=hex(gatepc),fp_calls=1890,fp_loop_iterations=60480,fp_word_stores=120960,
            output_store_pcs=[hex(pc) for pc,_ in writes],output_read_pcs=[hex(pc) for pc,_ in reads],
            output_read_count=101745,main_frame=320,sum_all_static_frame_allocations=sum(frames),
            stack_gap=symbols['__stack_top']-symbols['__bss_end'],fp_table_bytes_sha256=hashlib.sha256(raw).hexdigest(),
            original_helpers=458,extra_vector=0)
    code=assembly(SOFT/'spike/program.dis')
    def region(lo,hi):
        lo=int(lo,16);hi=int(hi,16)
        result=[];pc=lo
        while pc<hi:
            require(pc in code,'CFG region instruction boundary '+hex(pc))
            result.append(pc);pc+=4 if code[pc]['insn']&3==3 else 2
        require(pc==hi,'CFG region endpoint')
        return result
    terms=[]
    def add(name,pcs,iterations,reason):
        terms.append(dict(name=name,instructions_per_visit=len(pcs),visits=iterations,
            instructions=len(pcs)*iterations,pcs=[hex(p) for p in pcs],reason=reason))
    # Disjoint mandatory blocks on a completely correct execution. Conditional
    # branches count as one regardless of taken status; no fallback is omitted
    # from the program, but any mismatch invalidates this positive-path budget.
    add('mask_clear',region('800004d0','800004da'),128*2205,'3 instructions, all128 bytes at every original mask group')
    mask_body=region('800004e4','80000502')
    add('mask_mode0',region('800004e0','80000502'),32*735,'All32 selected')
    even=region('800004e0','800004e4')+region('80000688','8000068c')+region('800006a6','800006b4')
    odd=region('800006a6','800006ae')+mask_body
    add('mask_mode1_even',even,16*735,'Even skip including dispatch; i30 advances to odd header')
    add('mask_mode1_odd',odd,16*735,'Odd selected then returns to dispatch or finishes')
    add('mask_mode2_dispatch',[0x800004e0,0x80000688],6*735,'Entry and after selected indices2,9,16,23,30')
    add('mask_mode2_predicate',region('8000068c','8000069c'),32*735,'Multiply-based original i%7 predicate')
    add('mask_mode2_selected',mask_body,5*735,'Five selected positions')
    add('mask_mode2_skip',region('8000069c','800006a2'),27*735,'Skip increments/last check')
    add('mask_mode2_skip_loop',[0x800006a2],26*735,'Last skip i31 exits before this branch')
    add('fp_setup',region('80000aba','80000ade')+[0x80000b04],1890,'Original per-call setup and loop exit jump')
    add('fp_loop',region('80000ade','80000b04'),32*1890,'All32 input pairs per FP call, including VL0/start>=VL')
    add('call_gate_setup_compare0',region('8000050c','800005a6'),5985,'Op gate, full17SD init, actual call, vs check, first LD compare')
    add('remaining16_compares_counters',region('80000848','8000090c'),5985,'All other packed compares, counters and end-trial branch')
    add('original_helper',list(range(13)),5985,'13 instructions per op helper, PC differs by op; all are preserved')
    mandatory=sum(x['instructions'] for x in terms)
    # Remaining loop/control blocks bounded from their actual compiled ranges.
    overhead=[]
    def upper(name,pcs,visits):
        overhead.append(dict(name=name,unique_instructions=len(set(pcs)),visits_upper=visits,
            instructions_upper=len(set(pcs))*visits,pcs=[hex(p) for p in sorted(set(pcs))]))
    upper('trial_start_selection',region('80000b6c','80000b8c'),5985)
    upper('mask_group_setup_end',region('800004c8','800004d0')+region('800004da','800004e0')+
        region('80000502','8000050c')+region('8000090c','80000916'),2205)
    upper('VL_setup_end',region('80000470','800004c8')+region('80000916','8000091e'),735)
    upper('op_setup_end',region('80000434','80000470')+region('8000091e','8000092a'),105)
    upper('seed_setup_end',region('800003ba','800003ea')+region('80000424','80000434')+region('8000092a','80000936'),3)
    upper('seed_RNG_all_case_union',region('800003ea','80000424')+region('80000668','80000688'),96)
    upper('main_prologue',region('80000352','800003ba'),1)
    symbols=read(SOFT/'spike/symbols.json')
    bss=symbols['__bss_end']-symbols['__bss_start']
    bss_instructions=4*((bss+7)//8)+1
    # Successful final message is <256 bytes, <=6 numbers (each<=20 digits).
    # Final source-to-console loops are <=4 scans/byte and replay_write<=10/byte;
    # number conversion <=15/digit. 20000 also covers fixed tails/startup/HTIF.
    success_tail_allowance=20000
    upper_count=mandatory+sum(x['instructions_upper'] for x in overhead)+bss_instructions+success_tail_allowance
    require(mandatory>3000000,'Current literal-mask candidate must HOLD before reference')
    result=dict(status='HOST_COMPILED_STATIC_COST_HOLD_NO_REFERENCE_NO_DUT',host_exit=execution,
        host_runs=26,full_history_positive_and_negative_runs=24,missing_equal_FP_write_runs=2,source_negatives=3,
        compiled=compiled,positive_path_mandatory_core=mandatory,positive_path_upper=upper_count,
        cost_is_static_not_retired_measurement=True,terms=terms,overhead_upper=overhead,
        bss_clear_instructions=bss_instructions,success_tail_allowance=success_tail_allowance,
        failure_path_budget_not_claimed=True,reference_limit=3000000,reference_authorized=False,DUT_authorized=False,
        original_source_only_not_Linux_replay=True,fflags_oracle=False,pins_count=len(pins),pins_unchanged=True)
    for p,h in pins.items():require(sha(p)==h,'Post-inspection input changed '+p)
    save(HERE/'RESULT.json',result)
    print(json.dumps({k:result[k] for k in ('status','positive_path_mandatory_core','positive_path_upper','pins_count')}),flush=True)
if __name__=='__main__':main()
