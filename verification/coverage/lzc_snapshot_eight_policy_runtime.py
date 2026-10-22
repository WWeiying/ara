"""Fresh explicit-population eight-policy successor; preparation never runs EDA."""
import argparse
import copy
import csv
import json
from pathlib import Path
import re

import lzc_selector_native_seven_policy_runtime as prior
import prepare_mask_store_snapshot_cond24 as mask
import split_reviewed_native_metrics as metric

six, seven, frozen = prior.six, prior.seven, prior.frozen
require = prior.require
HERE = Path(__file__).resolve().parent
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_lzc_snapshot_eight_policy_runtime.py')
TCL = SCRIPT.with_suffix('.tcl')
SCOPE_FIX = HERE/'lzc_selector_native_seven_policy_runtime_v3.tcl'
SCOPE_SHA = '5ff065327cde3a972442379e0a6b7f8ae687e69b68b7bd0fe9db95169d07e7b9'
MASK_EL = HERE/'waivers/mask_store_snapshot.el'
MASK_SHA = 'c11b89f8ae115a50c83bd409d57d003c768991ae589656c021c5209cdb9f44a8'
REVIEW = HERE/'waivers/mask_store_snapshot_review.json'
REVIEW_SHA = '5f1cfac6fd12e96a63cd3755c0587b6cf64df13eaad3d5d9481172fe37550ec4'
CAPTURE = frozen.OUT/'mask-store-cond24-native-prepared-agent-725-20261006-01'
SOURCE_PROOF = frozen.OUT/'lzc-selector-native-cond60-four-state-review-723-20261006-01'
STAGES = prior.STAGES


def scope_fix():
    require(frozen.sha(SCOPE_FIX) == SCOPE_SHA, 'Approved immutable scope fix differs')
    old = b'    global env seven_rows seven_target_positions seven_before_complete\n'
    new = b'    global env seven_rows seven_target_positions seven_before_complete lpa_binding lpa_expected\n'
    original = prior.TCL.read_bytes()
    require(original.count(old) == 1 and SCOPE_FIX.read_bytes() == original.replace(old,new,1),
            'Scope successor has changes beyond approved declaration')


def route(raw, sources):
    """Typed routing for exports; existing semantic validators bind every record."""
    owners = {}
    for name, source in sources.items():
        for key, _ in metric.blocks(source):
            require(key not in owners or owners[key] == name, 'Ambiguous metric owner')
            owners[key] = name
    result = {name:[] for name in sources}
    for key, block in metric.blocks(raw):
        require(key in owners, 'Unknown scope/module/metric/type')
        result[owners[key]].append(block)
    require(all(result.values()), 'Missing policy metric stream')
    return {name:b''.join(parts) for name,parts in result.items()}


def split_bind(raw, config, sources, candidates, states=None):
    parts = route(raw,sources)
    for name in ('lzc','snapshot'):
        actual = mask.parse_records(parts[name].decode('ascii'))
        expected = mask.parse_records(sources[name].decode('ascii'))
        require(sorted(actual,key=str) == sorted(expected,key=str), 'Observed native condition identities differ: '+name)
        if name == 'snapshot':
            mask.bind(actual,candidates)
    return frozen.bindings(parts['six'],config,states)


