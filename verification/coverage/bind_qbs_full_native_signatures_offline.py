"""Audit actual fullcapture, build expected signatures/protection; no EDA or apply."""
import argparse
from collections import Counter
import json
from pathlib import Path
import tkinter

import prepare_qbs_full_nested_native_profile as full

f = full.f
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_bind_qbs_full_native_signatures_offline.py')
CAPTURE = f.proof.OUT/'qbs-full-nested-native-profile-agent-20261006-01'
CAPTURE_SEAL = 'c11ddc09123d063682e6ec738743cc37fdddefa5c921c3f64c4473c01ffd2f30'


def normalize(t, text):
    value = text
    for _ in range(4):
        parts = t.splitlist(value)
        if len(parts) != 1 or parts[0] == value:
            break
        value = parts[0]
    return value


def displays(raw, artifact):
    full.inspect_rows(raw, artifact)
    t = tkinter.Tcl(); t.tk.wantobjects(False)
    result = []
    for line in raw.decode('ascii').splitlines():
        row = t.splitlist(line)
        if row[0] != 'group':
            continue
        selected = normalize(t, row[9])
        vectors = [normalize(t, x) for x in t.splitlist(row[10])]
        original = [normalize(t, x) for x in t.splitlist(row[8])]
        result.append(dict(scope=row[1], expression=row[2], observed_handle=row[4],
            actual_path=row[5], actual_meta=row[6], raw_condition_display=row[9], raw_vector_display=row[10],
            condition_display_kind='META_ONLY_NO_NUMERIC_ID' if selected == row[6] else 'OPAQUE_UNPARSED_NOT_NUMERIC_PROOF',
            vector_display_kind='TRUTH_NAMES_ONLY_NO_VECTOR_IDS' if vectors == original else 'OPAQUE_UNPARSED_NOT_NUMERIC_PROOF',
            observed_native_condition_id=None, observed_native_vector_ids=None))
    f.require(len(result) == 1344, 'Incomplete actual display observations')
    return result


def protection(artifact):
    byscope = {}
    for scope, s in artifact['scope_protection'].items():
        width = s['width']; target = int(s['target_raw_bitmap'], 16); protected = int(s['protected_raw_bitmap'], 16)
        expected = sum(1 << (width-1-c['point']['raw_index']) for c in artifact['candidates'] if c['scope'] == scope)
        f.require(width == 21503 and target == expected and not target & protected and
            target | protected == (1 << width)-1 and bin(target).count('1') == 896 and
            bin(protected).count('1') == 20607, 'Exact target/complement bitmap differs')
        neighbors = []
        for g in artifact['native_groups']:
            if g['scope'] == scope:
                f.require(g['retained'] and set(g['targets']).isdisjoint(g['retained']) and
                          sorted(g['targets']+g['retained']) == sorted(g['names']), 'Whole/missing/aliased group')
                neighbors.append(dict(expression=g['expression'], retained_vectors=g['retained']))
        f.require(sum(len(g['retained_vectors']) for g in neighbors) == 896, 'Neighbor protection differs')
        byscope[scope] = dict(width=width, module_checksum=s['module_checksum'], metric_checksum=s['metric_checksum'],
            target_bitmap=hex(target), protected_bitmap=hex(protected), target_count=896, protected_count=20607,
            retained_target_group_vectors=neighbors, native_protection_qualified=False)
    f.require(len(byscope) == 2, 'Exact two scope complement required')
    return byscope


def bind_explicit_native(raw, artifact):
    """Only typed actual native EL signatures qualify this binding, never display/order."""
    records = f.proof.bind_native(raw, artifact['candidates'])
    f.require(len(records) == 1792 and all(int(r['native_id']) >= 0 and int(r['vector_id']) >= 0 for r in records),
              'Exact explicit numeric native records required')
    return records


