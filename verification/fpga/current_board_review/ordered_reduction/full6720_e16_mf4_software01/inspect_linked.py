#!/usr/bin/env python3
"""Finite source-derived successful CFG ledger for the single compiled pair."""
from collections import Counter
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
G=HERE.parents[1]
RUN=HERE/'execution01'
NAME='fp_redspecial_e16_mf4_full6720_main'
# Offsets refer to the pinned Spike linked image. SoC is independently byte
# checked; its entire source function is relocated by -14 bytes.
BLOCKS=[
 ('entry',0xe0,0x11a,1),('return',0x12c,0x148,1),('fixed_setup',0x14e,0x18c,1),
 ('scenario_setup',0x18e,0x1e6,8),('input_dispatch',0x1e8,0x1e8,128),
 ('jump_table',0x1ec,0x1f2,112),('scenario0_index',0x1f4,0x1f4,16),
 ('input_bits_fetch',0x1f8,0x1fe,80),('scenario2_select',0x200,0x206,16),
 ('scenario2_odd',0x208,0x20a,8),('scenario3_select',0x20c,0x212,16),
 ('scenario4_select',0x214,0x234,16),('scenario4_other',0x238,0x23e,13),
 ('scenario4_xor',0x242,0x242,16),('input_store_increment',0x246,0x24e,128),
 ('seed_and_scenario_setup',0x252,0x2c0,8),('length_setup',0x2c2,0x2d8,56),
 ('scenario5_select',0x2da,0x302,16),('scenario6_select',0x304,0x30a,16),
 ('scenario6_odd',0x30e,0x310,8),('scenario7_select',0x312,0x318,16),
 ('scenario7_odd',0x31c,0x31e,8),('scenario1_value',0x320,0x322,16),
 ('fixture_fields',0x324,0x34c,3360),('mask_mode_0_1_2',0x350,0x35a,2520),
 ('mask_setup_and_sticky0',0x35e,0x3ac,3360),('output_setup_helper_return',0x3ae,0x42a,6720),
 ('flags_check',0x42c,0x432,6720),('flags_seen_VL_choice',0x438,0x43e,6720),
 ('nonzero_VL_expected',0x442,0x442,5760),('all18_words_compare',0x444,0x4ae,6720),
 ('no_error_branch',0x4f2,0x4f2,6720),('sticky_increment',0x594,0x59c,6720),
 ('op_increment',0x5a0,0x5a4,3360),('rm_increment',0x5a8,0x5b4,1120),
 ('rm_setup',0x5b8,0x5c2,1120),('sticky1',0x5c4,0x5c6,3360),
 ('mode_increment',0x5c8,0x5cc,224),('mode_setup',0x5d0,0x5de,224),
 ('length_increment',0x5e0,0x5e4,56),('scenario_increment',0x5e8,0x5ee,8),
 ('success_summary_select',0x5f2,0x5fa,1),('summary_calls',0x606,0x662,1)]
ZERO=[('capacity_failure',0x11e,0x12a),('VLEN512',0x14a,0x14c),
      ('status_error',0x436,0x436),('byte_fallback',0x4b0,0x4ee),
      ('detail_printing',0x4f6,0x592),('failure_summary',0x5fe,0x602)]
