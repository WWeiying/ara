"""Source comparison only; reuse prior tested core without rerunning Host/DUT."""
import ast
import hashlib
import json
from pathlib import Path

H=Path(__file__).resolve().parent
OLD=H.parent/'unit_fof_e64_suffix_two_vcs_m9_plan01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def functions(path,normalize=False):
    text=path.read_text()
    if normalize:
        text=text.replace('UNIT_FOF_E64_SUFFIX','UNIT_FOF_E64_SC0_SC3').replace('masked-suffix','sc0/sc3')
    result={}
    for node in ast.parse(text).body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            if normalize and node.name=='artifacts':
                node.body=[x for x in node.body if not (isinstance(x,ast.Import)
                           and [a.name for a in x.names]==['source_owners'])]
            result[node.name]=ast.dump(node,include_attributes=False)
    return result

if __name__=='__main__':
    groups={
        'replay.py':('terminal_plan_gate','owner_gate','authorization_gate','durable_monitor',
                     'checked_runner','options_for','tests_for','dryrun','run','main'),
        'checker.py':('load','sha','specification','scope','runtime_case','console_gate','artifacts')}
    matched={}
    for file,names in groups.items():
        old,new=functions(OLD/file,True),functions(H/file)
        for n in names:
            if old[n]!=new[n]:raise ValueError('Unexpected reviewed-core delta '+file+':'+n)
        matched[file]=list(names)
    # Startup observer is the same two-sample observer, changing only the unit.
    old=(OLD/'observe_startup.py').read_text().replace('ara-unit-fof-e64-two-m9-01.service',
                                                     'ara-unit-fof-e64-sc0-sc3-m9-01.service')
    if old!=(H/'observe_startup.py').read_text():raise ValueError('Startup observer drift')
    result=dict(status='STATIC_CORE_EQUIVALENT_NOT_HOST_RERUN',matched_functions=matched,
                worker_sha256=sha(H/'replay.py'),checker_sha256=sha(H/'checker.py'),
                predecessor_worker_sha256=sha(OLD/'replay.py'),
                predecessor_host_sha256=sha(OLD/'host02/status.json'),
                exact_exit_hook_sha256=sha(OLD/'pinned_service_exit.py'),
                allowed_artifact_delta='marker/scope literals and import already loaded at module scope',
                DUT_or_reference_started=False)
    with (H/'delta_receipt.json').open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(result['status'],flush=True)
