"""Actual linked full successful CFG, flow conservation; no ISA execution."""
from collections import Counter
import importlib.util
import json
from pathlib import Path
import re
from prepare import HERE, OLD, NAME, sha, save, old

sp=importlib.util.spec_from_file_location('immutable_linked_parser',OLD/'compile01/inspect_linked.py')
parser=importlib.util.module_from_spec(sp);sp.loader.exec_module(parser)
parser.RUN=HERE/'build01'
BLOCKS=[
 ('entry',0xde,0x104,1),('return',0x116,0x132,1),('fixed_setup',0x134,0x168,1),
 ('seed_setup',0x16a,0x174,32),('nonzero_mask',0x176,0x176,13440),
 ('full_fresh_helper',0x17a,0x234,17920),('result_and_status',0x236,0x270,17920),
 ('flags_and_guards',0x274,0x2aa,17920),('sticky_increment',0x36e,0x376,17920),
 ('sticky0_followthrough',0x37a,0x37a,8960),('VL_mode_selection',0x37c,0x384,17920),
 ('zero_mask_jump',0x388,0x388,4480),('mode_increment',0x394,0x398,8960),
 ('mode_record_and_input_addresses',0x39c,0x3e4,8960),
 ('length_increment',0x3e6,0x3ec,2240),('mode0_reset',0x3f0,0x3f2,2240),
 ('op_increment',0x3f4,0x3fa,320),('op_setup',0x3fe,0x414,320),
 ('seed_increment',0x416,0x41c,32),('success_selection',0x420,0x428,1),
 ('summary_return',0x432,0x478,1)]
ZERO=[('capacity_failure',0x108,0x114),('error_details',0x2ae,0x36c),
      ('error_popcount',0x38a,0x392),('failure_summary',0x42a,0x42e)]


