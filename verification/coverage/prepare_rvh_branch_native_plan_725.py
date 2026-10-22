"""Prepare exact RVH branch selectors for existing native primitives; no EDA."""
import argparse
import json
from pathlib import Path

import rvh_direct_native_candidates_725 as static

HERE = Path(__file__).resolve().parent
STATIC = static.OUT / 'rvh-direct-native-candidates-agent-725-20261006-01'
STATIC_SEAL = 'd585c52ecc3611b86a3044dfd1164f8dcafcc8c37ad0ae0e73a8a2a17f268f9c'
PILOT = static.CORE + '.issue_stage_i.i_issue_read_operands'
require, digest = static.require, static.digest
PRIMITIVES = ('capture_operand_debug.tcl', 'capture_operand_debug_branch_v2.tcl',
              'capture_operand_debug.py', 'capture_operand_debug_branch.py',
              'capture_operand_debug_branch_v3.py', 'capture_operand_debug_branch_v4.py',
              'capture_operand_debug_branch_v5.py')


def selector(group, row):
    p = row['point']
    require(not row['hit725'] and p['file_id'] == group['source']['file_id']
            and p['attributes'] == group['group'], 'Target source/group binding differs')
    require(static.true_pattern(p['native_vector']['vector'], group['direct_expressions']),
            'Not an exact direct RVH true pattern')
    return dict(scope=group['scope'], compiled_coordinate=p['native_id']+','+p['vector'],
        raw_index=p['raw_index'], file_id=p['file_id'], source=group['source'],
        source_sha256=group['source_sha256'], module_checksum=group['module_checksum'],
        metric_checksum=group['metric_checksum'], group_checksum=p['attributes']['chksum'],
        generate_info=p['attributes'].get('generate_info'),
        compiled_expressions=p['expressions'], compiled_pattern=p['native_vector']['vector'],
        direct_rvh_expressions=group['direct_expressions'],
        expected_EL_group_expression=p['expressions'][0]['exprstr'],
        actual_GUI_meta=None, actual_GUI_path=None, actual_native_signature=None,
        identity_status='PENDING_MEASURED_NATIVE_BINDING_NOT_XML_APPROVAL')


def scope_rows(evidence):
    result = {}
    for group in evidence['groups']:
        scope = group['scope']
        rows = result.setdefault(scope, {})
        for key in ('targets', 'protected'):
            for row in group[key]:
                p = row['point']; index = p['raw_index']
                require(index not in rows, 'Duplicate compiled position')
                rows[index] = dict(point=p, coordinate=p['native_id']+','+p['vector'],
                    target=key == 'targets', module_checksum=group['module_checksum'],
                    metric_checksum=group['metric_checksum'])
    for outside in evidence['protected_outside_matching_groups']:
        scope = outside['scope']
        result.setdefault(scope, {})
        sample = next(iter(result[scope].values()), {'module_checksum':None,
                                                     'metric_checksum':outside['metric_checksum']})
        for p in outside['protected_outside_matching_groups']:
            require(p['raw_index'] not in result[scope], 'Overlapping outside protection')
            result[scope][p['raw_index']] = dict(point=p, coordinate=p['native_id']+','+p['vector'],
                target=False, module_checksum=sample['module_checksum'], metric_checksum=sample['metric_checksum'])
        require(set(result[scope]) == set(range(outside['metric_width'])), 'Incomplete full-scope branch protection')
    return {s:{'branch':[rows[i] for i in sorted(rows)]} for s,rows in sorted(result.items())}


def make_plan(evidence):
    require(evidence['counts']['targets'] == 247 and evidence['counts']['protected'] == 1126
            and len(evidence['groups']) == 38 and not evidence['native_identity_qualified'], 'Wrong static population')
    selectors = [dict(scope=g['scope'], group=g['group'],
                      selectors=[selector(g,r) for r in g['targets']], protected=g['protected'])
                 for g in evidence['groups']]
    full = scope_rows(evidence)
    require(PILOT in full, 'Reviewed pilot missing')
    pilot = {PILOT:full[PILOT]}
    pilot_rows = pilot[PILOT]['branch']
    require(len(pilot_rows) == 100 and sum(r['target'] for r in pilot_rows) == 3, 'Pilot identity differs')
    full_rows = [r for m in full.values() for r in m['branch']]
    require(len(full_rows) == 1780 and sum(r['target'] for r in full_rows) == 247, 'Full protection differs')
    return dict(schema='RVH725_BRANCH_NATIVE_PRIMITIVE_PLAN_V1', status='PREPARED_REVIEW_ONLY_NO_CAPTURE',
        group_selectors=selectors, full_scopes=full, pilot_scopes=pilot,
        pilot_counts=dict(scopes=1, targets=3, audited_branch_positions=100, protected=97),
        full_counts=dict(scopes=14, target_scopes=10, protection_only_scopes=4,
                         groups=38, targets=247, audited_branch_positions=1780,
                         protected=1533, original_local_protected=1126, outside_protected=407),
        workflow=[
            'Parent review before any session. First readonly full100 GUI branch inventory with column action then expand.',
            'Match complete compiled coordinate set against measured ItemID/leaf meta/path; unknown/missing IDs HOLD, no rename or extrapolation.',
            'Pilot3 temporary singletons only after native map and full100 before-empty gate; verify exact module/group checksum and EL expression.',
            'Each singleton requires exact one-position difference, protected97 unchanged, save/reset/reload native fields/signature parity and final empty.',
            'Full247 remains locked until independently sealed pilot result and separate parent authorization; full1780 same-session protection mandatory.'],
        audit_stages=['before','selected','reset','reloaded','final'],
        pilot_budget_seconds=1800, full_budget_seconds=10500,
        budget_basis='Pilot100 positions is bounded; full budget is ceiling only, estimate/review after pilot timing. No retry.',
        existing_native_primitives=list(PRIMITIVES),
        compatibility='Tcl8.4 list-safe eval; branch-only expanded metadata incl MISSING_ELSE/MISSING_DEFAULT; no builtin rename',
        primitive_adaptation_required=['Use RVH review annotation, not instrumentation/noninterference annotation',
            'Existing native ID key equality is a rejection gate, not evidence until actual GUI inventory',
            'Retain generate_info per exact group and every measured native field; no fixed requester_index whitelist',
            'Compare two saved complete records with signature parity; no assumed multi-expression native signature'],
        full_expansion_authorized=False, launch_approved=False, native_qualified=False,
        application_approval=False, EL_generated=False, processor_application=False,
        untouched_metrics=['line','cond','fsm','tgl'], source_only_hold=evidence['source_only_hold'])