def snapshot_binding(config, bitmap):
    require(frozen.sha(MASK_EL) == MASK_SHA and frozen.sha(REVIEW) == REVIEW_SHA, 'Scoped review bytes differ')
    review = json.loads(REVIEW.read_bytes())
    require(review['qualified_for_scoped_exclusion'] is True and review['aggregate_application'] is False
            and review['target_count'] == 24 and review['branch_hold_count'] == 8 and review['port8_protected'] is True,
            'Scoped24 approval limits differ')
    prepared = mask.read_config(CAPTURE, '79d3fab018b585106a88ff50cfa6bf4ba1a143051422a19598602a03fa99c7b5')
    proof = json.loads(mask.PROOF.read_bytes())
    require(frozen.sha(mask.PROOF) == mask.PROOF_SHA and len(proof['pins']) == 54, 'Source proof differs')
    for path, expected in proof['pins'].items():
        require(frozen.sha(path) == expected, 'Source proof54 pin differs')
    design = seven.proof.Design(Path(config['inputs'][0]))
    candidates,_ = mask.proof.compiled_points(design,bitmap)
    selected,held = mask.split_candidates(candidates)
    for row in selected:
        row['module_checksum'] = design.hierarchy[row['scope']].get('chksum')
    require(selected == prepared['candidates'], 'Latest source/shape/zero24 differs')
    native = mask.parse_records(MASK_EL.read_text());mask.bind(native,selected)
    require(native == mask.parse_records((CAPTURE/'first.el').read_text()), 'Reviewed native24/capture differs')
    guards=set(); targets=set()
    for name,g in config['groups'].items():
        if name == 'operand':
            targets.update((r['scope'],'branch',r['raw_index']) for r in g['qualified'])
            for scope,tab in g['plan']['scopes'].items():
                guards.update((scope,'branch',r['raw_index']) for r in tab['protected'])
        else:
            for scope,tab in g['plan']['scopes'].items():
                for row in tab['branch']:
                    (targets if row['target'] else guards).add((scope,'branch',row['point']['raw_index']))
    kept={mask.coordinate(r) for r in prepared['preserved_protected']}
    require(len(targets)==5808 and len(guards)==13562 and not {mask.coordinate(r) for r in selected}&targets
            and not kept&targets and len(kept&guards)==264 and
            len(kept-guards)==72 and all(k[1]=='cond' for k in kept-guards) and
            {mask.coordinate(r) for r in held} <= guards, 'Cross-policy protection/dedup differs')
    return prepared,selected


def dependencies():
    return (SCRIPT,TCL,TEST,SCOPE_FIX,Path(prior.__file__).resolve(),
        prior.TCL,HERE/'run_lzc_selector_native_seven_policy.py',
        HERE/'run_lzc_snapshot_eight_policy.py',HERE/'test_run_lzc_snapshot_eight_policy.py',
        Path(metric.__file__).resolve(),HERE/'test_split_reviewed_native_metrics.py',
        Path(mask.__file__).resolve(),HERE/'capture_lzc_batch.tcl')


def lzc_binding(plan, config, bitmap, snapshot):
    review=frozen.load_sealed(SOURCE_PROOF/'review.json',seven.PROOF_SEAL)
    require(plan['source_proof']==str(SOURCE_PROOF/'review.json')
            and plan['source_proof_sha256']==seven.PROOF_SEAL
            and plan['exact_lzc_protection_rows']==review['exact_protection_rows']
            and plan['condition_native_records']==[r['native_record'] for r in review['candidates']],
            'Exact LZC native proof/protection inventory differs')
    require(not {r['scope'] for r in review['exact_protection_rows']} &
            {r['scope'] for r in snapshot['preserved_protected']},
            'LZC/snapshot cross-protection overlap requires separate review')
    seven.latest_binding(review,bitmap,seven.proof.Design(Path(config['inputs'][0])))


