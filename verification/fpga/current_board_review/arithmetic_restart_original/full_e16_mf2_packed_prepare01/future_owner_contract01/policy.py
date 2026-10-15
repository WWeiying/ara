"""Unconsumed future M9 worker eligibility; no data/vstart oracle replacement."""
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent
DISPATCHER=Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/frozen/sources/hardware/src/ara_dispatcher.sv')
DISPATCHER_SHA='c179ddd08b2bdb8648246f187aa892be5853fda38aeca850402d5e5b9b17ef7d'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def no_work_reason(insn,vl,vstart):
    if not (type(insn)is int and type(vl)is int and type(vstart)is int and
        0<=insn<1<<32 and 0<=vl<=32 and 0<=vstart<=32):raise ValueError('Actual source dimensions required')
    if vstart>=vl:return 'vstart_ge_vl'
    # Only the actual unsigned VI decode is specialized, never VX/down/masks.
    if insn&127==0x57 and (insn>>12)&7==3 and insn>>26==0b001110:
        offset=(insn>>15)&31
        if offset>=vl:return 'unsigned_vslideup_vi_offset_ge_vl'
    return None
def required_target(insn,vl,vstart):return no_work_reason(insn,vl,vstart)is None
def contract():
    assert sha(DISPATCHER)==DISPATCHER_SHA
    proof=json.loads((SOURCE/'proof.json').read_text());backend=proof['backends']['soc']
    assert sha(backend['elf'])==backend['sha256']
    helpers=backend['helpers'];rows=json.loads((SOURCE/'sequence.json').read_text())
    assert len(rows)==4095 and len(helpers)==26
    target=[];reasons={}
    for row in rows:
        op=row['op'];instruction=helpers[f'op_{op}'][8]['insn']
        reason=no_work_reason(instruction,row['vl'],row['start'])
        if reason:reasons[reason]=reasons.get(reason,0)+1
        target.append(dict(call=row['ordinal'],op=op,seed=row['seed'],vl=row['vl'],vstart=row['start'],
            mode=row['mode'],pc=helpers[f'op_{op}'][8]['pc'],insn=instruction,required=reason is None,reason=reason))
    assert helpers['op_19'][8]['insn']==0x38813c57
    assert {x['op'] for x in target if x['reason']=='unsigned_vslideup_vi_offset_ge_vl'}=={19}
    assert {x['vl'] for x in target if x['reason']=='unsigned_vslideup_vi_offset_ge_vl'}=={1,2}
    return dict(source_calls=len(rows),required_helper_memory_owners=5*len(rows),
        required_target_owners=sum(x['required'] for x in target),
        required_op24_target_owners=sum(x['required'] and x['op']==24 for x in target),
        reason_counts=reasons,target_ledger=target,
        total_uop_count_fixed=False,full_oracle_and_vstart_unchanged=True)