def selection_payload(scopes):
    # Data-only Tcl: no GUI commands, no targets armed before measured binding.
    lines=['# Tcl8.4 data only. Native binding and parent approval required.',
           'set rvh_native_binding_gate 0', 'set dbg_scopes {'+' '.join('{'+s+'}' for s in scopes)+'}']
    keys=[]; disabled=[]
    for scope,m in scopes.items():
        coords=[r['coordinate'] for r in m['branch']]
        require(len(coords)==len(set(coords)), 'Duplicate selector key')
        keys.append('{'+scope+'|branch} {'+' '.join(coords)+'}')
        disabled.append('{'+scope+'|branch} {}')
    return '\n'.join(lines+['array set dbg_keys {\n'+'\n'.join(keys)+'\n}',
                           'array set dbg_targets {\n'+'\n'.join(disabled)+'\n}'])+'\n'


def prepare(output):
    require(output.parent == static.OUT and output.resolve() == output and not output.exists(), 'Fresh output required')
    seal_path=STATIC/'seal.json'
    require(digest(seal_path)==STATIC_SEAL, 'Wrong static seal')
    old=json.loads(seal_path.read_bytes())
    pins={**old['input_pins'],**old['output_pins'],str(seal_path):STATIC_SEAL}
    for p,h in pins.items(): require(digest(p)==h, 'Static input drift: '+p)
    evidence=json.loads((STATIC/'inventory.json').read_bytes())
    plan=make_plan(evidence)
    design_identity=static.Design(static.BUILD/'sim/simv.vdb')
    for scope, metrics in plan['full_scopes'].items():
        module_checksum=design_identity.hierarchy[scope].get('chksum')
        require(bool(module_checksum), 'Missing protected module identity')
        require(design_identity.definition(scope,'branch').get('chksum')==metrics['branch'][0]['metric_checksum'],
                'Protected compiled metric binding differs')
        for row in metrics['branch']:
            require(row['module_checksum'] in (None,module_checksum), 'Module identity mismatch')
            row['module_checksum']=module_checksum
    sample=Path((static.BASE/'combined-inputs.txt').read_text().splitlines()[-1])
    design=static.BUILD/'sim/simv.vdb'
    require(sample.is_dir() and len(list((sample/'snps/coverage/db/testdata').iterdir()))==1, 'Wrong single admitted sample')
    for p in sorted(sample.rglob('*')):
        if p.is_file(): pins[str(p)]=digest(p)
    for p in [Path(__file__).resolve(),HERE/'test_prepare_rvh_branch_native_plan_725.py']+[HERE/n for n in PRIMITIVES]:
        pins[str(p)]=digest(p)
    plan.update(static_seal=STATIC_SEAL, admission_seal=static.BASE_SHA,
                design_vdb=str(design), selected_admitted_test_vdb=str(sample),
                sample_role='Native measurement only; no population report or application',input_pins=pins)
    for p,h in pins.items(): require(digest(p)==h, 'Final input drift: '+p)
    output.mkdir()
    paths={'native-plan.json':json.dumps(plan,indent=2,sort_keys=True)+'\n',
           'pilot-discovery-selection.tcl':selection_payload(plan['pilot_scopes']),
           'full-discovery-selection.tcl':selection_payload(plan['full_scopes'])}
    for name,text in paths.items(): (output/name).write_text(text)
    receipt=dict(input_pins=pins,output_pins={str(output/n):digest(output/n) for n in paths})
    (output/'seal.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(output=str(output),seal=digest(output/'seal.json'),pins=len(pins),pilot=plan['pilot_counts'],full=plan['full_counts'])))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','verify'));parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seal');args=parser.parse_args();out=args.output.absolute()
    if args.mode=='prepare':
        require(args.seal is None,'No guessed seal');prepare(out)
    else:
        require(args.seal and digest(out/'seal.json')==args.seal,'Wrong plan seal')
        seal=json.loads((out/'seal.json').read_bytes())
        for p,h in {**seal['input_pins'],**seal['output_pins']}.items(): require(digest(p)==h,'Plan drift: '+p)
        print('VERIFY_PASS RVH_NATIVE_PLAN_ONLY_NO_LAUNCH')


if __name__=='__main__': main()