def prepare(output, six_output, six_seal, plan_output, plan_seal, accept_contract=False):
    require(accept_contract, 'Explicit inherited LZC X/0 source contract acceptance required')
    require(output.parent==frozen.OUT and output.resolve()==output and not output.exists(), 'Fresh output required')
    scope_fix()
    _,config=six.read_config(six_output,six_seal)
    plan=frozen.load_sealed(plan_output/'application-plan.json',plan_seal)
    require(type(config['population']) is int and config['population']>=725, 'Only explicit725-or-later admitted population')
    prior.contract(plan,config)
    require(plan['six_config']==str(six_output/'config.json') and plan['six_config_sha256']==six_seal,
            'Exact six/seven input links differ')
    bitmap=json.loads((Path(config['admitted_base'])/'combined-bits.json').read_bytes())
    snapshot,candidates=snapshot_binding(config,bitmap)
    lzc_binding(plan,config,bitmap,snapshot)
    sources=dict(six=(six_output/'combined.el').read_bytes(),
                 lzc=(SOURCE_PROOF/'candidate60.el').read_bytes(),snapshot=MASK_EL.read_bytes())
    combined=b''.join(sources.values())
    require(metric.split_exact(combined,sources)==sources, 'Proposal metric partition differs')
    split_bind(combined,config,sources,candidates)
    pins=dict(config['pins'])
    for group in (plan['pins'],snapshot['pins']):
        for path,sha in group.items():
            require(path not in pins or pins[path]==sha, 'Inherited pin conflict');pins[path]=sha
    for path in (*dependencies(),MASK_EL,REVIEW,six_output/'config.json',plan_output/'application-plan.json'):
        actual=frozen.sha(path)
        require(str(path) not in pins or pins[str(path)]==actual, 'Runtime dependency drift');pins[str(path)]=actual
    for path,sha in pins.items():require(frozen.sha(path)==sha, 'Runtime input drift: '+path)
    output.mkdir()
    for group in (*frozen.GROUPS,'lzc','snapshot'):(output/group).mkdir()
    for name in prior.HELPERS:
        source=six_output/name
        require(config['pins'].get(str(source))==frozen.sha(source), 'Unpinned six helper')
        (output/name).write_bytes(source.read_bytes())
    (output/'six-library.tcl').write_text(prior.six_library())
    (output/'seven-selection.tcl').write_text(prior.selection_text(plan))
    (output/'snapshot-selection.tcl').write_text(mask.native.group_script(snapshot['groups']))
    (output/'combined-eight.el').write_bytes(combined)
    (output/'config.json').write_bytes((six_output/'config.json').read_bytes())
    for f in output.iterdir():
        if f.is_file():pins[str(f)]=frozen.sha(f)
    runtime=dict(schema='lzc-snapshot-eight-explicit-population-v1', output=str(output),
        six_output=str(six_output),six_config_sha256=six_seal,seven_output=str(plan_output),seven_plan_sha256=plan_seal,
        population=config['population'],admission_sha256=config['admission_manifest_sha256'],
        targets=5892,protected=17774,audited=23666,stages=list(STAGES),
        command=prior.lifecycle.tool.launch_command(config['plan']['tool_identity'],TCL),
        timeout_seconds=frozen.TIMEOUT,approved_scope_fix_sha256=SCOPE_SHA,
        mask_review_sha256=REVIEW_SHA,mask_native_sha256=MASK_SHA,
        snapshot_candidates=candidates,snapshot_groups=snapshot['groups'],
        snapshot_branch_hold=8,lzc_branch_hold=60,op16='HOLD',
        padding_x0_contract_accepted=True,native_X_semantics_measured=False,four_state_initialization_qualified=False,
        launch_approved=False,application_approval=False,automatic_retry=False,official_denominator_verified=False,pins=pins)
    # Use a native JSON writer; never serialize an EL string with frozen.write.
    mask.save(output/'runtime-plan.json',runtime)
    mask.save(output/'runtime-plan.sha256.json',{str(output/'runtime-plan.json'):frozen.sha(output/'runtime-plan.json')})
    mask.save(output/'status.json',dict(status='PREPARED_NO_DVE',application_approval=False))
    return runtime


