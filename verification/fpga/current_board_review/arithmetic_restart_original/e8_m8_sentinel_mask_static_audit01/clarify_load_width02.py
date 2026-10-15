"""Correct load-kind labels in the static facts; no program or raw execution."""
import json,hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
path=HERE/'ARTIFACT_AUDIT.json'
p=json.loads(path.read_text())
count=p['ID0'].pop('retained_gold_LD_if_exact_specialization')
p['ID0']['retained_gold_scalar_loads_if_exact_specialization']=count
p['ID0']['retained_gold_fullword_LD']=count-4095
p['ID0']['retained_gold_tail_LHU']=4095
p['old_gold_fullword_LD']=4095*128
p['old_gold_tail_LHU']=4095
p['old_full_comparator_instructions']=4095*451
p['classification_note']='Fullword compares use BEQ/BNE. Final tail alone uses SUB/SNEZ after two LHU; do not call this per-word sticky.'
assert all(v['success_leaf_op_counts']['ld']==256 and v['success_leaf_op_counts']['lhu']==19
    for v in p['backends'].values())
p['parent_static_facts_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
p['pins'][str(path)]=p['parent_static_facts_sha256']
p['pins'][str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
with (HERE/'ARTIFACT_AUDIT02.json').open('x') as f:json.dump(p,f,indent=2);f.write('\n')
print('FACTS02',hashlib.sha256((HERE/'ARTIFACT_AUDIT02.json').read_bytes()).hexdigest())
