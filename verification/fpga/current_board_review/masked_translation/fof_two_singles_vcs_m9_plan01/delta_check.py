"""AST transfer check for the reviewed numeric-first bounded two-job core."""
import ast
import hashlib
import json
from pathlib import Path
H=Path(__file__).resolve().parent
OLD=H.parent/'unit_fof_e64_sc0_sc3_vcs_m9_plan01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def functions(p,normalize=False):
    text=p.read_text()
    if normalize:text=text.replace("str(case['scenario'])","str(case['sew'])")
    return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)}
if __name__=='__main__':
    names=('terminal_plan_gate','owner_gate','authorization_gate','durable_monitor','checked_runner',
           'options_for','tests_for','dryrun','run','main')
    a,b=functions(OLD/'replay.py',True),functions(H/'replay.py')
    for n in names:
        if a[n]!=b[n]:raise ValueError('Unexpected core delta: '+n)
    result=dict(status='STATIC_CORE_EQUIVALENT_NOT_HOST_RERUN',matched_functions=list(names),
        worker_sha256=sha(H/'replay.py'),checker_sha256=sha(H/'checker.py'),
        predecessor_worker_sha256=sha(OLD/'replay.py'),predecessor_delta_sha256=sha(OLD/'delta_receipt.json'),
        allowed_core_delta='spec table key scenario -> sew for exact two unchanged original ELFs')
    with (H/'delta_receipt.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(result['status'])
