#!/usr/bin/env python3
"""Mechanical specialization of accepted m1 entry; no execution of a reference."""
import hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
OLD=HERE.parents[1]/'full_e32_m1_packed_prepare01/reference_entry01'
def emit(name,text):
    with (HERE/name).open('x') as f:f.write(text)
def subst(text,old,new):
    if old not in text:raise ValueError('Missing specialization '+old)
    return text.replace(old,new)
def main():
    text=(OLD/'context.py').read_text().replace('software02','software01')
    emit('context.py',text)
    for name in ('raw_boundary.py','test_boundary.py'):emit(name,(OLD/name).read_text())
    text=(OLD/'reference_check.py').read_text()
    for old,new in [('range(17)','range(33)'),('full17','full33'),('exact17','exact33'),
                    ('==32','==64'),('not32','not64'),("row['vl'],32,mask", "row['vl'],64,mask"),
                    ('else 32','else 64'),("row['start']),", "row['start']),"),
                    ("row['vl'],16,row['start']", "row['vl'],17,row['start']"),
                    ('[91]*34','[91]*66'),('[91]*32','[91]*64'),('[4:132]','[4:260]'),
                    ('1<<32','1<<64'),("row['mask'][:4]", "row['mask'][:8]"),
                    ('136','264'),('191520','383040'),('101745','197505'),
                    ('vlmax=32','vlmax=64'),('physical_registers_per_group=1','physical_registers_per_group=2'),
                    ('observed_register_bytes=128','observed_register_bytes=256'),('vlm_read_bytes=4','vlm_read_bytes=8')]:
        text=subst(text,old,new)
    text=subst(text,'lifecycle.read(pc,address,rwidth)',
        "require(rd is not None,'Scalar read missing actual destination')\n                lifecycle.read(pc,address,rwidth,int(rd[2],16))")
    text=subst(text,"            if rd:\n                n=int(rd[1]);regs[n]=int(rd[2],16) if n else 0", """            if pc==symbols['arithmetic_main']:
                require(rd and int(rd[1])==2 and int(rd[2],16)==symbols['__stack_top']-336,'Actual hashbound main stack frame')
            if rd:
                n=int(rd[1]);regs[n]=int(rd[2],16) if n else 0""")
    text=subst(text,'FP_calls=lifecycle.fp_calls,', 'FP_calls=lifecycle.fp_calls,seed_cache_reads=lifecycle.cache_reads,seed_cache_stores=lifecycle.cache_stores,FP_cache_reads=lifecycle.fp_reads,')
    text=subst(text,'fflags_oracle=False,bootstrap_fcsr_zero_instructions=bootstrap_fcsr)',
        "fflags_oracle=False,bootstrap_fcsr_zero_instructions=bootstrap_fcsr,\n                    ownership_scope='Spike actual helper/source lifecycle; no DUT CVX tokens',\n                    VI2_short_noop_calls=sum(r['op']==19 and r['vl']<=2 for r in rows),\n                    no_helper_or_oracle_waiver_for_noop=True)")
    emit('reference_check.py',text)
    text=(OLD/'reference.py').read_text()
    for old,new in [('compiled_audit02','compiled_audit01'),('191520','383040'),('101745','197505'),('120960','241920')]:text=subst(text,old,new)
    text=subst(text,"        p.save(folder/'STOPPED.json',dict", "        check_pins(pins)\n        p.save(folder/'STOPPED.json',dict")
    emit('reference.py',text)
    print('SOURCE_ONLY_SPECIALIZATION_COMPLETE')
if __name__=='__main__':main()
