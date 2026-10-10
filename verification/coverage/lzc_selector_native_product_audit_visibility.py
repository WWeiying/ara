#!/usr/bin/env python3
"""Offline provenance/visibility diagnosis of failed batch02; no DVE launch."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import re

from lzc_selector_native_prepare import require, sha, write, tcl_word
from lzc_selector_native_product_inventory import decode_lines
from lzc_selector_native_product_prepare import OUT, check_pins

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / 'lzc_selector_native_product_audit_visibility.tcl'


def bindings(rows, records):
    native = {}
    for r in records:
        if r[0] != 'branch':
            continue
        require(len(r) == 7, 'Unexpected raw native branch schema')
        _, scope, identity, arm, parent, meta, _ = r
        match = re.fullmatch(r'Branch(\d+)\.([01])', meta)
        require(match is not None and match.groups() == (identity, arm) and parent == 'Item' + identity,
                'Raw native parent/meta/token identity differs')
        key = scope, identity, arm
        require(key not in native, 'Duplicate raw native branch token')
        native[key] = r
    result, seen = [], set()
    for position, row in enumerate(rows):
        if row['metric'] != 'branch':
            continue
        key = row['scope'], row['native_id'], row['vector']
        require(key in native and key not in seen, 'Protected branch not uniquely sourced from native discovery')
        seen.add(key)
        raw = native[key]
        result.append(dict(position=position, scope=raw[1], native_parent_path=raw[4],
                           native_select_token=raw[5], logical_native_id=raw[2], vector=raw[3]))
    require(seen == set(native) and len(result) == 1200 and len(rows) == 4200,
            'Native protection population changed')
    return result


def selection_text(values):
    text = 'array set lpa_binding [list \\\n'
    groups = defaultdict(list)
    for r in values:
        fields = (r['scope'], r['native_parent_path'], r['native_select_token'], r['logical_native_id'], r['vector'])
        text += ' ' + tcl_word(r['position']) + ' [list ' + ' '.join(map(tcl_word, fields)) + '] \\\n'
        groups[r['scope']].append((r['native_parent_path'], r['native_select_token']))
    text += ']\narray set lpa_expected [list \\\n'
    for scope, entries in groups.items():
        text += ' ' + tcl_word(scope) + ' [list ' + ' '.join(
            '[list ' + ' '.join(map(tcl_word, pair)) + ']' for pair in entries) + '] \\\n'
    return text + ']\n'


def diagnose(discovery, failed, output):
    require(discovery.parent == failed.parent == output.parent == OUT and not output.exists(),
            'Fresh direct offline evidence directory required')
    plan_path = failed / 'batch-plan.json'
    check_pins(json.loads((failed / 'batch-plan.sha256.json').read_bytes()))
    plan = json.loads(plan_path.read_bytes())
    check_pins(plan['pins'])
    records = decode_lines((discovery / 'native-inventory.tcllist').read_bytes().decode('latin1'))
    values = bindings(plan['protection_rows'], records)
    status = json.loads((failed / 'batch-status.json').read_bytes())
    require(status['status'] == 'FAILED_RECORDED_NOT_QUALIFICATION' and status['returncode'] == 0,
            'Recorded terminal non-qualified failure required')
    audits = {}
    for stage in ('global-before', 'global-final'):
        with (failed / (stage + '.tsv')).open() as stream:
            audits[stage] = list(csv.DictReader(stream, delimiter='\t'))
        require(len(audits[stage]) == 2, 'Failure no longer matches two-row boundary')
    require(audits['global-before'] == audits['global-final'], 'Before/final failure boundary differs')
    gui = (failed / 'DVEfiles/dve_gui.log').read_text()
    require('"Branch1.0"  were not found' in gui and 'LZC_NATIVE_BATCH_FAILED' in gui,
            'Expected native visibility failure not present')
    require(not list(failed.glob('case-*')) and not (failed / 'batch-result.json').exists(),
            'Failure occurred after cases started; analysis must be revised')
    for name in ('initial-empty.el', 'final-empty.el'):
        require((failed / name).read_bytes() == b'', 'Failure has residual native exclusion evidence')
    target = values[2]
    require(target['position'] == 2 and target['native_parent_path'] == 'Item1' and
            target['native_select_token'] == 'Branch1.0', 'Raw failure token differs')
    cond_source = (HERE / 'lzc_selector_native_product_discover.tcl').read_text().split('proc lpd_conditions ', 1)[1].split('proc lpd_session ', 1)[0]
    require('gui_list_expand' not in cond_source, 'Successful condition discovery used tree expansion; reassess')
    sources = [plan_path, failed / 'batch-plan.sha256.json', failed / 'batch-status.json',
               failed / 'global-before.tsv', failed / 'global-final.tsv', failed / 'DVEfiles/dve_gui.log',
               failed / 'initial-empty.el', failed / 'final-empty.el', discovery / 'native-inventory.tcllist',
               HERE / 'lzc_selector_native_product_discover.tcl', HERE / 'lzc_selector_native_product_batch.tcl',
               HERE / 'lzc_selector_native_product_capture_prepare.py', SCRIPT, Path(__file__).resolve(),
               HERE / 'test_lzc_selector_native_product_audit_visibility.py']
    pins = {str(path): sha(path) for path in sources}
    report = dict(status='STATIC_PROVENANCE_AND_VISIBILITY_DIAGNOSIS_NO_DVE_NO_QUALIFICATION',
        failed_batch=str(failed), elapsed_seconds=status['elapsed_seconds'], qualified_candidates=0,
        raw_native_branch_tokens=1200, preserved_native_visible_positions=4200,
        observed_failed_token=target, successful_rows=audits['global-before'],
        id_provenance=['DVE leaf meta -> regexp native ID/arm -> native-inventory.tcllist',
                       'inventory branch_native_rows -> protection_rows native[2]/native[3]',
                       'batch selection row -> lpb_row reconstructs the same observed BranchID.arm token'],
        raw_xml_native_id_used_for_failed_audit=False,
        confirmed=['All1200 protection branch IDs/arms exactly match raw observed native metadata.',
                   'Branch1.0 exists under native Item1 in the same compiled child discovery.',
                   'Discovery expands CovDetail.1 branch tree before selection; batch lpb_row omits that expansion.',
                   'Both audits stop after Branch0.0 and Branch0.1; no singleton case/exclusion was reached.'],
        causal_inference='Fresh Branch view leaves later parent children collapsed/non-selectable; omitted CovDetail expansion explains the exact two-row boundary.',
        inference_limit='The failing session did not record tree expansion flags or fresh full branch inventory. GUI visibility mechanism is statically supported and mocked, not directly remeasured.',
        correction='Library-only successor expands branch detail after every Branch view action, validates complete observed parent/meta set once per scope/pass, and selects saved native meta verbatim with exact count/readback.',
        condition_review='Successful discovery condition path uses cond/vector ListViews without CovDetail tree expansion; preserve that path, and test exact count/readback rejection. Batch02 never reached condition audit.',
        future_live_gate='No new DVE approved here. Before any future exclusion, successor must finish full4200 native initial audit; branch expression matching and EL signatures remain required.',
        frozen_files_modified=False, rtl_modified=False, launched=False,
        native_signature_qualification_complete=False, application_approval=False, pins=pins)
    output.mkdir()
    write(output / 'native-bindings.json', values)
    write(output / 'native-bindings.tcl', selection_text(values))
    report['pins'][str(output / 'native-bindings.json')] = sha(output / 'native-bindings.json')
    report['pins'][str(output / 'native-bindings.tcl')] = sha(output / 'native-bindings.tcl')
    write(output / 'diagnosis.json', report)
    write(output / 'diagnosis.sha256.json', {str(output / 'diagnosis.json'): sha(output / 'diagnosis.json')})
    print(json.dumps({k: report[k] for k in ('status', 'raw_native_branch_tokens', 'preserved_native_visible_positions', 'qualified_candidates')}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--discovery', type=Path, required=True)
    parser.add_argument('--failed-batch', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    diagnose(args.discovery.resolve(), args.failed_batch.resolve(), args.output.resolve())


if __name__ == '__main__':
    main()
