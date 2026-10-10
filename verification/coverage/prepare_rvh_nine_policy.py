"""Thin nine-policy preparation; explicit population, completed eight reference, no EDA."""
import argparse
import copy
import csv
import json
from pathlib import Path

import rvh_nine_policy_runtime as backend
import report_scope_ancestors as ancestors

eight, frozen, require = backend.eight, backend.frozen, backend.require
six = eight.six
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_prepare_run_rvh_nine_policy.py')
RUNNER = SCRIPT.with_name('run_rvh_nine_policy.py')
TCL = SCRIPT.with_name('rvh_nine_policy_entry.tcl')
CSV_SOURCE = SCRIPT.with_name('export_dve_coverage.tcl')
PLAN = 'nine-plan.json'
COUNTS = (6139, 19307, 25446)


def dependencies():
    return (*backend.dependencies(), SCRIPT, TEST, RUNNER, TCL, CSV_SOURCE, Path(ancestors.__file__).resolve(),
            Path(eight.prior.lifecycle.__file__).resolve())


def csv_library():
    text=CSV_SOURCE.read_text()
    boundary='\nproc export_rows '
    require(text.startswith('proc csv_row {stream values} {\n') and text.count(boundary)==1,
            'CSV-only source boundary changed')
    prefix=text.split(boundary)[0]
    require(prefix.count('\nproc ')==0 and 'gui_' not in prefix and 'source ' not in prefix,
            'Not an isolated CSV writer')
    return prefix+'\n'


def merge_pins(*groups):
    result = {}
    for group in groups:
        for path, sha in group.items():
            require(path not in result or result[path] == sha, 'Inherited pin conflict: '+path)
            result[path] = sha
    return result


def check_pins(pins):
    for path, sha in pins.items():
        require(frozen.sha(path) == sha, 'Nine input drift: '+path)


def population_gate(population, runtime):
    require(type(population) is int and population >= 727 and
            type(runtime['population']) is int and runtime['population'] == population,
            'Explicit population must match rebound eight inputs; no relabel')


def completed_reference(output, config_seal, result_seal):
    require(not (output/'DVEfiles/dve_gui.log').is_symlink(), 'Aliased eight completion log')
    state = json.loads((output/'status.json').read_bytes())
    require(state.get('status') == 'HISTORICAL_EIGHT_POLICY_REPORT_NOT_FINAL_APPROVAL',
            'Eight must be terminal verified, not running/failed')
    saved = frozen.load_sealed(output/'capture-result.json', result_seal)
    actual = eight.verify(output, config_seal)
    # Frozen run appends these two facade hashes to the verifier result.
    extras = {str(output/n): frozen.sha(output/n) for n in ('config.json', 'selection.tcl')}
    actual = copy.deepcopy(actual)
    require(all(k not in actual['files'] or actual['files'][k] == v for k,v in extras.items()),
            'Eight completion file conflict')
    actual['files'].update(extras)
    require(all(saved.get(k) == v for k,v in actual.items()) and
            saved.get('config_sha256') == config_seal and saved.get('final_reset') is True,
            'Saved eight completion differs from independent verifier')
    runtime = frozen.load_sealed(output/'runtime-plan.json', config_seal)
    return runtime, merge_pins(runtime['pins'], saved['files'],
        {str(output/'runtime-plan.json'): config_seal, str(output/'capture-result.json'): result_seal})


def root_data(rows, config, contract):
    scopes = set(config['root_refresh_scopes']) | {r[0] for r in contract['native_rows']}
    roots = ancestors.report_ancestors(rows, scopes)
    by_scope = {}
    stack = []
    for row in rows:
        depth = int(row['Depth'])
        stack = stack[:depth]+[row['Name']]
        scope = '.'.join(stack)
        require(row['GUIPath'] == scope, 'Report GUIPath differs from Depth stack')
        by_scope[scope] = row['Name']
    literal = eight.prior.lifecycle.literal
    names = {s: by_scope[s] for s in roots}
    text = ('set qbsrefresh_scopes {'+' '.join(literal(s) for s in roots)+'}\n'
            'global combo_root_names\narray unset combo_root_names\narray set combo_root_names {'+
            ' '.join(literal(s)+' '+literal(names[s]) for s in roots)+'}\n')
    return roots, names, text


def payloads(base, contract, callback_seal, root_text):
    names = (*eight.prior.HELPERS, 'six-library.tcl', 'seven-selection.tcl',
             'snapshot-selection.tcl', 'combined-eight.el', 'config.json')
    result = {n: (base/n).read_bytes() for n in names}
    result.update({'eight-library.tcl': backend.eight_library().encode('ascii'),
        'csv-row-library.tcl': csv_library().encode('ascii'),
        'rvh9-selection.tcl': backend.selection_payload(contract, callback_seal).encode('ascii'),
        'combined-nine.el': b''.join(backend.sources(contract).values()),
        'root-selection.tcl': root_text.encode('ascii')})
    return result