def main():
    out=HERE/'linked01';assert not out.exists();out.mkdir()
    pins={str(p):sha(p) for p in (HERE/'build01').rglob('*') if p.is_file()}
    pins.update({str(p):sha(p) for p in [Path(__file__),OLD/'compile01/inspect_linked.py',HERE/'helper_identity.json']})
    save(out/'inputs_before.json',pins)
    helpers=json.loads((HERE/'helper_identity.json').read_text())['helpers']
    reports={}
    for backend in ('soc','spike'):
        directory,code,functions,symbols,sizes=parser.parse(backend)
        blob=(directory/'program.elf').read_bytes()
        for pc,r in code.items():
            assert old.elf_bytes(blob,pc,len(r['insn'])//2)==int(r['insn'],16).to_bytes(len(r['insn'])//2,'little')
        helper_pcs=set()
        for helper in helpers:
            actual=functions[helper['name']]
            assert [r['insn'] for r in actual]==helper['codes'],helper['name']
            helper_pcs.update(r['pc'] for r in actual)
        extra=[r for pc,r in code.items() if (r['op'].startswith('v') or
            len(r['insn'])==8 and int(r['insn'],16)&127 in (0x53,0x43,0x47,0x4b,0x4f)) and pc not in helper_pcs]
        assert not extra,'Extra RVV/FP'
        body=functions[NAME+'_main'];pcs={r['pc'] for r in body}
        def addr(offset):
            return 0x80000000+offset-(0 if backend=='spike' else 8 if offset<=0x180 else 4)
        counts=Counter();ledger=[];zeros={}
        for name,lo,hi,n in BLOCKS:
            assert addr(lo) in pcs and addr(hi) in pcs,name
            selected=[r['pc'] for r in body if addr(lo)<=r['pc']<=addr(hi)]
            for pc in selected:
                assert pc not in counts
                counts[pc]=n
            ledger.append(dict(name=name,first=addr(lo),last=addr(hi),executions=n,
                instructions=len(selected),total=n*len(selected)))
        for name,lo,hi in ZERO:
            for r in body:
                if addr(lo)<=r['pc']<=addr(hi):zeros[r['pc']]=name
        assert pcs==set(counts)|set(zeros) and not set(counts)&set(zeros),'Full body partition'
        branches={0x104:('beq',1),0x270:('bnez',0),0x292:('bne',0),0x2aa:('beq',17920),
            0x376:('beq',8960),0x384:('bne',13440),0x398:('beq',2240),0x3ec:('beq',320),
            0x3fa:('beq',32),0x41c:('bne',31),0x428:('beqz',1)}
        incoming=Counter({body[0]['pc']:1});edges=[]
        for r in body:
            pc=r['pc'];n=counts[pc]
            if not n:continue
            if r['op']=='ret':assert n==1;continue
            nextpc=pc+len(r['insn'])//2
            if r['op']=='j':dests=[(int(r['args'].split()[0],16),n)]
            elif r['op'] in ('beq','bne','bnez','beqz','bltu','bgeu','blt','bge','bltz','bgez'):
                offset=pc-0x80000000+(0 if backend=='spike' else 8 if pc<=addr(0x180) else 4)
                op,taken=branches[offset];assert r['op']==op
                target=int(r['args'].split(',')[-1].split()[0],16)
                dests=[(target,taken),(nextpc,n-taken)]
            else:dests=[(nextpc,n)]
            for dest,weight in dests:
                assert weight>=0 and (not weight or dest in pcs)
                incoming[dest]+=weight
                if weight:edges.append(dict(pc=pc,target=dest,count=weight))
        assert all(incoming[pc]==counts.get(pc,0) for pc in pcs),'CFG flow conservation'
        stores=[r for r in body if addr(0x17a)<=r['pc']<=addr(0x234) and r['op'] in ('sd','sh') and '(sp)' not in r['args']]
        want=[('sd',f'a4,{i}(a5)') for i in range(0,128,8)]
        for i in range(0,32,8):want += [('sd',f'a2,{i}(a0)'),('sd',('a4' if i==24 else 'a2')+f',{i}(a1)')]
        want += [('sd',f's1,{i}(s0)') for i in range(0,128,8)]+[('sh','a4,128(s0)')]
        assert [(r['op'],r['args']) for r in stores]==want and all(counts[r['pc']]==17920 for r in stores)
        loads=[r for r in body if addr(0x1ba)<=r['pc']<=addr(0x1e6) and r['op']=='ld']
        assert [r['args'] for r in loads]==['a2,0(s2)','a2,0(a4)','a2,8(s2)','a2,8(a4)','a2,16(s2)','a2,16(a4)','a2,24(s2)','a4,24(a4)']
        assert all(counts[r['pc']]==17920 for r in loads)
        assert code[addr(0x244)]['text']=='lwu s0,0(s0)' and counts[addr(0x244)]==17920
        assert code[addr(0x3c0)]['text']=='ld s6,0(a5)' and counts[addr(0x3c0)]==8960
        for helper in helpers:
            assert not any(re.search(r'\bs(?:[0-9]|1[01])\b',r['args']) for r in functions[helper['name']])
        for offset,text in {0x17a:'sd s7,56(sp)',0x17c:'sd t1,48(sp)',0x17e:'sd t5,40(sp)',0x180:'sd t6,32(sp)',
            0x236:'ld t0,56(sp)',0x238:'srli a4,s6,0x20',0x240:'or a4,a4,t0',
            0x25e:'ld t6,32(sp)',0x260:'ld t5,40(sp)',0x262:'ld t1,48(sp)'}.items():
            assert code[addr(offset)]['text']==text,'Caller ABI '+hex(offset)
        assert sizes['a']==sizes['b']==2048 and sizes['mask']==128 and sizes['output']==130
        assert sizes['input_periods']==1536 and sizes['oracle_records']==71680
        assert all(symbols[n]%8==0 for n in ('a','b','mask','output','input_periods','oracle_records'))
        assert symbols['__bss_end']<symbols['__stack_top']-65536
        bss=symbols['__bss_end']-symbols['__bss_start'];assert bss%8==0
        for name,limit in [('replay_text',32),('replay_write',48),('num',32)]:assert len(functions[name])<=limit
        core=sum(counts.values());helper_count=326147;startup=4*(bss//8)+100;printing=256*64+16*128
        upper=core+helper_count+startup+printing
        report=dict(status='STATIC_LINKED_COST_UNDER_3M' if upper<=3000000 else 'HOLD_OVER_3M',
            backend=backend,elf_sha256=sha(directory/'program.elf'),calls=17920,result_bits=286720,
            guards=35840,flags=17920,vstarts=17920,original_helper_instructions=326144,capacity_instructions=3,
            body_instructions=core,whole_success_upper=upper,margin_to_3M=3000000-upper,
            startup_upper=startup,wrapper_printing_upper=printing,blocks=ledger,edges=edges,
            failure_PCs={str(k):v for k,v in zeros.items()},full_body_partition=True,flow_conservation=True,
            fresh_store_sites=stores,input_LD_sites=loads,fresh_stores=734720,input_LD=143360,
            output_LWU=17920,mode_record_LD=8960,record_bytes=71680,input_period_bytes=1536,
            BSS_bytes=bss,image_used_through_BSS=symbols['__bss_end']-0x80000000,
            stack_reserved=65536,normal_nested_frame=288,conservative_stack_requirement=512,
            ABI='s6 record preserved; sticky/s1-source temporaries explicitly spill/reload',
            no_extra_RVV_FP=True,all185_helper_encodings=True,
            limitation='All-correct terminating CFG conditional bound, not firmware measurement or failing-path deadline guarantee')
        save(out/(backend+'.json'),report);reports[backend]=report
    assert all(sha(p)==h for p,h in pins.items())
    save(out/'RESULT.json',dict(status='STATIC_COST_GATE_PASS_PENDING_REFERENCE_ADMISSION' if all(r['whole_success_upper']<=3000000 for r in reports.values()) else 'HOLD_COST',
        backends={k:{n:r[n] for n in ('elf_sha256','whole_success_upper','margin_to_3M')} for k,r in reports.items()},
        pins_unchanged=True,reference_executed=False,DUT_executed=False))
    print(json.dumps({k:r['whole_success_upper'] for k,r in reports.items()}),flush=True)


if __name__=='__main__':main()
