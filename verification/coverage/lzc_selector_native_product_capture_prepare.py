#!/usr/bin/env python3
"""Prepare product singleton signature capture contracts; never launch/apply EL."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

from lzc_selector_native_prepare import require, sha, write
import lzc_selector_native_product_prepare as product
from lzc_selector_native_product_inventory import bind, decode_lines

HERE = Path(__file__).resolve().parent


def protection_rows(inventory):
    rows = []
    for child in inventory['rows']:
        scope = child['scope']
        for native in child['branch_native_rows']:
            rows.append(dict(scope=scope, metric='branch', native_id=native[2],
                             vector=native[3], expression=None))
        for condition in child['conditions']:
            for vector in condition['vectors']:
                rows.append(dict(scope=scope, metric='cond', native_id=None,
                                 expression=condition['expression'], vector=vector))
    keys = [(r['scope'], r['metric'], r['native_id'], r['expression'], r['vector']) for r in rows]
    require(len(keys) == len(set(keys)) == 4200, 'Exact complete native protection inventory required')
    return rows


def resolve_branch(candidate, observations, rows):
    """Gate before exclusion: independently observed full parent text, not XML ID."""
    require(candidate['metric'] == 'branch', 'Branch candidate required')
    product.eligible(candidate['xml_provenance'], candidate['parameters']['WIDTH'], 'branch')
    matches = [r for r in observations if r.get('scope') == candidate['scope'] and
               r.get('expression') == candidate['expression']]
    require(len(matches) == 1, 'Unique exact native branch expression binding required before capture')
    observed = matches[0]
    require(isinstance(observed.get('native_id'), str) and observed['native_id'].isdigit() and
            observed.get('expression_source') == 'native_parent_text' and
            observed.get('module_checksum') == candidate['module_checksum'] and
            observed.get('arms') == ['0', '1'] and
            observed.get('raw_parent_text') == candidate['expression'] and
            observed.get('parent_path') == 'Item' + observed.get('native_id', ''),
            'Native branch parent provenance differs')
    positions = [i for i, row in enumerate(rows) if row['scope'] == candidate['scope'] and
                 row['metric'] == 'branch' and row['native_id'] == observed['native_id'] and row['vector'] == '0']
    require(len(positions) == 1, 'Resolved native branch not in independently discovered inventory')
    return positions[0], observed['native_id']


def condition_position(candidate, rows):
    require(candidate['metric'] == 'cond', 'Condition candidate required')
    product.eligible(candidate['xml_provenance'], candidate['parameters']['WIDTH'], 'cond')
    positions = [i for i, row in enumerate(rows) if row['scope'] == candidate['scope'] and
                 row['metric'] == 'cond' and row['expression'] == candidate['expression'] and row['vector'] == '1']
    require(len(positions) == 1, 'Exact discovered ternary true vector missing/ambiguous')
    return positions[0]


def bind_signature(first, second, candidate, rows, branch_observations=()):
    require(isinstance(first, bytes) and first and first == second, 'Saved/reloaded native bytes must match exactly')
    text = first.decode('ascii')
    if candidate['metric'] == 'cond':
        position = condition_position(candidate, rows)
        record = product.validate_condition_singleton(text, candidate)
    else:
        position, identity = resolve_branch(candidate, branch_observations, rows)
        record = product.validate_branch_singleton(text, candidate)
        require(record['native_id'] == identity, 'Saved native branch differs from independently resolved ID')
    return dict(position=position, native_record=record, native_id_source='Exact saved DVE singleton signature',
                signature_bound=True, qualification_complete=False, application_approval=False)


def verify_states(actual, rows, active):
    require(active == -1 or 0 <= active < len(rows), 'Invalid protected active position')
    wanted = [dict(position=str(i), scope=r['scope'], metric=r['metric'],
                   native_id=r['native_id'] or '', expression=r['expression'] or '',
                   vector=r['vector'], excluded=str(int(i == active))) for i, r in enumerate(rows)]
    require(actual == wanted, 'Complete global native protection state differs')


def verify_case(case, plan, key):
    require(case.is_relative_to(product.OUT), 'Capture evidence outside integration workspace')
    product.check_pins(plan['pins'])
    targets = [r for r in plan['targets'] if r['candidate']['key'] == key]
    require(len(targets) == 1, 'Unplanned candidate')
    candidate = targets[0]['candidate']
    status = json.loads((case / 'capture-status.json').read_bytes())
    require(status['status'] == 'CAPTURE_COMPLETE_PENDING_OFFLINE_VERIFICATION' and
            status['candidate_key'] == key and status['plan_sha256'] == sha(Path(plan['plan_path'])) and
            status['exclusion_application'] is False, 'Exact independently sealed completed capture required')
    product.check_pins(status['artifacts'])
    required = {'first.el', 'second.el', 'initial-empty.el', 'reset-empty.el', 'final-empty.el',
                'before.tsv', 'selected.tsv', 'reset.tsv', 'reloaded.tsv', 'final.tsv'}
    if candidate['metric'] == 'branch':
        required.add('branch-preflight.json')
    require(all(str(case / name) in status['artifacts'] for name in required), 'Unsealed/missing capture artifacts')
    observations = (json.loads((case / 'branch-preflight.json').read_bytes()) if candidate['metric'] == 'branch' else [])
    result = bind_signature((case / 'first.el').read_bytes(), (case / 'second.el').read_bytes(),
                            candidate, plan['protection_rows'], observations)
    fields = ['position', 'scope', 'metric', 'native_id', 'expression', 'vector', 'excluded']
    for stage, active in (('before', -1), ('selected', result['position']), ('reset', -1),
                          ('reloaded', result['position']), ('final', -1)):
        with (case / (stage + '.tsv')).open() as stream:
            reader = csv.DictReader(stream, delimiter='\t')
            require(reader.fieldnames == fields, 'Unexpected global protection audit schema')
            verify_states(list(reader), plan['protection_rows'], active)
    for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el'):
        require((case / name).read_bytes() == b'', 'Global residual exclusions')
    require({p.name for p in case.glob('*.el')} == {'first.el', 'second.el', 'initial-empty.el',
                                                  'reset-empty.el', 'final-empty.el'}, 'Unexpected EL artifact')
    result.update(status='PRODUCT_SINGLETON_SIGNATURE_AND_ROUNDTRIP_VERIFIED_NOT_WAIVER_APPROVAL',
                  candidate_key=key, global_native_position_checks=5 * len(plan['protection_rows']),
                  reset_and_final_empty=True, protected_false_and_other_visible_native_rows=True,
                  op16_hidden_state_not_qualified=True, native_signature_qualification_complete=False)
    return result


def prepare(prepared, discovery, output):
    require(prepared.parent == discovery.parent == output.parent == product.OUT and not output.exists(),
            'Fresh direct verification/out prepare directory required')
    static_path = prepared / 'product-plan.json'
    static = json.loads(static_path.read_bytes())
    product.check_pins(json.loads((prepared / 'product-plan.sha256.json').read_bytes()))
    product.check_pins(static['pins'])
    inv_path = discovery / 'native-inventory-parent-verified.json'
    inventory = json.loads(inv_path.read_bytes())
    product.check_pins(json.loads(inv_path.with_suffix('.sha256.json').read_bytes()))
    product.check_pins(inventory['input_sha256'])
    status = json.loads((discovery / 'discovery-status.json').read_bytes())
    product.check_pins(status['artifacts'])
    require(status['status'] == 'READONLY_DISCOVERY_COMPLETE_PENDING_OFFLINE_BINDING' and
            status['excludes'] is False and status['captures'] is False, 'Only completed read-only discovery')
    require(inventory['status'] == 'READONLY_NATIVE_INVENTORY_VERIFIED_NOT_CAPTURE_OR_APPLICATION_APPROVAL' and
            inventory['children'] == 36 and inventory['native_positions'] == 4200 and
            inventory['native_signature_qualification_complete'] is False and
            inventory['exclusions_applied'] is False and inventory['application_approval'] is False,
            'Inventory must not be a waiver or signature qualification')
    actual = bind(decode_lines((discovery / 'native-inventory.tcllist').read_bytes().decode('latin1')), static)
    require(actual == inventory['rows'], 'Independent parent inventory differs from raw native evidence')
    rows = protection_rows(inventory)
    targets = []
    for candidate in static['targets']:
        product.eligible(candidate['xml_provenance'], candidate['parameters']['WIDTH'], candidate['metric'])
        require(candidate['module_checksum'] == '3250293308' and candidate['native_id'] is None and
                candidate['native_vector_id'] is None and candidate['unreachable_selector_value'] == 1,
                'Only unresolved exact-child true candidates')
        position = condition_position(candidate, rows) if candidate['metric'] == 'cond' else None
        targets.append(dict(candidate=candidate, target_position=position,
            selector=dict(scope=candidate['scope'], full_expression=candidate['expression'],
                          vector='1' if candidate['metric'] == 'cond' else None, native_id=None),
            gate=('PARENT_REVIEW_REQUIRED_EXACT_EXPRESSION_VECTOR1' if position is not None else
                  'HOLD_UNTIL_UNIQUE_READONLY_NATIVE_BRANCH_PARENT_EXPRESSION_BINDING'),
            learn_native_id_from='Native singleton EL only; no XML/root/UI-order numeric transfer',
            expected_signature={k: candidate[k] for k in ('scope', 'module_checksum', 'metric_checksum',
                                                        'point_checksum', 'expression')},
            expected_native_detail=(dict(width='1', bit='-1', vector='1', native_id=None, vector_id=None)
                                    if position is not None else dict(arm='0', signature=candidate['expression'] + ' 1',
                                                                     native_id=None))))
    require(Counter(t['candidate']['metric'] for t in targets) == {'branch': 60, 'cond': 60},
            '120 total candidates means 60 branch plus60 ternary, not120 branch')
    pins = dict(static['pins'])
    pins.update(inventory['input_sha256'])
    for path in (static_path, prepared / 'product-plan.sha256.json', inv_path,
                 inv_path.with_suffix('.sha256.json'), discovery / 'discovery-status.json',
                 HERE / 'lzc_selector_native_product_inventory.py', Path(__file__).resolve(),
                 HERE / 'test_lzc_selector_native_product_capture_prepare.py'):
        pins[str(path)] = sha(path)
    result = dict(status='PRODUCT_120_SINGLETON_CAPTURE_PLAN_PARENT_REVIEW_REQUIRED_NO_LAUNCH',
        plan_path=str(output / 'capture-plan.json'), base=static['base'], tests=707,
        candidates=120, branch_candidates=60, condition_op23_candidates=60,
        branch_preflight_hold=60, condition_signature_capture_proposals=60,
        targets=targets, protection_rows=rows, native_visible_positions=4200,
        hidden_xml_op16_positions_not_qualified=1200, op16_candidates_hold=60,
        native_signature_qualification_complete=False, capture_approval=False,
        application_approval=False, launched=False, native_id_transfer=False, pins=pins,
        proposed_pilot_keys=[next(t['candidate']['key'] for t in targets if
                                t['candidate']['metric'] == 'cond' and t['candidate']['parameters']['WIDTH'] == width)
                             for width in (10, 23)],
        proposed_bounds=dict(maximum_total_singletons=120, singletons_per_session=1,
                             proposed_host_timeout_seconds=900, pilot_sessions=2,
                             approval_scope='Parent must separately approve pilot/script; batch requires new approval'),
        capture_contract=[
            'No launch entry point in this prepare tool; DVE capture script must receive separate parent review.',
            'Recheck exact707 test population, all source/build/shape pins and child module3250293308.',
            'Expand product hierarchy and verify complete native inventories in all36 children before exclusion.',
            'Branch unresolved: require unique independent exact native parent text mapping to observed branch ID. Missing/ambiguous mapping aborts before exclusion; no XML ID fallback.',
            'Condition: select exact discovered full ternary expression then vector1 only; never use XML/root numeric IDs or opaque UI columns.',
            'Before, selected, reset, reloaded, final: five complete global4200 native state audits. Only exact selected target may change.',
            'Save first singleton EL, reset/save empty, reload/recalculate/audit, save second identical EL, reset/audit/save final empty.',
            'Offline parse exactly one EL entry, bind exact child/module/metric/point checksum/expression/true detail; learn native IDs from saved signature.',
            'Parent separately approves processor application after signature/semantic/full protection review. Root two-state proof does not certify four-state initialization or hidden op16 state.'
        ])
    product.check_pins(pins)
    output.mkdir()
    write(output / 'capture-plan.json', result)
    write(output / 'capture-plan.sha256.json', {str(output / 'capture-plan.json'): sha(output / 'capture-plan.json')})
    print(json.dumps({k: result[k] for k in ('status', 'candidates', 'branch_preflight_hold',
                                          'condition_signature_capture_proposals', 'native_visible_positions')}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('--prepared', type=Path, required=True)
    prep.add_argument('--discovery', type=Path, required=True)
    prep.add_argument('--output', type=Path, required=True)
    verify = commands.add_parser('verify-case')
    verify.add_argument('--plan', type=Path, required=True)
    verify.add_argument('--case', type=Path, required=True)
    verify.add_argument('--key', required=True)
    verify.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare(args.prepared.resolve(), args.discovery.resolve(), args.output.resolve())
    else:
        plan_path = args.plan.resolve()
        product.check_pins(json.loads(plan_path.with_suffix('.sha256.json').read_bytes()))
        require(args.output.resolve().is_relative_to(product.OUT), 'Offline report outside workspace')
        write(args.output.resolve(), verify_case(args.case.resolve(), json.loads(plan_path.read_bytes()), args.key))


if __name__ == '__main__':
    main()
