"""Source-to-M9 owner eligibility; not a Spike cvx/uop acceptance claim."""
from context import artifacts,require
def target_required(row,insn):
    if row['vl']==0 or row['start']>=row['vl']:return False
    if row['op']==19:
        require(insn&127==0x57 and (insn>>12)&7==3 and (insn>>26)&63==14 and (insn>>15)&31==2,
            'Only exact actual VSLIDEUP.VI offset2 optional-owner exception')
        if row['vl']<=2:return False
    return True
def ledger():
    _,_,helpers,rows=artifacts();out=[]
    for row in rows:
        insn=helpers[f'op_{row["op"]}'][8]['insn']
        out.append(dict(ordinal=row['ordinal'],op=row['op'],vl=row['vl'],vstart=row['start'],
            target_insn=insn,target_required=target_required(row,insn),required_setup_memory_indices=[1,2,3,4,11]))
    return out