def singleton_evidence(artifact):
    root = f.proof.OUT/'lzc_selector_native_product_batch-707-20261006-05'
    status_path = root/'batch-status.json'
    status = json.loads(status_path.read_bytes())
    paths = [root/'case-000'/name for name in ('first.el', 'second.el', 'before.tsv',
             'selected.tsv', 'reset.tsv', 'reloaded.tsv', 'final.tsv',
             'initial-empty.el', 'reset-empty.el', 'final-empty.el')]
    pins = {str(p): status['artifacts'][str(p)] for p in paths}
    f.check_pins(pins)
    first = paths[0].read_bytes()
    f.require(status['returncode'] == 0 and first == paths[1].read_bytes() and
              b'Condition 20 "1194113825"' in first and b'(2 "1")' in first and
              all((root/'case-000'/name).read_bytes() == b'' for name in
                  ('initial-empty.el', 'reset-empty.el', 'final-empty.el')),
              'Existing actual singleton signature/reset evidence differs')
    script = SCRIPT.with_name('lzc_selector_native_product_batch.tcl')
    pins[str(script)] = f.sha(script)
    executed_script = Path(status['actual_script'])
    f.require(f.sha(executed_script) == status['actual_script_sha256'], 'Historical executed script drift')
    for p in (executed_script, SCRIPT.with_name('lzc_selector_native_product_batch_v5_library.tcl'),
              SCRIPT.with_name('lzc_selector_native_product_discover.tcl')):
        pins[str(p)] = f.sha(p)
    pins[str(status_path)] = f.sha(status_path)
    expression = '(activation_valid_i[0] && gen_side_row[0].gen_activation_byte[0].older[8])'
    matches = [c for c in artifact['candidates'] if c['scope'].endswith('bank0.i_payload_buffer')
               and c['point']['expression'] == expression and c['point']['vector'] == '11']
    f.require(len(matches) == 1, 'Exact single nested vector candidate absent')
    return pins, dict(existing_actual_EL=str(paths[0]), observed_condition_id=20,
        observed_vector_id=2, reload_bytes_identical=True,
        applicability='Actual LZC condition export API evidence only; NOT QBS nested-meta qualification.',
        QBS_probe_candidate=matches[0], selected_vector_count=1,
        plan_only=True, authorization_required=True,
        read_only=False, reason='Native EL export of a selected vector requires temporary GUI exclusion, then reset; no persisted application.',
        known_API_sequence=[
            'gui_list_action -id CoverageTable.1 -column Condition EXACT_SCOPE',
            'Resolve actual parent/child handles afresh; verify observed path/meta and selected readback',
            'Clear prior selections; gui_list_select -id CovDetail.1 -list cond -select [list ACTUAL_CHILD_META]',
            'gui_list_select -id CovDetail.1 -list vector -select [list 11]; verify exact selected count/name',
            'gui_exclude_items -id CovDetail.1 -list vector -selected -annotation REVIEWED_ANNOTATION',
            'gui_exclusion -id CoverageTable.1 -recalculate',
            'gui_exclusion_file -save -file SINGLETON_EL',
            'gui_exclusion -reset',
            'gui_exclusion_file -load -file SINGLETON_EL',
            'Repeat exact signature and neighbor audit; gui_exclusion -reset; save final empty EL'],
        exact_protection='Global initial empty EL; all three nested truth vectors before/selected/reset/reload/final, plus parent and adjacent gate vectors. Only nested11 selected; nested01/10 and all other1791 candidate vectors protected. Global EL exactly one record excludes all43005 other raw condition points, all other metrics/scopes. No whole condition/module record allowed.',
        numeric_gate='Actual EL Condition/vector IDs plus exact module/metric/point checksums,width,bit,expression,truth vector; never infer IDs from handles/XML order.',
        no_launch=True, full1792_qualification=False)


