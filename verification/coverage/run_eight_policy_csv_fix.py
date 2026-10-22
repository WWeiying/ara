"""One-shot foreground lifecycle for the reviewed CSV-only eight successor."""
from pathlib import Path
from types import FunctionType

import run_lzc_snapshot_eight_policy as prior
import eight_policy_csv_fix_runtime as generic

frozen,require=generic.frozen,generic.require
SCRIPT=Path(__file__).resolve();TEST=generic.TEST
for name,value in vars(prior).items():
    if isinstance(value,FunctionType) and value.__module__==prior.__name__:
        globals()[name]=FunctionType(value.__code__,globals(),name,value.__defaults__,value.__closure__)
    elif not name.startswith('__') and name not in ('generic','SCRIPT','TEST'):
        globals().setdefault(name,value)


def entry_dependencies(output):
    return (*generic.dependencies(),Path(prior.__file__).resolve(),output/generic.PLAN)


def prepare_entry(output,config_seal):
    output=output_path(output);unstarted(output)
    require(not(output/PLAN).exists(),'CSV launch already prepared')
    _,config=generic.read_config(output,config_seal)
    pins=generic.shared.merge_pins(config['pins'],{str(p):frozen.sha(p) for p in entry_dependencies(output)})
    plan=dict(schema='EIGHT_CSV_FIX_SINGLE_LAUNCH_V1',output=str(output),config_sha256=config_seal,
        population=config['population'],admission_manifest_sha256=config['admission_manifest_sha256'],
        command=config['command'],targets=5892,protected=17774,audited=23666,
        timeout_seconds=frozen.TIMEOUT,config_reprepared=False,automatic_retry=False,launch_approved=False,
        parent_review_required=True,application_approval=False,pins=pins)
    generic.eight.mask.save(output/PLAN,plan)
    return plan


def reviewed_entry(output,launch_seal):
    output=output_path(output);plan=frozen.load_sealed(output/PLAN,launch_seal)
    require(plan['schema']=='EIGHT_CSV_FIX_SINGLE_LAUNCH_V1' and plan['output']==str(output)
        and (plan['targets'],plan['protected'],plan['audited'])==generic.COUNTS
        and plan['timeout_seconds']==frozen.TIMEOUT and plan['parent_review_required'] is True
        and all(plan[k] is False for k in ('config_reprepared','automatic_retry','launch_approved',
                                        'application_approval')),'CSV launch contract changed')
    generic.shared.check_pins(plan['pins'])
    context,config=generic.read_config(output,plan['config_sha256'])
    require(plan['population']==config['population'] and
        plan['admission_manifest_sha256']==config['admission_manifest_sha256'] and
        plan['command']==config['command'] and
        all(plan['pins'].get(p)==h for p,h in config['pins'].items()),'CSV launch binding changed')
    for path in entry_dependencies(output):
        require(plan['pins'].get(str(path))==frozen.sha(path),'Missing CSV launch dependency')
    return plan,context,config


if __name__=='__main__':main()