def prepare(output, base, base_seal, population, reference, reference_seal, result_seal,
            review, review_seal):
    require(output.parent == frozen.OUT and output.resolve() == output and not output.exists(),
            'Fresh direct output required')
    context, config = eight.read_config(base, base_seal)
    runtime = frozen.load_sealed(base/'runtime-plan.json', base_seal)
    population_gate(population, runtime)
    completed, completion_pins = completed_reference(reference, reference_seal, result_seal)
    require(completed['population'] <= population, 'Completion reference newer than final population')
    _, reference_config = eight.read_config(reference, reference_seal)
    require(reference_config['inputs'][0] == config['inputs'][0] and
            (base/'combined-eight.el').read_bytes() == (reference/'combined-eight.el').read_bytes(),
            'Completion design/native policy reference differs')
    contract = backend.build_contract(base, base_seal, review, review_seal)
    receipt = frozen.load_sealed(review/'review-receipt.json', backend.RVH_REVIEW_SHA)
    review_record = frozen.load_sealed(review/'seal.json', review_seal)
    pins = merge_pins(config['pins'], completion_pins, receipt['input_pins'], review_record['output_pins'])
    for p,h in ((base/'runtime-plan.json',base_seal),(review/'seal.json',review_seal)):
        pins = merge_pins(pins, {str(p): h})
    for p in dependencies(): pins = merge_pins(pins, {str(p): frozen.sha(p)})
    check_pins(pins)
    # Use the independently qualified raw hierarchy, including collapsed generate names.
    raw_csv = reference/'summary_raw.csv'
    with raw_csv.open(newline='') as f: rows = list(csv.DictReader(f))
    roots, display, root_text = root_data(rows, config, contract)
    output.mkdir()
    for name in (*frozen.GROUPS, 'lzc', 'snapshot', 'rvh'): (output/name).mkdir()
    eight.mask.save(output/'rvh9-contract.json', contract)
    callback_seal = frozen.sha(output/'rvh9-contract.json')
    for name, data in payloads(base,contract,callback_seal,root_text).items():
        (output/name).write_bytes(data)
    for path in output.iterdir():
        if path.is_file(): pins = merge_pins(pins, {str(path): frozen.sha(path)})
    command = eight.prior.lifecycle.tool.launch_command(config['plan']['tool_identity'], TCL)
    facade = copy.deepcopy(runtime)
    facade.update(output=str(output),command=command,pins=pins)
    eight.mask.save(output/'runtime-plan.json', facade)
    pins = merge_pins(pins, {str(output/'runtime-plan.json'): frozen.sha(output/'runtime-plan.json')})
    plan = dict(schema='RVH_NINE_POLICY_PREPARED_V1',output=str(output),population=population,
        admission_sha256=runtime['admission_sha256'],eight_output=str(base),eight_seal=base_seal,
        completed_eight_output=str(reference),completed_eight_seal=reference_seal,
        completed_eight_result_seal=result_seal,rvh_review=str(review),rvh_review_seal=review_seal,
        contract_sha256=callback_seal,root_refresh_scopes=roots,root_display_names=display,
        targets=COUNTS[0],protected=COUNTS[1],audited=COUNTS[2],command=command,
        timeout_seconds=frozen.TIMEOUT,application_approval=False,launch_approved=False,
        automatic_retry=False,new_RTL_signoff=False,official_denominator_verified=False,pins=pins)
    eight.mask.save(output/PLAN,plan)
    eight.mask.save(output/'status.json',dict(status='PREPARED_NO_DVE',application_approval=False))
    return plan


def evidence_pins(plan):
    base=Path(plan['eight_output']); completed=Path(plan['completed_eight_output'])
    review=Path(plan['rvh_review'])
    runtime=frozen.load_sealed(base/'runtime-plan.json',plan['eight_seal'])
    reference=frozen.load_sealed(completed/'runtime-plan.json',plan['completed_eight_seal'])
    result=frozen.load_sealed(completed/'capture-result.json',plan['completed_eight_result_seal'])
    receipt=frozen.load_sealed(review/'review-receipt.json',backend.RVH_REVIEW_SHA)
    record=frozen.load_sealed(review/'seal.json',plan['rvh_review_seal'])
    require(result.get('status')=='HISTORICAL_EIGHT_POLICY_REPORT_NOT_FINAL_APPROVAL'
            and result.get('config_sha256')==plan['completed_eight_seal'] and
            result.get('final_reset') is True and reference['population']<=plan['population'],
            'Missing terminal eight reference')
    explicit={str(base/'runtime-plan.json'):plan['eight_seal'],
        str(completed/'runtime-plan.json'):plan['completed_eight_seal'],
        str(completed/'capture-result.json'):plan['completed_eight_result_seal'],
        str(review/'seal.json'):plan['rvh_review_seal']}
    return merge_pins(runtime['pins'],reference['pins'],result['files'],receipt['input_pins'],
                      record['output_pins'],explicit)


