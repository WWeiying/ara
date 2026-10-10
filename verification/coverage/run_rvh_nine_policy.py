"""Thin one-shot foreground runner for a separately reviewed nine-policy plan."""
from pathlib import Path
from types import FunctionType

import run_lzc_snapshot_eight_policy as prior
import prepare_rvh_nine_policy as generic

frozen,require=generic.frozen,generic.require
SCRIPT=Path(__file__).resolve()
TEST=generic.TEST
for name,value in vars(prior).items():
    if isinstance(value,FunctionType) and value.__module__==prior.__name__:
        globals()[name]=FunctionType(value.__code__,globals(),name,value.__defaults__,value.__closure__)
    elif not name.startswith('__') and name not in ('generic','SCRIPT','TEST'):
        globals().setdefault(name,value)


def entry_dependencies(output):
    return (*generic.dependencies(),Path(prior.__file__).resolve(),output/generic.PLAN)


def prepare_entry(output,config_seal):
    output=output_path(output);unstarted(output)
    require(not(output/PLAN).exists(),'Launch plan exists')
    _,config=generic.read_config(output,config_seal)
    pins=generic.merge_pins(config['pins'],{str(p):frozen.sha(p) for p in entry_dependencies(output)})
    plan=dict(schema='RVH_NINE_POLICY_SINGLE_LAUNCH_V1',output=str(output),config_sha256=config_seal,
        population=config['population'],admission_manifest_sha256=config['admission_manifest_sha256'],
        command=config['command'],targets=6139,protected=19307,audited=25446,
        timeout_seconds=frozen.TIMEOUT,config_reprepared=False,automatic_retry=False,
        launch_approved=False,parent_review_required=True,application_approval=False,pins=pins)
    generic.eight.mask.save(output/PLAN,plan)
    return plan


def reviewed_entry(output,launch_seal):
    output=output_path(output);plan=frozen.load_sealed(output/PLAN,launch_seal)
    require(plan['schema']=='RVH_NINE_POLICY_SINGLE_LAUNCH_V1' and plan['output']==str(output)
        and (plan['targets'],plan['protected'],plan['audited'])==generic.COUNTS
        and plan['timeout_seconds']==frozen.TIMEOUT and plan['parent_review_required'] is True
        and all(plan[k] is False for k in ('config_reprepared','automatic_retry','launch_approved',
                                        'application_approval')),'Nine launch contract changed')
    generic.check_pins(plan['pins'])
    context,config=generic.read_config(output,plan['config_sha256'])
    require(plan['population']==config['population'] and
        plan['admission_manifest_sha256']==config['admission_manifest_sha256'] and
        plan['command']==config['command'] and
        all(plan['pins'].get(p)==h for p,h in config['pins'].items()),'Launch binding changed')
    for p in entry_dependencies(output):
        require(plan['pins'].get(str(p))==frozen.sha(p),'Missing launch dependency')
    return plan,context,config


if __name__=='__main__':main()