def read_config(output, seal):
    runtime=frozen.load_sealed(output/'runtime-plan.json',seal);scope_fix()
    require(runtime['schema']=='lzc-snapshot-eight-explicit-population-v1' and runtime['output']==str(output)
            and (runtime['targets'],runtime['protected'],runtime['audited'])==(5892,17774,23666)
            and runtime['stages']==list(STAGES) and runtime['timeout_seconds']==frozen.TIMEOUT
            and runtime['approved_scope_fix_sha256']==SCOPE_SHA and runtime['mask_review_sha256']==REVIEW_SHA
            and runtime['mask_native_sha256']==MASK_SHA and runtime['snapshot_branch_hold']==8
            and runtime['lzc_branch_hold']==60 and runtime['op16']=='HOLD'
            and runtime['padding_x0_contract_accepted'] is True
            and all(runtime[k] is False for k in ('launch_approved','application_approval','automatic_retry',
                'official_denominator_verified','native_X_semantics_measured','four_state_initialization_qualified')),
            'Eight runtime contract differs')
    for path,sha in runtime['pins'].items():require(frozen.sha(path)==sha, 'Eight pin drift: '+path)
    six_output=Path(runtime['six_output']);plan_output=Path(runtime['seven_output'])
    context,config=six.read_config(six_output,runtime['six_config_sha256'])
    plan=frozen.load_sealed(plan_output/'application-plan.json',runtime['seven_plan_sha256']);prior.contract(plan,config)
    require(config['population']==runtime['population']>=725 and
            config['admission_manifest_sha256']==runtime['admission_sha256'] and
            plan['six_config']==str(six_output/'config.json') and plan['six_config_sha256']==runtime['six_config_sha256'],
            'Population/plan link differs; relabel forbidden')
    require(all(runtime['pins'].get(k)==v for k,v in dict(config['pins'],**plan['pins']).items()), 'Mandatory inherited pins omitted')
    bitmap=json.loads((Path(config['admitted_base'])/'combined-bits.json').read_bytes())
    snapshot,candidates=snapshot_binding(config,bitmap)
    lzc_binding(plan,config,bitmap,snapshot)
    require(all(runtime['pins'].get(k)==v for k,v in snapshot['pins'].items()),
            'Mandatory snapshot capture pins omitted')
    require(runtime['snapshot_candidates']==candidates and runtime['snapshot_groups']==snapshot['groups'], 'Snapshot binding differs')
    for f in (*dependencies(),MASK_EL,REVIEW,six_output/'config.json',plan_output/'application-plan.json',
              output/'config.json',output/'six-library.tcl',output/'seven-selection.tcl',
              output/'snapshot-selection.tcl',output/'combined-eight.el',*(output/n for n in prior.HELPERS)):
        require(runtime['pins'].get(str(f))==frozen.sha(f), 'Mandatory dependency missing')
    for n in prior.HELPERS:
        require((output/n).read_bytes()==(six_output/n).read_bytes(), 'Six helper changed')
    require((output/'config.json').read_bytes()==(six_output/'config.json').read_bytes()
            and (output/'six-library.tcl').read_text()==prior.six_library()
            and (output/'seven-selection.tcl').read_text()==prior.selection_text(plan)
            and (output/'snapshot-selection.tcl').read_text()==mask.native.group_script(snapshot['groups']), 'Generated facade/selection differs')
    sources=dict(six=(six_output/'combined.el').read_bytes(),lzc=(SOURCE_PROOF/'candidate60.el').read_bytes(),snapshot=MASK_EL.read_bytes())
    require(metric.split_exact((output/'combined-eight.el').read_bytes(),sources)==sources, 'Proposal source bytes differ')
    require(runtime['command']==prior.lifecycle.tool.launch_command(config['plan']['tool_identity'],TCL), 'Runtime command differs')
    derived=copy.deepcopy(config);derived.update(output=str(output),command=runtime['command'],pins=runtime['pins'])
    return context,derived