def read_config(output, seal):
    require(output.parent == frozen.OUT and output.resolve() == output, 'Unsafe nine output')
    plan = frozen.load_sealed(output/PLAN,seal)
    require(plan['schema'] == 'RVH_NINE_POLICY_PREPARED_V1' and plan['output'] == str(output)
            and (plan['targets'],plan['protected'],plan['audited']) == COUNTS
            and plan['timeout_seconds'] == frozen.TIMEOUT and all(plan[k] is False for k in
                ('application_approval','launch_approved','automatic_retry','new_RTL_signoff',
                 'official_denominator_verified')), 'Nine prepared contract differs')
    check_pins(plan['pins'])
    base = Path(plan['eight_output'])
    context, config = eight.read_config(base,plan['eight_seal'])
    runtime = frozen.load_sealed(base/'runtime-plan.json',plan['eight_seal'])
    population_gate(plan['population'],runtime)
    require(plan['admission_sha256'] == runtime['admission_sha256'], 'Admission relabel')
    require(all(plan['pins'].get(p) == h for p,h in config['pins'].items()), 'Missing inherited pins')
    require(all(plan['pins'].get(p) == h for p,h in evidence_pins(plan).items()),
            'Missing completion/native review pins')
    for p in (*dependencies(),output/'runtime-plan.json',output/'rvh9-contract.json'):
        require(plan['pins'].get(str(p)) == frozen.sha(p),'Missing actual dependency pin')
    contract = frozen.load_sealed(output/'rvh9-contract.json',plan['contract_sha256'])
    require(contract['eight_output'] == str(base) and contract['eight_seal'] == plan['eight_seal']
            and contract['population'] == plan['population'] and
            contract['admission_sha256'] == plan['admission_sha256'], 'Callback population differs')
    completed = Path(plan['completed_eight_output'])
    frozen.load_sealed(completed/'capture-result.json',plan['completed_eight_result_seal'])
    with (completed/'summary_raw.csv').open(newline='') as f: rows=list(csv.DictReader(f))
    roots, names, text = root_data(rows,config,contract)
    require((roots,names)==(plan['root_refresh_scopes'],plan['root_display_names']), 'Root selection drift')
    for name,data in payloads(base,contract,plan['contract_sha256'],text).items():
        require(plan['pins'].get(str(output/name)) == frozen.sha(output/name) and
                (output/name).read_bytes()==data, 'Generated helper/facade changed: '+name)
    command = eight.prior.lifecycle.tool.launch_command(config['plan']['tool_identity'],TCL)
    require(plan['command']==command,'Nine launch command changed')
    facade = copy.deepcopy(runtime)
    facade.update(output=str(output),command=command,pins={p:h for p,h in plan['pins'].items()
        if p != str(output/'runtime-plan.json')})
    require(json.loads((output/'runtime-plan.json').read_bytes())==facade,'Eight verifier facade drift')
    derived=copy.deepcopy(config)
    derived.update(output=str(output),command=command,pins=plan['pins'],rvh9_contract=contract,
        root_refresh_scopes=roots,root_display_names=names)
    return context,derived


def verify(output,seal):
    return backend.verify_successor(output,seal,read_config)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','check','verify'))
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--seal')
    for name in ('eight-output','completed-eight-output','rvh-review'):
        parser.add_argument('--'+name,type=Path)
    for name in ('eight-seal','completed-eight-seal','completed-eight-result-seal','rvh-review-seal'):
        parser.add_argument('--'+name)
    parser.add_argument('--population',type=int)
    a=parser.parse_args();out=a.output.absolute()
    values=(a.eight_output,a.eight_seal,a.population,a.completed_eight_output,
        a.completed_eight_seal,a.completed_eight_result_seal,a.rvh_review,a.rvh_review_seal)
    if a.mode=='prepare':
        require(all(v is not None for v in values) and not a.seal,'Explicit sealed inputs/population required')
        prepare(out,a.eight_output.absolute(),a.eight_seal,a.population,a.completed_eight_output.absolute(),
            a.completed_eight_seal,a.completed_eight_result_seal,a.rvh_review.absolute(),a.rvh_review_seal)
        result=dict(status='PREPARED_NO_DVE',seal=frozen.sha(out/PLAN))
    else:
        require(a.seal and all(v is None for v in values),'Sealed output only')
        result=verify(out,a.seal) if a.mode=='verify' else dict(status='CHECKED_NO_DVE',
            population=read_config(out,a.seal)[1]['population'])
    print(json.dumps(result))


if __name__=='__main__':main()
