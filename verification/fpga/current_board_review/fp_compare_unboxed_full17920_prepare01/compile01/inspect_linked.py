#!/usr/bin/env python3
"""Static linked-code ledger. No instruction emulator or reference execution."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
RUN = HERE/'run02'
ROOT = HERE.parent
NAME = 'fp_compare_unboxed_e16_mf4_full17920_main'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v): p.write_text(json.dumps(v,indent=2)+'\n')
def require(ok, why):
    if not ok: raise ValueError(why)

def parse(backend):
    d=RUN/backend; functions={}; current=None; code={}
    for line in (d/'disassemble.log').read_text().splitlines():
        m=re.match(r'^([0-9a-f]+) <([^>]+)>:',line)
        if m: current=m[2];functions[current]=[]
        m=re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([^\s]+)\s*(.*)',line)
        if m:
            pc=int(m[1],16); args=m[4].split('#')[0].strip()
            r=dict(pc=pc,insn=m[2],op=m[3],args=args,text=m[3]+' '+args)
            code[pc]=r;functions[current].append(r)
    symbols={}; sizes={}
    for line in (d/'symbols.log').read_text().splitlines():
        parts=line.split()
        if len(parts)==3: address,kind,name=parts
        elif len(parts)==4:
            address,size,kind,name=parts;sizes[name]=int(size,16)
        else: raise ValueError('Symbol parser')
        symbols[name]=int(address,16)
    return d,code,functions,symbols,sizes

# Exact addresses below belong to the pinned Spike ELF only. SoC differs by one
# mask-address materialization instruction; its independent addresses are checked.
BLOCKS=[
 ('entry_and_capacity_branch',0x0de,0x104,1),
 ('return',0x116,0x132,1),
 ('fixed_initialization',0x134,0x168,1),
 ('seed_initialization',0x16a,0x174,32),
 ('nonzero_mask_constant_load',0x176,0x176,32*10*7*3*2),
 ('fresh_setup_and_helper_call',0x17a,0x234,17920),
 ('packed_result_status_begin',0x236,0x26e,17920),
 ('flags_guards_no_error',0x272,0x2aa,17920),
 ('sticky_increment',0x36a,0x372,17920),
 ('sticky0_followthrough',0x376,0x376,8960),
 ('call_VL_and_mode_branch',0x378,0x380,17920),
 ('zero_mask_jump',0x384,0x384,4480),
 ('mode_increment',0x390,0x394,8960),
 ('mode_initialization',0x398,0x3aa,8960),
 ('length_increment',0x3ac,0x3b2,2240),
 ('length_record_load_and_input_addresses',0x3b6,0x3ea,2240),
 ('op_increment',0x3ec,0x3f2,320),
 ('op_function_pointer_initialization',0x3f6,0x40c,320),
 ('seed_increment',0x40e,0x414,32),
 ('summary_success_selection',0x418,0x420,1),
 ('summary_caller_and_exit',0x42a,0x470,1),
]
ZERO=[('capacity_failure',0x108,0x114),('error_details',0x2ae,0x368),
      ('bad_bit_popcount_loop',0x386,0x38e),('failure_summary_selection',0x422,0x426)]

def main():
    out=HERE/'linked_audit02';require(not out.exists(),'Fresh static audit only');out.mkdir()
    pins={str(p):sha(p) for p in RUN.rglob('*') if p.is_file()}
    pins[str(Path(__file__))]=sha(Path(__file__))
    save(out/'inputs_before.json',pins)
    old=json.loads((ROOT/'source_model02/helper_identity.json').read_text())['prior_actual_helpers']
    reports={}
    for backend in ('soc','spike'):
        d,code,func,sym,sizes=parse(backend)
        expected_sha={'soc':'19afd0c6fd9c0810efbfdd9a635d092672554e6a1f3d4a3a537af00c4de13e37',
                      'spike':'0ecbd714c95e1aed2b1a6586cebdd7953e090d2da6d8c6521ee1101c2aec9671'}[backend]
        require(sha(d/'program.elf')==expected_sha,'Exact actual ELF')
        helper_pcs=set()
        for helper in old:
            actual=func[helper['name']]
            require([r['insn'] for r in actual]==helper['codes'],'Actual all185 helper bytes '+helper['name'])
            helper_pcs.update(r['pc'] for r in actual)
        extra=[r for pc,r in code.items() if (r['op'].startswith('v') or (len(r['insn'])==8 and int(r['insn'],16)&127==0x53)) and pc not in helper_pcs]
        require(not extra,'Extra vector/FP instructions')
        body=func[NAME]; bodypcs={r['pc'] for r in body}
        def addr(offset):
            if backend=='spike': return 0x80000000+offset
            return 0x80000000+offset-(8 if offset<=0x180 else 4)
        counts=Counter(); ledger=[]
        for label,lo,hi,multiplicity in BLOCKS:
            first,last=addr(lo),addr(hi)
            require(first in bodypcs and last in bodypcs,'Actual block boundaries '+label)
            pcs=[r['pc'] for r in body if first<=r['pc']<=last]
            for pc in pcs:
                require(pc not in counts,'Overlapping accounting blocks')
                counts[pc]=multiplicity
            ledger.append(dict(name=label,first_pc=hex(first),last_pc=hex(last),static_instructions=len(pcs),
                               executions=multiplicity,total=len(pcs)*multiplicity))
        zeros={}
        for label,lo,hi in ZERO:
            for r in body:
                if addr(lo)<=r['pc']<=addr(hi): zeros[r['pc']]=label
        require(bodypcs==set(counts)|set(zeros),'Full source-function CFG partition')
        require(not set(counts)&set(zeros),'Success/failure partition overlap')
        # Source-derived loop totals, checked against actual branches/registers.
        anchors={0x104:('beq','a4,a5,'),0x234:('jalr','t2'),0x26e:('bnez','a5,'),
                 0x290:('bne','a0,a6,'),0x2aa:('beq','t6,s0,'),0x372:('beq','a3,a4,'),
                 0x380:('bne','s3,a5,'),0x394:('beq','s3,a4,'),0x3b2:('beq','a4,t1,'),
                 0x3f2:('beq','s4,a4,'),0x414:('bne','s5,a4,')}
        for pc,(op,args) in anchors.items():
            r=code[addr(pc)];require(r['op']==op and r['args'].startswith(args),'Actual CFG discriminator')
        # Flow conservation is independent of the arithmetic sum of block sizes.
        # Counts here are original source loop trip counts / all-correct predicates.
        taken={addr(pc):n for pc,n in {0x104:1,0x26e:0,0x290:0,0x2aa:17920,
               0x372:8960,0x380:13440,0x394:2240,0x3b2:320,0x3f2:32,0x414:31,0x420:1}.items()}
        incoming=Counter({body[0]['pc']:1}); edges=[]
        for r in body:
            pc=r['pc']; n=counts.get(pc,0)
            if not n:continue
            nextpc=pc+len(r['insn'])//2
            if r['op']=='ret':
                require(n==1,'Single function return');continue
            if r['op']=='j':
                target=int(r['args'].split()[0],16); dests=[(target,n)]
            elif r['op'] in ('beq','bne','bnez','beqz','bltu','bgeu','blt','bge','bltz','bgez'):
                require(pc in taken,'Unclassified successful conditional')
                target=int(r['args'].split(',')[-1].split()[0],16)
                dests=[(target,taken[pc]),(nextpc,n-taken[pc])]
            else:
                # Calls return to nextpc. Their callee bodies are separately bounded.
                dests=[(nextpc,n)]
            for dest,weight in dests:
                require(weight>=0 and (not weight or dest in bodypcs),'CFG edge escapes body')
                incoming[dest]+=weight
                if weight:edges.append(dict(source=hex(pc),destination=hex(dest),executions=weight))
        require(all(incoming[pc]==counts.get(pc,0) for pc in bodypcs),'Actual CFG incoming/outgoing balance')
        stores=[]
        for r in body:
            if addr(0x17a)<=r['pc']<=addr(0x234) and r['op'] in ('sd','sh') and '(sp)' not in r['args']:
                stores.append(r)
        want=[('sd','a4,%d(a5)'%o) for o in range(0,128,8)]
        for o in range(0,32,8):
            want += [('sd','a2,%d(a0)'%o),('sd',('a4' if o==24 else 'a2')+',%d(a1)'%o)]
        want += [('sd','s1,%d(s0)'%o) for o in range(0,128,8)]+[('sh','a4,128(s0)')]
        require([(r['op'],r['args']) for r in stores]==want,'41 exact fresh store sites')
        input_lds=[r for r in body if addr(0x1b8)<=r['pc']<=addr(0x1e4) and r['op']=='ld']
        require([r['args'] for r in input_lds]==['a2,0(s2)','a2,0(a4)','a2,8(s2)','a2,8(a4)',
                  'a2,16(s2)','a2,16(a4)','a2,24(s2)','a4,24(a4)'],'Eight actual per-call input LD sites')
        require(all(counts[r['pc']]==17920 for r in stores+input_lds),'Fresh setup not hoisted/elided')
        require(code[addr(0x244)]['text']=='lwu s0,0(s0)' and counts[addr(0x244)]==17920,'One aligned output LWU')
        require(code[addr(0x3c8)]['text']=='ld s6,0(a4)' and counts[addr(0x3c8)]==2240,'Record load once per8 calls')
        # ABI: record lives in preserved s6; sticky and live caller temporaries spill.
        for h in old:
            for r in func[h['name']]:
                require(not re.search(r'\bs(?:[0-9]|1[01])\b',r['args']), 'Helper clobbers saved register')
        abi={0x17a:'sd s7,56(sp)',0x17c:'sd t1,48(sp)',0x17e:'sd t6,40(sp)',
             0x236:'ld t0,56(sp)',0x238:'srli a4,s6,0x20',0x240:'or a4,a4,t0',
             0x25e:'ld t6,40(sp)',0x260:'ld t1,48(sp)'}
        for pc,text in abi.items():require(code[addr(pc)]['text']==text,'Actual caller ABI preservation')
        require(sizes['a']==sizes['b']==2048 and sizes['mask']==128 and sizes['output']==130,'Full backing arrays')
        require(all(sym[n]%8==0 for n in ('a','b','mask','output','input_periods','oracle_records')),'Actual alignment')
        require(sizes['input_periods']==1536 and sizes['oracle_records']==17920,'Actual ROM sizes')
        require(sym['__bss_end']<sym['__stack_top']-65536,'Linked stack reserve')
        core_count=sum(counts.values())
        helpers=7168*17+10752*19+3
        bss_words=(sym['__bss_end']-sym['__bss_start'])//8
        require((sym['__bss_end']-sym['__bss_start'])%8==0,'Actual BSS loop geometry')
        startup=4*bss_words+100
        # Bound all successful final printing and wrapper costs: <256 output bytes,
        # <=16 invocations, <64 instructions/character including text length scan,
        # decimal conversion (8 total digits), output byte loop and call overhead.
        printing_upper=256*64+16*128
        whole=core_count+helpers+startup+printing_upper
        require(len(func['replay_text'])<=32 and len(func['replay_write'])<=48 and len(func['num'])<=32,'Actual runtime bound structure')
        report=dict(status='COMPILED_SUCCESS_CFG_UNDER_3M_PENDING_INDEPENDENT_REVIEW' if whole<=3000000 else 'HOLD_COMPILED_CFG_OVER_3M',
                    elf_sha256=expected_sha, full_calls=17920, result_bits=286720, guards=35840,
                    blocks=ledger, harness_success_instructions=core_count, original_helpers=helpers,
                    BSS_words=bss_words,startup_upper=startup,wrapper_printing_upper=printing_upper,whole_success_upper=whole,
                    margin_to_3M=3000000-whole, zero_execution_failure_PCs={hex(k):v for k,v in zeros.items()},
                    all_source_body_instructions_partitioned=True, CFG_flow_conservation=True, CFG_edges=edges,
                    fresh_store_sites=stores,input_LD_sites=input_lds,
                    dynamic_input_LD=143360,dynamic_fresh_stores=734720,output_LWU=17920,record_LD=2240,
                    ABI=dict(record='s6 preserved through original helper',sticky='s7 ->56(sp)->t0; OR record flags',
                             source_frame=224,main_frame=16,number_frame=48,normal_max_nested_frame=288,
                             conservative_stack_requirement=512,reserved_stack=65536),
                    mapped_BSS_end=hex(sym['__bss_end']),image_used_through_BSS=sym['__bss_end']-0x80000000,
                    extra_RVV_FP=[],static_helper_encodings=185,
                    limitation='Static all-correct terminating CFG upper, not measured firmware cost or bound on failing/infinite hardware behavior; EOF park not counted.')
        save(out/(backend+'.json'),report);reports[backend]=report
    require({p:sha(Path(p)) for p in pins}==pins,'Artifact drift during static review')
    save(out/'inputs_after.json',pins)
    save(out/'RESULT.json',dict(status='STATIC_LINKED_PROOF_PENDING_INDEPENDENT_REVIEW',
         backends={k:{f:v[f] for f in ('status','whole_success_upper','margin_to_3M','elf_sha256')} for k,v in reports.items()},
         no_reference=True,no_DUT=True, source_unchanged=True))
    print(json.dumps({k:v['whole_success_upper'] for k,v in reports.items()}))

if __name__=='__main__':main()
