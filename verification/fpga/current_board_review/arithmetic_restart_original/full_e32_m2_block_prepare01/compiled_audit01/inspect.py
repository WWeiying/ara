#!/usr/bin/env python3
"""Read-only linked-code proof and weighted positive CFG, not ISA execution."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
SOFT=HERE.parent/'software01'
A=HERE.parents[1]
spec=importlib.util.spec_from_file_location('sealed_disassembly_reader',A/'full_e32_m1_packed_prepare01/compiled_audit01/inspect03.py')
reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
read,save,sha,require,assembly=reader.read,reader.save,reader.sha,reader.require,reader.assembly

def region(code,lo,hi):
    pc=lo;result=[]
    while pc<hi:
        require(pc in code,'Actual CFG instruction '+hex(pc));result.append(pc)
        pc+=4 if code[pc]['insn']&3==3 else 2
    require(pc==hi,'Actual CFG endpoint '+hex(hi));return result

def target(item):return int(item['args'].split(',')[-1].split()[0],16)
def signed(value,bits):return value-(1<<bits) if value&(1<<(bits-1)) else value
def imm_s(word):return signed(((word>>25)<<5)|((word>>7)&31),12)

def mask_path(code,start,end,mode,symbols):
    # Only this finite scalar mask subgraph. Both conditional operands are
    # the source's mode and literal1; never infer arbitrary branch outcomes.
    pcs=[];pc=start
    while pc!=end:
        require(pc not in pcs and len(pcs)<400,'Mask path acyclic/bounded')
        pcs.append(pc);item=code[pc];op,args=item['op'],item['args']
        nxt=pc+(4 if item['insn']&3==3 else 2)
        if op=='j':nxt=target(item)
        elif op=='bnez':
            require(args.startswith('s8,'),'Only mode!=0 gate');nxt=target(item) if mode else nxt
        elif op=='beq':
            require(args.startswith('s8,a4,'),'Only mode==1 gate');nxt=target(item) if mode==1 else nxt
        else:require(op in ('auipc','sd','li','lbu','ori','sb'),'Mask path no loop/fence/memset/vector '+op)
        pc=nxt
    regs={3:symbols['__global_pointer$'],27:symbols['mask']};clears=[];events=[];lastload=None;lastbit=None
    for pc in pcs:
        item=code[pc];word=item['insn'];op=item['op']
        if op=='auipc':regs[(word>>7)&31]=(pc+signed(word&0xfffff000,32))&((1<<64)-1)
        elif op=='sd':
            require(word&127==0x23 and (word>>12)&7==3 and (word>>20)&31==0,'Actual SD zero')
            rs1=(word>>15)&31;require(rs1 in regs,'Known clear base')
            clears.append(dict(pc=hex(pc),address=regs[rs1]+imm_s(word)))
        elif op=='lbu':
            require(word&127==3 and (word>>12)&7==4 and (word>>7)&31==15,'Actual LBU a5')
            rs1=(word>>15)&31;require(rs1 in regs,'Known LBU base')
            lastload=(pc,regs[rs1]+signed(word>>20,12));lastbit=None
        elif op=='ori':
            require(word&127==19 and (word>>12)&7==6 and (word>>7)&31==15 and (word>>15)&31==15,'Actual ORI a5,a5')
            lastbit=signed(word>>20,12)&255
        elif op=='sb':
            require(word&127==0x23 and (word>>12)&7==0 and (word>>20)&31==15 and (word>>15)&31==27,'Actual SB a5,offset(s11)')
            address=regs[27]+imm_s(word)
            require(len(clears)==16 and lastload is not None and lastload[1]==address,'All clears precede same-byte read/modify/write')
            require(lastbit in (1,2,4,8,16,32,64,128),'Exactly one selected bit')
            index=(address-symbols['mask'])*8+(lastbit.bit_length()-1)
            events.append(dict(pc=hex(pc),load_pc=hex(lastload[0]),index=index,address=address,bit=lastbit))
            lastload=None;lastbit=None
    require([x['address'] for x in clears]==list(range(symbols['mask'],symbols['mask']+128,8)),'16 exact ordered clear addresses')
    expected=list(range(64)) if mode==0 else list(range(1,64,2)) if mode==1 else list(range(2,64,7))
    require([x['index'] for x in events]==expected,'Actual complete ordered selected writes')
    return dict(pcs=[hex(x) for x in pcs],instructions=len(pcs),clear=clears,bitsets=events)

def main():
    pins=read(SOFT/'pins.json')
    for p,h in pins.items():require(sha(p)==h,'Input pin drift '+p)
    receipt=read(SOFT/'execution_receipt.json');proof=read(SOFT/'proof.json');rows=read(SOFT/'sequence.json')
    require(type(receipt['returncode']) is int and receipt['returncode']==0 and not receipt['timed_out'],'Actual Hostcompile exit0')
    require(len(proof['host'])==30,'All30 Host runs')
    for row in proof['host']:
        require(type(row['returncode']) is int and row['returncode']==row['expected_returncode'] and not row['timed_out'],'Actual Host outcome')
        require(sha(row['log'])==row['sha256'],'Actual Host log hash')
    require(len(rows)==5985 and sum(r['op']>=25 for r in rows)==1890,'Actual source sequence scope')
    groups=[r for r in rows if r['si']==0]
    require(len(groups)==2205 and [sum(r['mode']==m for r in groups) for m in range(3)]==[735]*3,'Actual735 groups each mode')
    pool=[];lookup={};ids=[]
    for row in rows:
        raw=b''.join(struct.pack('<Q',x) for x in row['words']);require(len(raw)==264,'33 words each row')
        one=[]
        for off in range(0,264,64):
            block=raw[off:off+64].ljust(64,b'\0')
            if block not in lookup:lookup[block]=len(pool);pool.append(block)
            one.append(lookup[block])
        ids.append(one)
        require(b''.join(pool[x] for x in one)[:264]==raw and pool[one[-1]][8:]==bytes(56),'Full exact264/padding-only ROM')
        require((row['words'][0]&0xffffffff)==91 and row['words'][-1]>>32==91 and
                (row['words'][-1]&0xffffffff)==row['expected'][63],'Front/last element63/rear word meaning')
    poolraw=b''.join(pool);idraw=b''.join(struct.pack('<H',x) for one in ids for x in one)
    header=(SOFT/'original/operations.h').read_text()
    fpraw=b''.join(struct.pack('<I',int(x,16)) for x in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)',header.split('fp_expected[10][64] = {')[1].split('};')[0]))
    require(len(fpraw)==2560 and len(pool)==1499 and len(poolraw)+len(idraw)==155786,'Exact gold table/ROM scope')
    original=Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04/overlay/opt/ara-tests/rvv_matrix_e32_m2')
    require(original.read_bytes().count(fpraw)==1,'Original ELF exact640 FP patterns')
    compiled={}
    for backend in ('soc','spike'):
        root=SOFT/backend;code=assembly(root/'program.dis');symbols=read(root/'symbols.json');raw=(root/'program.elf').read_bytes()
        require(sha(root/'program.elf')==proof['backends'][backend]['sha256'],'ELF bound')
        require(raw.count(fpraw)==raw.count(poolraw)==raw.count(idraw)==1,'Unique exact source/table/IDs in linked ELF')
        body={p:x for p,x in code.items() if symbols['arithmetic_main']<=p<symbols['capacity']}
        init=[p for p,x in body.items() if x['op']=='sd' and re.fullmatch(r's6,\d+\(s0\)',x['args'])]
        outputloads=[p for p,x in body.items() if x['op']=='ld' and re.fullmatch(r'a[1-5],\d+\(s0\)',x['args'])]
        for pcs in (init,outputloads):
            require([int(code[p]['args'].split(',')[1].split('(')[0]) for p in pcs]==list(range(0,264,8)),'Actual33 output transfers no rounding')
        require(any('<out>' in x['args'] and x['args'].startswith('s0,s0,') for x in body.values()),'Actual output base')
        require(any(x['op']=='add' and x['args']=='s6,a0,a1' for x in body.values()) and
                any(x['op']=='slli' and x['args']=='a0,a1,0x20' for x in body.values()) and
                any(x['op']=='li' and x['args']=='a1,91' for x in body.values()),'Actual uint32 guard fill both halves')
        fpstores=[p for p,x in body.items() if x['op']=='sw' and re.fullmatch(r'a5,\d+\(s[34]\)',x['args'])]
        require(len(fpstores)==128,'Actual128 FP SW')
        fppcs=region(code,fpstores[0]-2,fpstores[-1]+8)
        require(len(fppcs)==257 and code[fppcs[-1]]['op']=='j' and target(code[fppcs[-1]])==init[0],'256 LW/SW plus output init jump')
        fpevents=[]
        for n,pc in enumerate(fpstores):
            index,bank=divmod(n,2);reg='s3' if bank else 's4';qindex=(3*index if bank else index)%8
            require(code[pc]['args']==f'a5,{4*index}({reg})' and code[pc]['insn']&127==0x23 and (code[pc]['insn']>>12)&7==2,'Actual interleaved SW address/width')
            prev=fpstores[0]-2 if n==0 else fpstores[n-1]+4
            require(code[prev]['op']=='lw' and code[prev]['args']==f'a5,{192+4*qindex}(sp)' and prev+2==pc,'Actual seed-cache permutation and load before each SW')
            fpevents.append(dict(pc=hex(pc),bank='b' if bank else 'a',index=index,seed_slot=qindex))
        require(any('<a>' in x['args'] and x['args'].startswith('s4,s4,') for x in body.values()) and
                any('<b>' in x['args'] and x['args'].startswith('s3,s3,') for x in body.values()),'Actual FP bank bases')
        gate=[p for p,x in body.items() if x['op']=='bltu' and x['args'].startswith('a5,a4,') and target(x)==fppcs[0]]
        require(len(gate)==1 and code[gate[0]-2]['args']=='a5,24' and code[gate[0]-4]['args']=='a4,72(sp)','Only op>24 FP gate')
        reentries=[p for p,x in body.items() if x['op']=='j' and target(x)==gate[0]-4]
        require(len(reentries)==3,'All next-si paths re-enter FP gate independent VL/equality')
        clear=[p for p,x in body.items() if x['op']=='sd' and x['args'].startswith('zero,') and '<mask' in x['args']]
        require(len(clear)==16,'Actual16 SD clear sites')
        start=clear[0]-4;end=init[0]
        # First mask0 path falls through directly to the trial setup block.
        group_setup=next(p for p in sorted(body) if p>clear[-1] and body[p]['op']=='ld' and body[p]['args']=='a5,136(sp)')
        paths={str(mode):mask_path(code,start,group_setup,mode,symbols) for mode in range(3)}
        require(sum(len(p['bitsets'])*735 for p in paths.values())==77175,'Actual ordered SB total77175')
        require(any('<mask>' in x['args'] and x['args'].startswith('s11,s11,') for x in body.values()),'Actual mask SB base')
        frames=[-int(x['args'].split(',')[-1].split()[0]) for x in code.values() if x['op']=='addi' and x['args'].startswith('sp,sp,-')]
        gap=symbols['__stack_top']-symbols['__bss_end']
        require(code[symbols['arithmetic_main']]['args']=='sp,sp,-336' and gap>=65536 and sum(frames)<65536,'Actual frame/stack reserve')
        require(proof['backends'][backend]['helper_instructions']==458 and not proof['backends'][backend]['extra_vector'],'458 original/no extra RVV')
        compiled[backend]=dict(elf_sha256=sha(root/'program.elf'),mask_paths=paths,FP_events=fpevents,
            FP_gate=hex(gate[0]),FP_reentry_pcs=list(map(hex,reentries)),FP_instructions_per_call=257,FP_SW_total=128*1890,
            output_store_pcs=list(map(hex,init)),output_read_pcs=list(map(hex,outputloads)),output_words=33,
            full_output_reads=33*5985,mask_SD_total=16*2205,mask_SB_total=77175,main_frame=336,
            static_frame_allocation_sum=sum(frames),stack_gap=gap,helper_instructions=458,extra_RVV=0,
            dictionary_ROM_bytes=len(poolraw)+len(idraw),blocks=len(pool),exact_source_FP_bytes=2560)
    code=assembly(SOFT/'spike/program.dis')
    def R(lo,hi):return region(code,int(lo,16),int(hi,16))
    terms=[]
    def add(name,pcs,visits,upper=False):
        terms.append(dict(name=name,pcs=list(map(hex,pcs)),instructions_per_visit=len(pcs),visits=visits,
            instructions=len(pcs)*visits,upper=upper))
    for mode,path in compiled['spike']['mask_paths'].items():
        add('mask_mode'+mode,[int(p,16) for p in path['pcs']],735)
    add('FP_all128_ordered_SW_and_exit',R('80000e92','80001196'),1890)
    add('gate_output33SD_call_vs_firstcompare',R('8000095a','80000a46'),5985)
    add('remaining32LD_gold_checks_and_counters',R('80000cac','80000e42'),5985)
    add('original_helper13',list(range(13)),5985)
    core=sum(t['instructions'] for t in terms)
    add('trial_start_selection_union',R('800011fc','80001218')+R('800012b2','800012be'),5985,True)
    add('mask_group_setup_end_union',R('80000946','8000095a')+R('80000e42','80000e4a'),2205,True)
    add('VL_setup_end_union',R('800004b2','800004e6')+R('80000e4a','80000e54'),735,True)
    add('op_setup_end_union',R('80000484','800004b2')+R('80000e54','80000e6a'),105,True)
    add('seed_setup_end_union',R('800003cc','80000402')+R('80000446','8000044a')+R('8000046a','80000484')+R('8000164c','8000165c'),3,True)
    add('RNG_case_union',R('80000402','80000446')+R('800015c4','800015d4')+R('800015ea','80001606'),64*3,True)
    add('seed8_pattern',R('8000044a','8000046a'),8*3)
    add('main_prologue_union',R('80000352','800003cc'),1,True)
    symbols=read(SOFT/'spike/symbols.json')
    bss=4*((symbols['__bss_end']-symbols['__bss_start']+7)//8)+1
    # Same bounded successful text/number/exit tail as the accepted m1 audit:
    # <256 chars, <=6 decimal numbers, <=20 digits each; no failure printing.
    tail=20000;total=sum(t['instructions'] for t in terms)+bss+tail
    require(total<=3000000,'Static positive upper exceeds3M: HOLD')
    for p,h in pins.items():require(sha(p)==h,'Post-inspection input drift '+p)
    evidence={str(p):sha(p) for p in [HERE/'inspect.py',SOFT/'execution_receipt.json',SOFT/'software_status.json',SOFT/'pins.json',SOFT/'proof.json',
        SOFT/'SOURCE_FREEZE.json',Path(reader.__file__)]}
    save(HERE/'RESULT.json',dict(status='HOST_COMPILED_ACTUAL_LOWERING_STATIC_COST_PASS_NO_REFERENCE_NO_DUT',
        actual_execution=receipt,Host_runs=30,Host_complete_history_runs=24,fresh_order_negative_runs=6,
        compiled=compiled,mandatory_core=core,positive_path_upper=total,terms=terms,bss_instructions=bss,success_tail_allowance=tail,
        cost_is_static_not_retired=True,failure_fallback_budget_not_claimed=True,scope=proof['scope'],
        pins_count=len(pins),pins_unchanged=True,evidence=evidence,reference=False,DUT=False,fflags_oracle=False))
    print(json.dumps(dict(mandatory_core=core,positive_path_upper=total,pins=len(pins),actual_Hostcompile_rc=0)),flush=True)

if __name__=='__main__':main()
