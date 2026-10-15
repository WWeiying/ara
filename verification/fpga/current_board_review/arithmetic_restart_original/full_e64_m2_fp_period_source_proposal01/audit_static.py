"""Source algebra and instruction-list inventory only; no Host, compiler or ISA execution."""
import hashlib
import json
from pathlib import Path
import re
H=Path(__file__).resolve().parent
OLD=H.parent/'full_e64_m2_block_software01'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(b,s):
    if not b:raise ValueError(s)
def main():
    pins=json.loads((OLD/'pins.json').read_text())
    for p,h in pins.items():need(sha(p)==h,'Sealed artifact drift '+p)
    source=(OLD/'case.c').read_text();proposal=(H/'case_proposal.c').read_text();header=(H/'fp_period.h').read_text()
    block=(H/'original_FP_block.txt').read_text().rstrip('\n')
    inverse=proposal.replace('#include "fp_period.h"\n','').replace('#if SEW >= 32\n                    if(op>=25)refresh_fp_period(a,b,fp_inputs,seed);\n#endif',block)
    need(inverse==source,'ONLY FP loop replacement and include')
    rows=json.loads((OLD/'sequence.json').read_text());need(len(rows)==5985,'Original full sequence')
    cases=[]
    for seed in range(3):
        body=header.split(f'    case {seed}:\n')[1].split('        break;')[0]
        stores=[(b,int(i),int(v)) for b,i,v in re.findall(r'fp_period_store\(dst_([ab])\+(\d+),v(\d)\);',body)]
        expected=[(b,i,((i if b=='a' else 3*i)+seed)%8) for i in range(32) for b in ('a','b')]
        need(stores==expected,'All64 stores exact original order/indices')
        need(len(set((b,i) for b,i,v in stores))==64,'All fresh destinations without omission')
        cases.append(dict(seed=seed,ordered_stores=stores,stores=64,source_period=8))
    need(header.count('table[')==8 and 'const volatile uint64_t *table=input;' in header,'Eight fresh table loads inside every call')
    fp_calls=sum(r['op']>=25 for r in rows);need(fp_calls==1890,'Every original FP call including VL0')
    asm=(H/'lowering_witness.S').read_text();prefix=asm.split('.Lfp_seed2:\n')[0]
    instructions=lambda s:[l.strip() for l in s.splitlines() if l.startswith('    ')]
    prefix_count=len(instructions(prefix));need(prefix_count==13,'Eight LD plus five selector instructions')
    branches=[]
    regs=['t0','t1','t2','t3','t4','t5','t6','a4']
    for seed in range(3):
        body=asm.split(f'.Lfp_seed{seed}:\n')[1].split('.Lfp_')[0]
        ops=instructions(body);need(len(ops)==65 and ops[-1]=='ret','Exactly64 SD plus return')
        expected=[f'sd {regs[((i if b=="a" else 3*i)+seed)%8]},{8*i}({"a0" if b=="a" else "a1"})' for i in range(32) for b in ('a','b')]
        need(ops[:-1]==expected,'Witness matches proposed original store mapping')
        branches.append(dict(seed=seed,store_instructions=64,return_instructions=1,callee_upper=78))
    old_review=json.loads((OLD/'compiled_review.json').read_text())
    terms={t['name']:t for t in old_review['terms']}
    old_phase=sum(terms[n]['instructions'] for n in ('FP_loop','FP_setup_and_return'))
    need(old_phase==491*1890,'Actual old ELF491 instructions/FPcall')
    # Constructive RV64 leaf bound:78 callee+50 caller allowance. Not a GCC receipt.
    replacement_upper=128;constructive_saving=(491-replacement_upper)*1890
    need(constructive_saving>=75000,'Constructive saving threshold')
    for p,h in pins.items():need(sha(p)==h,'Sealed pre/post unchanged '+p)
    inputs=[OLD/'pins.json',OLD/'compiled_review.json',OLD/'case.c',H.parent/'full_e64_m2_software_review01/REVIEW.json',H/'fp_period.h',H/'case_proposal.c',H/'original_FP_block.txt',H/'lowering_witness.S',H/'audit_static.py']
    result=dict(status='STATIC_SOURCE_PROPOSAL_ONLY_NOT_GCC_MEASURED',source_reverse_delta_equal=True,calls=5985,FP_calls=1890,FP_word_stores=120960,per_FPcall_stores=64,per_FPcall_a_before_b=True,cases=cases,witness_branches=branches,old_actual_CFG_FP_phase=old_phase,old_actual_CFG_per_FPcall=491,constructive_lowering_per_FPcall_upper=128,constructive_saving=constructive_saving,constructive_net_upper_if_other_CFG_unchanged=old_review['positive_path_conservative_upper']-constructive_saving,actual_new_GCC_instruction_count=None,minimum_measured_net_saving_required=75000,actual_future_full_CFG_gate=3000000,old_HOLD_preserved=True,Host_executed=False,compile_executed=False,reference_executed=False,DUT_executed=False,pins={str(p):sha(p) for p in inputs})
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