def verify(output, seal):
    context,config=read_config(output,seal);runtime=frozen.load_sealed(output/'runtime-plan.json',seal)
    plan=frozen.load_sealed(Path(runtime['seven_output'])/'application-plan.json',runtime['seven_plan_sha256'])
    sources=dict(six=(Path(runtime['six_output'])/'combined.el').read_bytes(),lzc=(SOURCE_PROOF/'candidate60.el').read_bytes(),snapshot=MASK_EL.read_bytes())
    condition_scopes={r['scope'] for r in plan['condition_native_records']}|{r['scope'] for r in runtime['snapshot_candidates']}
    def bind(raw,cfg,states=None):return split_bind(raw,cfg,sources,runtime['snapshot_candidates'],states)
    namespace=dict(context.namespace(),bindings=bind,
        log_adapter=lambda p:(p/'DVEfiles/dve_gui.log').read_text().splitlines().count('SIX_POPULATION_SELECTION_ADAPTER_INSTALLED')==1)
    result=prior.seven_verifier(namespace,lambda s,m,a:prior.change_allowed(s,m,a,condition_scopes))(output,config)
    log=(output/'DVEfiles/dve_gui.log').read_text();require(not re.search(r'(SEVEN|EIGHT)_(ERROR|FAILED)',log),'Eight session failed')
    extra=[output/'runtime-plan.json',output/'combined-eight.el',output/'snapshot-selection.tcl']
    for stage in STAGES:
        active=stage in ('selected','reloaded','after-root')
        path=output/'lzc'/('states_'+stage+'.tsv')
        require(path.is_file() and not path.is_symlink(),'Aliased/missing LZC states')
        prior.read_lzc_states(path,plan,active);extra.append(path)
        path=output/'snapshot'/('states_'+stage+'.csv')
        require(path.is_file() and not path.is_symlink(),'Aliased/missing snapshot states')
        with path.open(newline='') as f:
            reader=csv.DictReader(f);rows=list(reader);require(reader.fieldnames==mask.native.AUDIT_COLUMNS,'Snapshot schema differs')
        wanted=[dict(zip(mask.native.AUDIT_COLUMNS,[stage,g['scope'],g['expression'],' '.join(g['names']),
            ' '.join(g['targets']),' '.join(g['retained']),str(len(g['targets']) if active else 0),'0'])) for g in runtime['snapshot_groups']]
        require(rows==wanted,'Snapshot96 target/protect state differs');extra.append(path)
        for marker in ('SEVEN_LZC_AUDIT %s 4200'%stage,'SEVEN_FULL_AUDIT %s 23570'%stage,
                       'EIGHT_SNAPSHOT_AUDIT %s 96'%stage,'EIGHT_FULL_AUDIT %s 23666'%stage):
            require(log.splitlines().count(marker)==1,'Missing complete stage: '+marker)
    for group in frozen.GROUPS:
        f=output/group/'states_after-root.tsv';require(f.read_bytes()==(output/group/'states_selected.tsv').read_bytes(),'Six after-root drift');extra.append(f)
    for n in ('reloaded.el','after-root.el'):
        f=output/n;require(f.read_bytes()==(output/'applied.el').read_bytes(),'Actual combined reload differs');bind(f.read_bytes(),config);extra.append(f)
    f=output/'session-final-empty.el';require(f.read_bytes()==b'','Session final not empty');extra.append(f)
    for marker in ('EIGHT_RUNTIME_INSTALLED','EIGHT_ACTUAL_RELOAD_EXACT5892','EIGHT_DONE_EXACT5892'):
        require(log.splitlines().count(marker)==1,'Missing eight completion')
    result.update(status='HISTORICAL_EIGHT_POLICY_REPORT_NOT_FINAL_APPROVAL',records=5892,protected=17774,
        audited=23666,state_checks=23666*len(STAGES),application_approval=False,actual_combined_reload_verified=True,
        snapshot_branch_hold=8,lzc_branch_hold=60,op16='HOLD',historical_percentages_inherited=False,
        admission_manifest_sha256=runtime['admission_sha256'],native_X_semantics_measured=False,four_state_initialization_qualified=False)
    result['files'].update({str(p):frozen.sha(p) for p in extra})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','check','verify'))
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--seal')
    parser.add_argument('--six-output',type=Path);parser.add_argument('--six-seal')
    parser.add_argument('--seven-output',type=Path);parser.add_argument('--seven-seal')
    parser.add_argument('--accept-padding-x0-contract',action='store_true')
    a=parser.parse_args();out=a.output.absolute()
    if a.mode=='prepare':
        require(all((a.six_output,a.six_seal,a.seven_output,a.seven_seal,a.accept_padding_x0_contract)) and not a.seal,'Explicit sealed sources required')
        prepare(out,a.six_output.absolute(),a.six_seal,a.seven_output.absolute(),a.seven_seal,True)
        print(json.dumps(dict(status='PREPARED_NO_DVE',seal=frozen.sha(out/'runtime-plan.json'))))
    else:
        require(a.seal and not any((a.six_output,a.six_seal,a.seven_output,a.seven_seal,a.accept_padding_x0_contract)),'Sealed output only')
        result=verify(out,a.seal) if a.mode=='verify' else dict(status='CHECKED_NO_DVE',population=read_config(out,a.seal)[1]['population'])
        print(json.dumps(result))


if __name__=='__main__':main()
