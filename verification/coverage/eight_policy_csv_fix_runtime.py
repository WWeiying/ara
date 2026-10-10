"""Independent CSV-dependency-only eight successor; preparation never launches EDA."""
import argparse
import copy
import json
from pathlib import Path
from types import FunctionType

import prepare_rvh_nine_policy as shared

eight, frozen, require = shared.eight, shared.frozen, shared.require
six = eight.six
SCRIPT=Path(__file__).resolve()
TCL=SCRIPT.with_suffix('.tcl')
TEST=SCRIPT.with_name('test_eight_policy_csv_fix.py')
RUNNER=SCRIPT.with_name('run_eight_policy_csv_fix.py')
PLAN='csv-fixed-eight-plan.json'
COUNTS=(5892,17774,23666)


def dependencies():
    return (SCRIPT,TCL,TEST,RUNNER,shared.SCRIPT,shared.CSV_SOURCE,shared.backend.SCRIPT,
            eight.SCRIPT,eight.TCL,Path(eight.prior.lifecycle.__file__).resolve())


def payloads(base):
    names=(*eight.prior.HELPERS,'six-library.tcl','seven-selection.tcl',
           'snapshot-selection.tcl','combined-eight.el','config.json')
    result={n:(base/n).read_bytes() for n in names}
    result['csv-row-library.tcl']=shared.csv_library().encode('ascii')
    return result


def prepare(output,base,base_seal,population):
    shared.backend.immutable_eight()
    require(output.parent==frozen.OUT and output.resolve()==output and not output.exists(),
            'Fresh direct CSV successor output required')
    _,config=eight.read_config(base,base_seal)
    source=frozen.load_sealed(base/'runtime-plan.json',base_seal)
    shared.population_gate(population,source)
    pins=shared.merge_pins(config['pins'],{str(base/'runtime-plan.json'):base_seal},
        {str(p):frozen.sha(p) for p in dependencies()})
    shared.check_pins(pins)
    output.mkdir()
    for name in (*frozen.GROUPS,'lzc','snapshot'):(output/name).mkdir()
    for name,data in payloads(base).items():(output/name).write_bytes(data)
    for path in output.iterdir():
        if path.is_file():pins=shared.merge_pins(pins,{str(path):frozen.sha(path)})
    command=eight.prior.lifecycle.tool.launch_command(config['plan']['tool_identity'],TCL)
    facade=copy.deepcopy(source);facade.update(output=str(output),command=command,pins=pins)
    eight.mask.save(output/'runtime-plan.json',facade)
    pins=shared.merge_pins(pins,{str(output/'runtime-plan.json'):frozen.sha(output/'runtime-plan.json')})
    plan=dict(schema='EIGHT_CSV_DEPENDENCY_ONLY_SUCCESSOR_V1',output=str(output),population=population,
        eight_output=str(base),eight_seal=base_seal,admission_sha256=source['admission_sha256'],
        targets=5892,protected=17774,audited=23666,command=command,timeout_seconds=frozen.TIMEOUT,
        csv_source=str(shared.CSV_SOURCE),csv_source_sha256=frozen.sha(shared.CSV_SOURCE),
        csv_helper_sha256=frozen.sha(output/'csv-row-library.tcl'),
        application_approval=False,launch_approved=False,automatic_retry=False,
        official_denominator_verified=False,new_RTL_signoff=False,pins=pins)
    eight.mask.save(output/PLAN,plan)
    eight.mask.save(output/'status.json',dict(status='PREPARED_NO_DVE',application_approval=False))
    return plan


def read_config(output,seal):
    shared.backend.immutable_eight()
    require(output.parent==frozen.OUT and output.resolve()==output,'Unsafe CSV successor output')
    plan=frozen.load_sealed(output/PLAN,seal)
    require(plan['schema']=='EIGHT_CSV_DEPENDENCY_ONLY_SUCCESSOR_V1' and plan['output']==str(output)
        and (plan['targets'],plan['protected'],plan['audited'])==COUNTS
        and plan['timeout_seconds']==frozen.TIMEOUT and all(plan[k] is False for k in
            ('application_approval','launch_approved','automatic_retry','official_denominator_verified',
             'new_RTL_signoff')),'CSV successor contract changed')
    shared.check_pins(plan['pins'])
    base=Path(plan['eight_output'])
    context,config=eight.read_config(base,plan['eight_seal'])
    source=frozen.load_sealed(base/'runtime-plan.json',plan['eight_seal'])
    shared.population_gate(plan['population'],source)
    require(plan['admission_sha256']==source['admission_sha256'] and
        all(plan['pins'].get(p)==h for p,h in config['pins'].items()),'Source population/pins differ')
    for path in (*dependencies(),base/'runtime-plan.json',output/'runtime-plan.json'):
        require(plan['pins'].get(str(path))==frozen.sha(path),'Missing CSV successor dependency')
    for name,data in payloads(base).items():
        path=output/name
        require(path.is_file() and not path.is_symlink() and
            plan['pins'].get(str(path))==frozen.sha(path) and path.read_bytes()==data,
            'CSV successor changes beyond helper installation: '+name)
    require(plan['csv_source']==str(shared.CSV_SOURCE) and
        plan['csv_source_sha256']==frozen.sha(shared.CSV_SOURCE) and
        plan['csv_helper_sha256']==frozen.sha(output/'csv-row-library.tcl'),'CSV helper identity changed')
    command=eight.prior.lifecycle.tool.launch_command(config['plan']['tool_identity'],TCL)
    require(plan['command']==command,'CSV successor command changed')
    facade=copy.deepcopy(source)
    facade.update(output=str(output),command=command,pins={p:h for p,h in plan['pins'].items()
        if p!=str(output/'runtime-plan.json')})
    require(json.loads((output/'runtime-plan.json').read_bytes())==facade,'Eight facade changed')
    derived=copy.deepcopy(config);derived.update(output=str(output),command=command,pins=plan['pins'])
    return context,derived


def verify(output,seal):
    # Only the reader is substituted. The frozen verifier body and native binders are unchanged.
    namespace=dict(eight.__dict__,read_config=read_config)
    verifier=FunctionType(eight.verify.__code__,namespace,eight.verify.__name__,
                          eight.verify.__defaults__,eight.verify.__closure__)
    result=verifier(output,seal)
    lines=(output/'DVEfiles/dve_gui.log').read_text().splitlines()
    require(lines.count('EIGHT_CSV_WRITER_INSTALLED')==1,'Missing CSV-before-init evidence')
    result['files'].update({str(output/p):frozen.sha(output/p) for p in
        (PLAN,'csv-row-library.tcl')})
    result.update(csv_dependency_only_successor=True,original_eight_verifier_unchanged=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','check','verify'))
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--seal')
    parser.add_argument('--eight-output',type=Path);parser.add_argument('--eight-seal')
    parser.add_argument('--population',type=int)
    a=parser.parse_args();out=a.output.absolute()
    if a.mode=='prepare':
        require(a.eight_output and a.eight_seal and a.population and not a.seal,'Explicit source population required')
        prepare(out,a.eight_output.absolute(),a.eight_seal,a.population)
        result=dict(status='PREPARED_NO_DVE',seal=frozen.sha(out/PLAN))
    else:
        require(a.seal and not any((a.eight_output,a.eight_seal,a.population)),'Sealed output only')
        result=verify(out,a.seal) if a.mode=='verify' else dict(status='CHECKED_NO_DVE',
            population=read_config(out,a.seal)[1]['population'])
    print(json.dumps(result))


if __name__=='__main__':main()
