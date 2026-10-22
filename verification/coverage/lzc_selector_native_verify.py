#!/usr/bin/env python3
"""Verify standalone native singleton artifacts; no processor exclusion authority."""
import argparse
import csv
import json
from pathlib import Path

import lzc_selector_native_prepare as native
import lzc_selector_native_run as runner
from lzc_native_records import parse_records
from inventory_operand_debug import Design
from audit_readonly import native_entries


def verify_states(path, rows, target):
    with path.open() as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        native.require(reader.fieldnames == ['position', 'metric', 'id', 'vector', 'excluded'],
                       'Unexpected audit schema')
        actual = list(reader)
    expected = [dict(position=str(i), metric=r[0], id=r[1], vector=r[2],
                     excluded=str(int(i == target))) for i, r in enumerate(rows)]
    native.require(actual == expected, 'Protected singleton audit differs: ' + str(path))


def verify(capture):
    plan = json.loads((capture / 'capture-plan.json').read_bytes())
    status = json.loads((capture / 'native-capture-status.json').read_bytes())
    native.require(status['status'] == 'CAPTURE_COMPLETE_PENDING_OFFLINE_VERIFICATION', 'Not completed capture')
    runner.check_pins(plan['pins'])
    runner.check_pins(status['artifacts'])
    case = capture.parent
    top = plan['experiment']['top']
    scope = top + '.dut'
    native.require(case.name == top and top.startswith('lzc_selector_native_'), 'Standalone scope required')
    design = Design(case / 'simv.vdb')
    rows = plan['rows']
    metadata = {}
    for metric in ('branch', 'cond'):
        node, population = native.compiled_points(design, scope, metric)
        for point in population:
            metadata[metric, point['native_id'], point['vector']] = (node.get('chksum'), point)
    verify_states(capture / 'before.tsv', rows, -1)
    verify_states(capture / 'final.tsv', rows, -1)
    records = []
    for target in plan['targets']:
        metric, identity, vector, expression = rows[target]
        metric_checksum, point = metadata[metric, identity, vector]
        first = capture / f'first-{target}.el'
        second = capture / f'second-{target}.el'
        native.require(first.read_bytes() == second.read_bytes() and first.stat().st_size > 0,
                       'Native saved signature roundtrip differs')
        if metric == 'cond':
            parsed = parse_records(first.read_text())
            native.require(len(parsed) == 1, 'Not exactly one native condition vector')
            record = parsed[0]
            wanted = dict(scope=scope, module_checksum=design.hierarchy[scope].get('chksum'),
                          metric_checksum=metric_checksum,
                          point_checksum=point['attributes']['chksum'], expression=expression,
                          width=point['attributes']['width'], bit='-1', vector=vector)
            native.require(all(record.get(k) == v for k, v in wanted.items()), 'Native condition signature differs')
            native.require(record['native_id'] == '2' and record['vector_id'] == str(int(vector) + 1),
                           'Root native condition identity differs from measured standalone pilot')
        else:
            parsed = native_entries(first.read_text())
            native.require(len(parsed) == 1, 'Not exactly one native branch arm')
            record = parsed[0]
            native.require(record['scope'] == scope and record['point'] == f'Branch {identity} ({vector})'
                           and record['checksum'] == [design.hierarchy[scope].get('chksum'), metric_checksum]
                           and record['nativepointchecksum'] == point['attributes']['chksum'],
                           'Native branch signature differs')
        for stage, active in (('selected', target), ('reset', -1), ('reloaded', target)):
            verify_states(capture / f'{stage}-{target}.tsv', rows, active)
        native.require((capture / f'reset-{target}.el').read_bytes() == b'', 'Residual reset exclusions')
        records.append(dict(position=target, metric=metric, native=record, compiled_point=point))
    for name in ('initial-empty.el', 'final-empty.el'):
        native.require((capture / name).read_bytes() == b'', 'Residual global exclusions')
    log = (capture / 'DVEfiles/dve_gui.log').read_text()
    root_branch = {r['compiled_point']['native_id'] for r in records if r['metric'] == 'branch'}
    root_cond = {r['compiled_point']['native_id'] for r in records if r['metric'] == 'cond'}
    native_lines = []
    seen = set()
    for line in log.splitlines():
        if line.startswith('LSN_NATIVE_BRANCH '):
            key = tuple(line.split()[:3])
            selected = line.split()[1].split('=')[1] in root_branch
        elif line.startswith('LSN_NATIVE_CONDITION '):
            key = tuple(line.split()[:2])
            selected = line.split()[1].split('=')[1] in root_cond
        else:
            continue
        if selected and key not in seen:
            seen.add(key)
            native_lines.append(line)
    native.require(len(native_lines) == (3 if plan.get('xml_only_rows') else 4),
                   'Missing pre-exclusion native root coverage observations')
    return dict(status='STANDALONE_NATIVE_ARTIFACT_VERIFIED_NOT_PROCESSOR_APPROVAL',
                experiment=plan['experiment'], captured_records=records,
                protected_rows_per_audit=len(rows), complete_audits=2 + 3 * len(plan['targets']),
                singleton_roundtrips=len(plan['targets']), global_final_empty=True,
                xml_only_rows=plan.get('xml_only_rows', []),
                xml_only_rows_individually_native_qualified=False,
                native_pre_exclusion_observations=native_lines,
                artifact_sha256={str(p): native.sha(p) for p in capture.rglob('*') if p.is_file()},
                old_processor_exclusions=False, application_approval=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    native.write(args.output.absolute(), verify(args.capture.absolute()))


if __name__ == '__main__':
    main()
