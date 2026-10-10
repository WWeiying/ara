#!/usr/bin/env python3
"""Offline parsing of complete read-only product native inventory, no qualification."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import tkinter

from lzc_selector_native_prepare import require, sha, write
from lzc_selector_native_product_prepare import check_pins, OUT


def decode_lines(text):
    parser = tkinter.Tcl()
    # splitlist parses data only; do not evaluate the native inventory as Tcl code.
    records, pending = [], ''
    for line in text.split('\n'):
        if not line and not pending:
            continue
        pending += line
        require(len(pending) < 4 * 1024 * 1024, 'Native record exceeds bounded size')
        try:
            record = list(parser.splitlist(pending))
        except tkinter.TclError:
            pending += '\n'
            continue
        records.append(record)
        pending = ''
    require(not pending, 'Incomplete Tcl native inventory record')
    return records


def normalize(value, parser):
    for _ in range(4):
        values = parser.splitlist(value)
        if len(values) != 1 or values[0] == value:
            break
        value = values[0]
    return value


def bind(records, static):
    parser = tkinter.Tcl()
    scopes = sorted({r['scope'] for r in static['targets']})
    grouped = defaultdict(list)
    populations = []
    allowed = {'population': 4, 'child_binding': 4, 'branch': 7, 'conditions': 3,
               'condition': 6, 'condition_ids_display': 4, 'child_complete': 4}
    for row in records:
        require(row and row[0] in allowed and len(row) == allowed[row[0]], 'Unexpected native record schema')
        if row[0] == 'population':
            populations.append(row)
        else:
            require(row[1] in scopes, 'Foreign/non-child native scope')
            grouped[row[1]].append(row)
    require(len(populations) == 1 and len(parser.splitlist(populations[0][3])) == 707,
            'Wrong native test population')
    require(sorted(grouped) == scopes, 'Missing product child')
    results = []
    for scope in scopes:
        rows = grouped[scope]
        bindings = [r for r in rows if r[0] == 'child_binding']
        complete = [r for r in rows if r[0] == 'child_complete']
        names = [r for r in rows if r[0] == 'conditions']
        display = [r for r in rows if r[0] == 'condition_ids_display']
        require(len(bindings) == len(complete) == len(names) == len(display) == 1,
                'Incomplete/duplicate child inventory')
        child = next(r for r in static['targets'] if r['scope'] == scope)
        params = ','.join(f'{k}={v}' for k, v in sorted(child['parameters'].items()))
        require(bindings[0][2:] == ['3250293308', params] and child['module_checksum'] == '3250293308',
                'Child module/parameter binding differs')
        cond = next(r for r in static['protected'] if r['scope'] == scope and r['metric'] == 'cond')
        branch = next(r for r in static['protected'] if r['scope'] == scope and r['metric'] == 'branch')
        expected = defaultdict(set)
        for point in cond['points']:
            if point['attributes']['optype'] != '16':
                expected[point['expression']].add(point['vector'])
        actual_names = [normalize(v, parser) for v in parser.splitlist(names[0][2])]
        require(len(actual_names) == len(set(actual_names)) and sorted(actual_names) == sorted(expected),
                'Complete native expressions differ')
        actual_cond = [r for r in rows if r[0] == 'condition']
        require(len(actual_cond) == len(expected) and {r[2] for r in actual_cond} == set(expected),
                'Condition detail inventory incomplete/duplicate')
        conditions = []
        for row in actual_cond:
            vectors = list(parser.splitlist(row[3]))
            require(len(vectors) == len(set(vectors)) and set(vectors) == expected[row[2]],
                    'Native true/false vector population differs')
            conditions.append(dict(expression=row[2], vectors=vectors, native_columns=row[4],
                                   condition_columns=row[5], native_id=None,
                                   note='Display/raw columns retained; no numeric ID inferred from XML/root/order'))
        arms = [r for r in rows if r[0] == 'branch']
        require(len(arms) == len(branch['points']), 'Complete native branch row count differs')
        ids = defaultdict(set)
        for row in arms:
            require(row[2].isdigit() and row[3] in ('0', '1') and
                    row[4] == 'Item' + row[2] and row[5] == f'Branch{row[2]}.{row[3]}',
                    'Native branch path/signature differs')
            require(row[3] not in ids[row[2]], 'Duplicate native arm')
            ids[row[2]].add(row[3])
        require(all(v == {'0', '1'} for v in ids.values()), 'Missing native true/false branch arm')
        vector_count = sum(len(c['vectors']) for c in conditions)
        require(complete[0][2:] == [str(len(arms)), str(vector_count)], 'Child completion counters differ')
        results.append(dict(scope=scope, module_checksum='3250293308', parameters=child['parameters'],
                            branch_native_rows=arms, branch_native_ids_observed=sorted(ids, key=int),
                            conditions=conditions, condition_ids_display_raw=display[0][2:],
                            native_positions=len(arms) + vector_count,
                            branch_id_to_expression_binding_pending=True,
                            condition_numeric_signature_binding_pending=True))
    return results


def verify(discovery, output):
    require(discovery.parent == OUT and output.parent == discovery and not output.exists(),
            'Fresh output inside discovery directory required')
    plan = json.loads((discovery / 'discovery-plan.json').read_bytes())
    status = json.loads((discovery / 'discovery-status.json').read_bytes())
    check_pins(json.loads((discovery / 'discovery-plan.sha256.json').read_bytes()))
    check_pins(plan['pins'])
    check_pins(status['artifacts'])
    require(status['status'] == 'READONLY_DISCOVERY_COMPLETE_PENDING_OFFLINE_BINDING'
            and not status['excludes'] and not status['captures'], 'Not complete read-only discovery')
    static = json.loads((Path(plan['prepared']) / 'product-plan.json').read_bytes())
    raw = (discovery / 'native-inventory.tcllist').read_bytes()
    # ASCII identities remain exact; transport opaque UI bytes losslessly, not as guessed Unicode.
    rows = bind(decode_lines(raw.decode('latin1')), static)
    result = dict(status='READONLY_NATIVE_INVENTORY_VERIFIED_NOT_CAPTURE_OR_APPLICATION_APPROVAL',
        children=len(rows), native_positions=sum(r['native_positions'] for r in rows), rows=rows,
        xml_or_root_ids_transferred=False, native_signature_qualification_complete=False,
        raw_ui_encoding='DVE default unknown; lossless latin1 byte transport, not semantic decoding',
        op16='HOLD', exclusions_applied=False, captures_started=False, application_approval=False,
        input_sha256={str(p): sha(p) for p in (discovery / 'discovery-plan.json',
            discovery / 'discovery-status.json', discovery / 'native-inventory.tcllist',
            Path(__file__).resolve(), Path(__file__).with_name('test_lzc_selector_native_product_inventory.py'))})
    write(output, result)
    write(output.with_suffix('.sha256.json'), {str(output): sha(output)})
    print(json.dumps({k: result[k] for k in ('status', 'children', 'native_positions')}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--discovery', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    verify(args.discovery.resolve(), args.output.resolve())


if __name__ == '__main__':
    main()
