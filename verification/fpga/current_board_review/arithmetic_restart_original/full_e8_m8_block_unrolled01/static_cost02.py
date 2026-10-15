"""Count actual success-path basic blocks; no instruction execution or raw read."""
import hashlib
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'full_e8_m8_block_prepare01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dis(root):
    return {int(m[1],16):dict(insn=int(m[2],16),op=m[3],args=m[4]) for m in re.finditer(
        r'^[ \t]*([0-9a-f]+):[ \t]+([0-9a-f]{4,8})[ \t]+(\S+)[ \t]*([^\n]*)',
        (root/'spike/program.dis').read_text(),re.M)}
old,new=dis(OLD),dis(HERE)
for root,code in ((OLD,old),(HERE,new)):
    addresses={int(m[1],16) for line in (root/'spike/program.dis').read_text().splitlines()
        if (m:=re.match(r'^[ \t]*([0-9a-f]+):[ \t]+[0-9a-f]{4,8}[ \t]+',line))}
    assert set(code)==addresses, 'Cross-line/missing instruction parse'
assert new[0x800000b6]['op']=='ret' and new[0x800000b8]['op']=='ld'

def region(code,a,b):return [code[pc] for pc in sorted(code) if a<=pc<b]
def count(code,a,b):return len(region(code,a,b))

# Range ends are exclusive; frequencies follow the unchanged original loop nest.
rows=[
 ('prologue',0x350,0x3ba,0x9ae,0xa18,1),
 ('seed_setup',0x3ba,0x3e4,0xa18,0xa42,3),
 ('rng_common_to_case2',0x3e4,0x40a,0xa42,0xa68,3072),
 ('rng_noncase2',0x40a,0x40e,0xa68,0xa6c,2688),
 ('rng_zero_or_one',0x40e,0x412,0xa6c,0xa70,768),
 ('rng_case1',0x412,0x41a,0xa70,0xa78,384),
 ('rng_case2',0xb84,0xb8e,0x134c,0x1358,384),
 ('rng_case_gt2',0xb7a,0xb7e,0x1340,0x1344,1920),
 ('rng_case3',0xb7e,0xb84,0x1344,0x134c,384),
 ('rng_case0',0xb8e,0xba0,0x1358,0x136a,384),
 ('rng_common_advance_nonzero',0x41a,0x424,0xa78,0xa82,2688),
 ('after_seed_inputs',0x424,0x430,0xa82,0xa8e,3),
 ('op_setup',0x430,0x47a,0xa8e,0xad8,75),
 ('first_vl_check',0x47a,0x47e,0xad8,0xadc,75),
 ('subsequent_vl',0x486,0x48e,0xae4,0xaec,450),
 ('vl_setup_including_optional_li3',0x48e,0x4c4,0xaec,0xb28,525),
 ('mask_enter',0x4c4,0x4d2,0xb28,0xb36,1575),
 ('mask_copy_common',0x4d6,0x4e2,0xb3a,0xb46,1575*16),
 ('mask_copy_nonfirst',0x4d2,0x4d6,0xb36,0xb3a,1575*15),
 ('trial_loop_setup',0x4e2,0x4fa,0xb46,0xb60,1575),
 ('trial_counter',0x5e6,0x608,0xd98,0xdbc,4095),
 ('next_trial_kind',0x608,0x60e,0xdbc,0xdc2,2520),
 ('next_trial_half',0x950,0x95a,0x1116,0x1120,1260),
 ('next_trial_end_check',0x60e,0x612,0xdc2,0xdc6,1260),
 ('next_trial_end_not_cap',0x612,0x618,0xdc6,0xdcc,1080),
 ('next_trial_end_cap',0x948,0x950,0x110e,0x1116,180),
 ('after_mask',0x618,0x628,0xdcc,0xddc,1575),
 ('next_mask',0x628,0x630,0xddc,0xde6,1050),
 ('next_vl',0x95a,0x964,0x1120,0x112a,525),
 ('next_op',0x964,0x970,0x112a,0x1136,75),
 ('next_seed',0x970,0x978,0x1136,0x113e,3),
]
report=[]
for name,a,b,c,d,freq in rows:
    a,b,c,d=(x+0x80000000 for x in (a,b,c,d))
    oc,nc=count(old,a,b),count(new,c,d)
    report.append(dict(name=name,old_range=[hex(a),hex(b)],new_range=[hex(c),hex(d)],
        old_instructions=oc,new_instructions=nc,frequency=freq,delta=(nc-oc)*freq))
# One listed LI3 is skipped for105 special-kind VL groups in each version;
# subtracting that common charge cancels in the delta.
old_init=count(old,0x800004fa,0x80000544)+15*10
new_init=count(new,0x80000b60,0x80000d86)
report.append(dict(name='initializer_and_helper_call_setup',old_instructions=old_init,
    new_instructions=new_init,frequency=4095,delta=(new_init-old_init)*4095))
old_cmp=count(old,0x80000544,0x800005e6)+15*32
# All-success comparator takes BEQ b0->b8, skipping fail LI/RET at b4/b6.
new_leaf=count(new,0x80000082,0x800006e0)-2
new_cmp=count(new,0x80000d86,0x80000d98)+new_leaf
report.append(dict(name='comparison_including_actual_call_ret',old_instructions=old_cmp,
    new_instructions=new_cmp,leaf_success_instructions=new_leaf,frequency=4095,delta=(new_cmp-old_cmp)*4095))
old_print=region(old,0x80000978,0x80000ad2)
new_print=region(new,0x8000113e,0x80001298)
assert [x['op'] for x in old_print]==[x['op'] for x in new_print], 'Print CFG changed'
assert not any('(sp)' in x['args'] for x in region(new,0x80000082,0x800006e0)), 'New comparator stack spill'
assert old[0x80000350]['args'].endswith('-304') and new[0x800009ae]['args'].endswith('-304')
delta=sum(x['delta'] for x in report)
proof=json.loads((HERE/'proof.json').read_text());oldproof=json.loads((OLD/'proof.json').read_text())
result=dict(status='STATIC_ACTUAL_CODE_NET_SAVING_GATE',blocks=report,
    common_optional_li3_skips_each=105,main_print_cfg_mnemonics_equal=True,
    comparator_stack_memory_instructions=0,main_frame_bytes_both=304,
    delta_instructions=delta,baseline_firmware=3271926,predicted_firmware=3271926+delta,
    exact_other_runtime_path_assumption='Unchanged source and opcode CFG; relocation only; no new reference',
    conservative_other_path_reserve=10000,conservative_firmware=3271926+delta+10000,
    reference_allowed_by_cost=3271926+delta+10000<=3000000,
    layout={b:dict(stack_gap=proof['backends'][b]['stack_gap'],
       prior_gap=oldproof['backends'][b]['stack_gap'],
       allocated_growth=oldproof['backends'][b]['stack_gap']-proof['backends'][b]['stack_gap']) for b in ('soc','spike')},
    pins={str(p):sha(p) for p in (HERE/'static_cost02.py',HERE/'spike/program.dis',OLD/'spike/program.dis',
        HERE/'proof.json',OLD/'proof.json',OLD/'HOLD.json')})
with (HERE/'static_cost02.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('blocks','pins')},indent=2))