def evidence():
    path = CAPTURE/'discovery-plan.json'
    f.require(f.sha(path) == CAPTURE_SEAL, 'Actual fullcapture external seal differs')
    plan = json.loads(path.read_bytes()); status_path = CAPTURE/'capture-status.json'
    status = json.loads(status_path.read_bytes())
    f.check_pins(plan['pins']); f.check_pins(status['artifacts'])
    artifact = json.loads(Path(plan['proof']).read_bytes())
    raw_path = CAPTURE/'native-rows.tcllist'; raw = raw_path.read_bytes()
    actual = full.inspect_rows(raw, artifact)
    f.require(status['returncode'] == 0 and all(status[k] == v for k, v in actual.items()), 'Actual terminal/independent replay differs')
    observed = displays(raw, artifact)
    kinds = dict(condition=dict(Counter(x['condition_display_kind'] for x in observed)),
                 vector=dict(Counter(x['vector_display_kind'] for x in observed)))
    expected = []
    for c in artifact['candidates']:
        point = c['point']; attrs = point['attributes']
        expected.append(dict(scope=c['scope'], raw_index=point['raw_index'], expression=point['expression'],
            vector=point['vector'], module_checksum=c['module_checksum'], metric_checksum=c['checksum'],
            point_checksum=attrs['chksum'], width=attrs['width'], bit='-1',
            compiled_condition_id_NOT_GUI=point['native_id'], observed_native_id=None, observed_vector_id=None))
    pins = dict(plan['pins']); pins.update(status['artifacts'])
    singleton_pins, singleton = singleton_evidence(artifact)
    pins.update(singleton_pins)
    for p in (path, status_path, SCRIPT, TEST, full.SCRIPT, full.TEST, full.BODY, full.TCL,
              Path(f.proof.__file__), SCRIPT.with_name('lzc_native_records.py'),
              SCRIPT.with_name('prepare_mask_store_snapshot_cond24.py')):
        pins[str(p)] = f.sha(p)
    session = (CAPTURE/'DVEfiles/session.tcl').read_text()
    condition_header = 'Layout_CovDetail_cndListView_names Expression, ,  ,   ,ID,Coverage,Line No.,'
    vector_header = 'Layout_CovDetail_vector_names ID, ,  ,   ,Coverage,1,2,'
    f.require(condition_header in session and vector_header in session, 'Actual subview header evidence differs')
    return dict(schema='QBS_FULL_NATIVE_SIGNATURE_PROTECTION_OFFLINE_V1',
        status='ACTUAL1344_MAPPING_PASS_NUMERIC_SIGNATURE_AND_PROTECTION_HOLD', pins=pins,
        capture=str(CAPTURE), capture_seal=CAPTURE_SEAL, parent_execution_provenance='PARENT_AGENT_INDEPENDENT_EXECUTION',
        actual_capture_replayed=actual, ID_display_semantics=kinds, observed_groups=observed,
        expected_compiled_signatures_NOT_NATIVE_EVIDENCE=expected, observed_native_numeric_records=0,
        signature_gap='All1344 selected-object ID-display fields still return meta and vector truth names; neither handles nor XML IDs are native Condition/vector IDs.',
        actual_saved_subview_headers=dict(condition=condition_header, vector=vector_header,
            endpoint_ID_column_width=0, width_at_show1_not_captured=True,
            future_ID_heading_query_is_plan_only=True),
        bounded_singleton_interface_study=singleton,
        scope_protection=protection(artifact), protected_count=41214, target_count=1792,
        scope_boundary=f.SCOPE_BOUNDARY,
        future_numeric_gate=dict(required='Actual typed native Condition/vector IDs plus module/metric/point checksum, width,bit,expression and truth vector; strict binder provided, no synthetic EL produced.',
            ID_field_read='Known actual Condition/vector subview ID heading, not blank hidden columns; only a future separately reviewed run may query it.',
            preferred_signature_authority='Observed native singleton EL checksum/expression/vector record, not GUI display ID alone.',
            no_relaunch_authorized=True),
        future_protection_gate=dict(native_status='HOLD_NOT_EXECUTED', stages=[
            'initial-global-empty', 'before-read-only-neighbor-audit', 'selected-exact1792-vector-audit',
            'first-native-EL-exact-shape', 'reset-global-empty', 'reload-first-EL',
            'reloaded-exact1792-and-neighbor-audit', 'second-EL-identical-signatures', 'final-reset-global-empty'],
            full41214_basis='Exact raw complement pinned to compiled shape;1792 neighboring truth vectors explicitly retained. Future exact1792 vector-only EL allowlist rejects every complement point, other scope/metric, wholecondition/module and extra record.',
            untouched_dynamic_points='All mask/plane/offset/byte_valid and other non-target vectors remain protected; no blanket module waiver.'),
        native_qualified=False, protection_qualified=False, EDA_started=False, exclusions_applied=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'verify'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    args = parser.parse_args(); output = args.output.absolute()
    f.require(output.parent == f.proof.OUT and output.resolve() == output, 'Direct fresh out required')
    if args.command == 'prepare':
        f.require(not output.exists(), 'Existing artifact protected')
        record = evidence(); output.mkdir(); f.write(output/'review-plan.json', record)
        print(json.dumps(dict(output=str(output), seal=f.sha(output/'review-plan.json'), native_qualified=False)))
    else:
        f.require(f.sha(output/'review-plan.json') == args.seal, 'External successor seal drift')
        record = json.loads((output/'review-plan.json').read_bytes())
        f.require(record == evidence(), 'Offline signature/protection reproduction differs')
        print('VERIFY_PASS_NUMERIC_SIGNATURE_PROTECTION_HOLD_NO_EDA')


if __name__ == '__main__':
    main()
