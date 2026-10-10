"""Reuse frozen exclusive-claim lifecycle for explicitly reviewed eight-policy run."""
from pathlib import Path
from types import FunctionType

import run_lzc_selector_native_seven_policy as prior
import lzc_snapshot_eight_policy_runtime as generic

frozen,require=generic.frozen,generic.require
SCRIPT=Path(__file__).resolve();TEST=SCRIPT.with_name('test_run_lzc_snapshot_eight_policy.py')
for name,value in vars(prior).items():
    if isinstance(value,FunctionType) and value.__module__==prior.__name__:
        globals()[name]=FunctionType(value.__code__,globals(),name,value.__defaults__,value.__closure__)
    elif not name.startswith('__') and name not in ('generic','SCRIPT','TEST'):
        globals().setdefault(name,value)


def prepare_entry(output, config_seal):
    output=output_path(output);unstarted(output)
    require(not(output/PLAN).exists(),'Launch plan exists')
    _,config=generic.read_config(output,config_seal)
    runtime=frozen.load_sealed(output/'runtime-plan.json',config_seal);pins=dict(config['pins'])
    for f in (SCRIPT,TEST,Path(generic.__file__).resolve(),generic.TCL,output/'runtime-plan.json',Path(prior.__file__).resolve()):
        actual=frozen.sha(f);require(str(f) not in pins or pins[str(f)]==actual,'Entry pin conflict');pins[str(f)]=actual
    plan=dict(schema='eight-policy-explicit-single-launch-v1',output=str(output),config_sha256=config_seal,
        admission_manifest_sha256=runtime['admission_sha256'],population=runtime['population'],
        targets=5892,protected=17774,audited=23666,command=config['command'],timeout_seconds=frozen.TIMEOUT,
        config_reprepared=False,automatic_retry=False,launch_approved=False,parent_review_required=True,
        application_approval=False,pins=pins)
    generic.mask.save(output/PLAN,plan)
    generic.mask.save(output/'population-launch-plan.sha256.json',{str(output/PLAN):frozen.sha(output/PLAN)})
    return plan


def reviewed_entry(output, launch_seal):
    output=output_path(output);plan=frozen.load_sealed(output/PLAN,launch_seal)
    require(plan['schema']=='eight-policy-explicit-single-launch-v1' and plan['output']==str(output)
        and (plan['targets'],plan['protected'],plan['audited'],plan['timeout_seconds'])==(5892,17774,23666,frozen.TIMEOUT)
        and plan['parent_review_required'] is True and all(plan[k] is False for k in
            ('config_reprepared','automatic_retry','launch_approved','application_approval')),'Launch contract differs')
    for path,sha in plan['pins'].items():require(frozen.sha(path)==sha,'Launch pin drift')
    context,config=generic.read_config(output,plan['config_sha256'])
    require(plan['population']==config['population'] and plan['admission_manifest_sha256']==config['admission_manifest_sha256']
        and plan['command']==config['command'] and all(plan['pins'].get(p)==h for p,h in config['pins'].items()),'Launch input binding differs')
    for f in (SCRIPT,TEST,Path(generic.__file__).resolve(),generic.TCL,output/'runtime-plan.json',Path(prior.__file__).resolve()):
        require(plan['pins'].get(str(f))==frozen.sha(f),'Unpinned actual entry')
    return plan,context,config


if __name__=='__main__':main()