TAKEN={0x10c:0,0x114:0,0x11a:1,0x1e8:16,0x206:8,0x234:3,
       0x24e:120,0x30a:8,0x318:8,0x34c:840,0x42a:0,0x432:6720,
       0x43e:960,0x4ae:6720,0x4f2:6720,0x59c:3360,0x5a4:2240,
       0x5b4:224,0x5cc:56,0x5e4:48,0x5ee:7,0x5fa:1}

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def main():
    p=load('owned_prepare',HERE/'prepare.py')
    parser_path=G/'fp_compare_unboxed_full17920_prepare01/compile01/inspect_linked.py'
    parser=load('sealed_disassembly_reader',parser_path);parser.RUN=RUN
    elfreader_path=G/'fp_compare_unboxed_full17920_prepare01/prepare_source.py'
    elfreader=load('sealed_elf_reader',elfreader_path)
    require,save,sha=p.require,p.save,p.sha
    out=HERE/'linked01';out.mkdir()
    pins=json.loads((RUN/'inputs_after.json').read_text())
    pins.update({str(f):sha(f) for f in RUN.rglob('*') if f.is_file()})
    pins.update({str(f):sha(f) for f in [Path(__file__),parser_path,elfreader_path,HERE/'receipt01/supervisor.exit.json',G/'ordered_reduction/original_e16_mf4_prepare01/sourceproof.json']})
    require(all(sha(f)==h for f,h in pins.items()),'Input drift')
    save(out/'inputs_before.json',pins)
    try:
        old=json.loads((G/'ordered_reduction/original_e16_mf4_prepare01/sourceproof.json').read_text())
        original=(p.ARCHIVE/'original.elf').read_bytes()
        source_fixtures=(p.ARCHIVE/'fixtures.h').read_text()
        fixture_values=[(int(a,16),int(b)) for a,b in re.findall(r'\{UINT64_C\(0x([0-9a-fA-F]+)\),\s*(\d+)\}',source_fixtures)]
        require(len(fixture_values)==6720 and fixture_values[4905]==(0x7e00,16),'Original fixture bank')
        summary={}
        for backend in ('soc','spike'):
            folder,code,funcs,symbols,sizes=parser.parse(backend)
            elf=(folder/'program.elf').read_bytes()
            require(sha(folder/'program.elf')==json.loads((RUN/'RESULT.json').read_text())['binaries'][backend]['sha256'],'Single compiled identity')
            for pc,row in code.items():
                raw=bytes.fromhex(row['insn'])[::-1]
                require(elfreader.elf_bytes(elf,pc,len(raw))==raw,'Actual disassembly bytes')
            helpers={}; hp=set()
            for name in ('capacity','op_0','op_1','op_2'):
                rows=funcs[name]; raw=b''.join(bytes.fromhex(r['insn'])[::-1] for r in rows)
                require(original.count(raw)==1,'Unique original helper bytes '+name)
                if name=='capacity': require([r['insn'] for r in rows]==['52fd','00e2f557','8082'],'Original fractional capacity')
                else: require([r['insn'] for r in rows]==[r[1] for r in old['helper_windows']['soc'][name]['original']],'Original21-instruction window')
                hp.update(r['pc'] for r in rows)
                helpers[name]=dict(pc=hex(rows[0]['pc']),instructions=len(rows),bytes=len(raw),codes=[r['insn'] for r in rows])
            require(len(hp)==66,'Capacity3 plus three21 helpers')
            extra=[r for pc,r in code.items() if pc not in hp and (r['op'].startswith('v') or (len(r['insn'])==8 and int(r['insn'],16)&127==0x53))]
            require(not extra,'No extra vector/FP instructions')
            addr=lambda off:0x80000000+off-(14 if backend=='soc' else 0)
            body=funcs[NAME]; bodypcs={r['pc'] for r in body}; counts=Counter(); blocks=[];zero={}
            for name,lo,hi,n in BLOCKS:
                require(addr(lo) in bodypcs and addr(hi) in bodypcs,'Actual block endpoints '+name)
                pcs=[r['pc'] for r in body if addr(lo)<=r['pc']<=addr(hi)]
                for pc in pcs: require(pc not in counts,'Disjoint blocks');counts[pc]=n
                blocks.append(dict(name=name,first=hex(addr(lo)),last=hex(addr(hi)),instructions=len(pcs),multiplicity=n,total=len(pcs)*n))
            for name,lo,hi in ZERO:
                for r in body:
                    if addr(lo)<=r['pc']<=addr(hi):zero[r['pc']]=name
            require(set(counts)|set(zero)==bodypcs and not set(counts)&set(zero),'All source PCs classified')
            # Original reduction_input's seven-way source switch: actual relative
            # jump table proves the mapping; all source cases execute16 times.
            upper=code[addr(0x1aa)];lower=code[addr(0x1ae)]
            require(upper['op']=='auipc' and lower['op']=='addi','Actual switch address materialization')
            table=upper['pc']+(int(upper['args'].split(',')[1],0)<<12)+int(lower['args'].split(',')[-1])
            offsets=struct.unpack('<7i',elfreader.elf_bytes(elf,table,28))
            targets=[addr(x) for x in (0x1f4,0x320,0x200,0x20c,0x214,0x2da,0x304)]
            require([table+x for x in offsets]==targets,'Every original scenario switch edge')
            incoming=Counter({body[0]['pc']:1});edges=[];taken={addr(k):v for k,v in TAKEN.items()}
            for r in body:
                pc=r['pc'];n=counts.get(pc,0)
                if not n:continue
                nxt=pc+len(r['insn'])//2
                if r['op']=='ret':require(n==1,'One source return');continue
                if r['op']=='jr':
                    require(pc==addr(0x1f2) and r['args']=='a5','Only classified input switch')
                    destinations=[(t,16) for t in targets]
                elif r['op']=='j':destinations=[(int(r['args'].split()[0],16),n)]
                elif r['op'] in ('beq','bne','bltu','bgeu','blt','bge','beqz','bnez','bltz','bgez'):
                    require(pc in taken,'Classified conditional edge')
                    destinations=[(int(r['args'].split(',')[-1].split()[0],16),taken[pc]),(nxt,n-taken[pc])]
                else: destinations=[(nxt,n)]
                for dst,weight in destinations:
                    require(weight>=0 and (not weight or dst in bodypcs),'No positive edge escape')
                    incoming[dst]+=weight
                    if weight:edges.append(dict(source=hex(pc),destination=hex(dst),weight=weight))
            require(all(incoming[pc]==counts.get(pc,0) for pc in bodypcs),'Full per-instruction CFG flow conservation')
            def rows(lo,hi):return [r for r in body if addr(lo)<=r['pc']<=addr(hi)]
            for lo,hi,op,base,num,n in [(0x288,0x2a6,'sd','a4',16,8),(0x374,0x382,'sd','a4',8,3360),(0x3ba,0x3dc,'sd','s0',18,6720)]:
                actual=rows(lo,hi)
                require(len(actual)==num and all(r['op']==op and r['args'].endswith(','+str(i*8)+'('+base+')') and counts[r['pc']]==n for i,r in enumerate(actual)),'Actual fresh full extent')
            loads=[r for r in rows(0x444,0x4ae) if r['op']=='ld']
            require(len(loads)==18 and all(r['args'].endswith(','+str(i*8)+'(s0)') and counts[r['pc']]==6720 for i,r in enumerate(loads)),'All144B actual reads')
            require(code[addr(0x246)]['text']=='sh a5,0(t3)' and counts[addr(0x246)]==128,'16 input SH per scenario only')
            require(code[addr(0x33e)]['text']=='ld a4,0(a5)' and code[addr(0x340)]['text']=='lw a5,8(a5)','Actual fixture fields')
            # Scalar caller values t4/t5/t6 are caller-saved; every live value
            # needed after helper is reloaded from its actual stack slot.
            abi={0x3ae:'sd t0,152(sp)',0x3b0:'sd a7,48(sp)',0x412:'sd t6,144(sp)',0x414:'sd a7,136(sp)',
                 0x424:'ld a7,136(sp)',0x426:'ld t6,144(sp)',0x428:'ld t0,152(sp)'}
            for off,expected in abi.items(): require(code[addr(off)]['text']==expected,'Actual live-register ABI')
            for name in helpers:
                require(all(not re.search(r'\bs(?:[0-9]|1[01])\b',r['args']) for r in funcs[name]),'Helper callee-saved contract')
            require(body[0]['text']=='addi sp,sp,-368','Actual source stack')
            require(funcs['main'][0]['text']=='addi sp,sp,-16' and funcs['num'][0]['text']=='addi sp,sp,-48','Actual nested frames')
            for name,size in [('input',1024),('seed',128),('mask',64),('output',144),('fixtures',107520)]:
                require(sizes[name]==size,'Full original object '+name)
            require(all(symbols[n]%8==0 for n in ('seed','mask','output')),'Packed addresses aligned')
            require(symbols['__stack_top']==0x800ffff0 and symbols['__bss_end']<symbols['__stack_top']-65536,'1MiB and64KiB stack')
            fixturebytes=elfreader.elf_bytes(elf,symbols['fixtures'],107520)
            require(all(struct.unpack_from('<QI',fixturebytes,i*16)==v for i,v in enumerate(fixture_values)),'Both full original banks linked unchanged')
            require(list(struct.unpack('<3Q',elfreader.elf_bytes(elf,symbols['functions'],24)))==[symbols['op_'+str(i)] for i in range(3)],'Original op0/1/2 table order')
            memcpy=funcs['memcpy']
            require([r['op'] for r in memcpy]==['li','bne','ret','add','lbu','add','addi','sb','j'],'Actual memcpy loop')
            memcpy_count=8*(7*32+3)
            require(len([r for r in body if r['op']=='jal' and '<memcpy>' in r['args']])==1,'Only one seed-index memcpy site')
            bssbytes=symbols['__bss_end']-symbols['__bss_start']
            require(symbols['__bss_start']%8==0 and bssbytes%8==0,'Whole aligned BSS extent')
            boot=0x8000003e if backend=='soc' else 0x80000042
            require([code[boot+x]['op'] for x in (0,4,8,10)]==['bgeu','sd','addi','j'] and code[boot+4]['args']=='zero,0(t0)' and code[boot+8]['args']=='t0,t0,8','Actual four-instruction BSS loop')
            bss=bssbytes//8
            startup=4*bss+100
            printing=256*64+20*128
            require(len(funcs['text'])<=16 and len(funcs['num'])<=32 and len(funcs['main'])<=40 and len(funcs['replay_text'])<=32 and len(funcs['replay_write'])<=48,'Runtime bounds inspected')
            core=sum(counts.values());total=core+6720*21+3+memcpy_count+startup+printing
            result=dict(status='COMPILED_CONDITIONAL_LT_3M' if total<=3000000 else 'HOLD_COST',elf_sha256=sha(folder/'program.elf'),
                 source_calls=6720,oracle_bytes=967680,flags=6720,vstart=6720,helpers=helpers,helper_dynamic_instructions=141123,
                 input_SH=128,seed_SD=128,mask_SD=26880,output_SD=120960,output_LD=120960,fixture_field_reads=6720,
                 blocks=blocks,CFG_edges=edges,zero_success_PCs={hex(pc):label for pc,label in zero.items()},full_CFG_flow_conserved=True,
                 original_fixture_banks=True,extra_vector_FP=[],source_frame=368,normal_nested_stack=432,stack_reserve=65536,
                 whole_image_through_BSS=symbols['__bss_end']-0x80000000,source_CFG=core,seed_memcpy=memcpy_count,
                 BSS_words=bss,startup_upper=startup,printing_wrapper_upper=printing,whole_positive_upper=total,margin_to_3M=3000000-total,
                 limitation='Conditional all-correct finite CFG; not executed firmware, runtime, reference, DUT or Linux acceptance')
            save(out/(backend+'.json'),result)
            summary[backend]={k:result[k] for k in ('status','elf_sha256','whole_positive_upper','margin_to_3M')}
        require(all(sha(f)==h for f,h in pins.items()),'Audit input drift')
        save(out/'inputs_after.json',pins)
        save(out/'RESULT.json',dict(status='LINKED_AUDIT_COMPLETE',backends=summary,reference=False,DUT=False))
        print(json.dumps(summary),flush=True)
    except BaseException as error:
        save(out/'FIRST_FAILURE.json',dict(type=type(error).__name__,message=str(error)))
        raise

if __name__=='__main__': main()
