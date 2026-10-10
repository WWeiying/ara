"""Offline exact native FSM identity, protected points and rooted report audit."""
import argparse
import csv
import json
from pathlib import Path
import re

import fsm741_exact_capture_v2 as capture
import fsm741_transition_batch as batch
from inventory_operand_debug import Design
from closure_point_inventory import read_xml

life, require = capture.life, capture.require
ANNOTATION = 'Frozen configuration/source-proven FSM point; exact three-group scope'
METRICS = ('Score', 'Line', 'Toggle', 'FSM', 'Condition', 'Branch')


def native_records(text):
    module = metric = scope = machine = machine_sha = annotation = None
    records = []
    for line in text.splitlines():
        require(line != '', 'Unexpected empty native directive')
        match = re.fullmatch(r'CHECKSUM: "([0-9]+) ([0-9]+)"', line)
        if match:
            module, metric = match.groups()
            scope = machine = machine_sha = annotation = None
            continue
        match = re.fullmatch(r'INSTANCE: (\S+)', line)
        if match:
            require(module is not None, 'INSTANCE without checksum')
            scope = match[1]
            machine = machine_sha = annotation = None
            continue
        match = re.fullmatch(r'Fsm (\S+) "([0-9]+)"', line)
        if match:
            require(scope is not None, 'Fsm without instance')
            machine, machine_sha = match.groups()
            annotation = None
            continue
        match = re.fullmatch(r'ANNOTATION: "([^"\r\n]*)"', line)
        if match:
            require(machine is not None, 'Annotation without machine')
            annotation = match[1]
            continue
        match = re.fullmatch(r'(State|Transition) (\S+) "([^"\r\n]+)"', line)
        require(match is not None and all(v is not None for v in
                (module, metric, scope, machine, machine_sha, annotation)), 'Unknown/incomplete native directive: ' + line)
        records.append((module, metric, scope, machine, machine_sha, annotation, *match.groups()))
    require(len(records) == len(set(records)), 'Duplicate native exclusion')
    return sorted(records)


def expected_records(plan, design):
    records = []
    for group in plan['groups']:
        states = {r['name']: r['attributes']['value'] for g in plan['groups']
                  if g['scope'] == group['scope'] and g['machine']['name'] == group['machine']['name']
                  and g['mode'] == 'State' for r in g['rows']}
        for row in group['rows']:
            if not row['target']:
                continue
            signature = (str(int(states[row['source']], 16)) + '->' + str(int(states[row['destination']], 16))
                         if group['mode'] == 'Transition' else str(int(row['attributes']['value'], 16)))
            records.append((design.hierarchy[group['scope']].get('chksum'), group['checksum'],
                            group['scope'], group['machine']['name'], group['machine']['chksum'],
                            ANNOTATION, group['mode'], row['name'], signature))
    require(len(records) == len(set(records)) == plan['targets'], 'Expected native population differs')
    return sorted(records)


def audit_points(rows, plan):
    expected = {}
    for stage in ('initial', 'applied', 'reset', 'reloaded', 'final'):
        for group in plan['groups']:
            for row in group['rows']:
                key = (stage, group['scope'], group['machine']['name'], group['mode'], row['name'])
                observed = plan.get('strategy') == 'direct-transition-only-66' and group['mode'] == 'State' and stage in ('applied', 'reloaded')
                expected[key] = 'INHERITED_OBSERVATION' if observed else str(int(stage in ('applied', 'reloaded') and row['target']))
                if plan.get('point_query_authority') == 'saved-native-identity' and row['target'] and stage in ('applied', 'reloaded'):
                    expected[key] = 'NATIVE_EL_AUTHORITY'
    actual = {}
    for row in rows:
        require(len(row) == 7, 'Native audit schema differs')
        key = tuple(row[:5])
        require(key not in actual and key in expected, 'Duplicate/foreign native audit point')
        require(row[6] == expected[key] and (row[5] in ('0', '1') if expected[key] in ('INHERITED_OBSERVATION', 'NATIVE_EL_AUTHORITY')
                                           else row[5] == expected[key]), 'Native exclusion state differs')
        actual[key] = row[6]
    require(actual == expected, 'Missing protected/native audit point')


def audit(out):
    plan_path = out / 'plan.json'
    plan = json.loads(plan_path.read_bytes())
    pins = dict(plan['pins'])
    batch66 = plan.get('strategy') == 'direct-transition-only-66'
    transition_only = batch66 or plan.get('strategy') == 'direct-transition-only'
    target_count, protected_count = (66, 321) if batch66 else ((34, 121) if transition_only else (42, 113))
    require(plan['targets'] == target_count and plan['protected'] == protected_count and plan['no_other_waivers'], 'Wrong exact scope')
    for p in (plan_path, Path(__file__).resolve(), Path(__file__).with_name('test_audit_fsm741_exact.py')):
        pins[str(p)] = life.digest(p)
    life.check(pins)
    raw = life.read_bound(capture.report.admission.RAW, capture.report.admission.RAW_SHA)
    book = life.read_bound(capture.report.BASE / 'admission-manifest.json', capture.report.SEAL)
    authoritative = life.merge_pins(book['input_pins'], book['output_pins'])
    bitmap_path = capture.report.BASE / 'combined-bits.json'
    bitmap = life.read_bound(bitmap_path, authoritative[str(bitmap_path)])
    shape_path = Path(raw['input_ledger'][0]) / 'snps/coverage/db/shape/fsm.verilog.shape.xml'
    expected_groups = (batch if batch66 else capture).groups_from_shape(read_xml(shape_path), bitmap)
    if transition_only and not batch66:
        for group in expected_groups:
            if group['mode'] == 'State':
                for row in group['rows']:
                    row['target'] = False
    require(life.digest(shape_path) == bitmap['design']['shape/fsm.verilog.shape.xml'] and
            plan['groups'] == expected_groups, 'Plan candidate/shape binding differs')
    ledger = (capture.report.BASE / 'combined-inputs.txt').read_text().splitlines()
    require(plan['input_ledger'] == (ledger if plan['population'] == 741 else ledger[:2]), 'Plan population differs')
    tool = capture.tool
    tool.revalidate(raw['tool_identity'])
    design = Design(Path(plan['input_ledger'][0]))
    expected = expected_records(plan, design)
    artifacts = ['status.json', 'first.el', 'second.el', 'initial.el', 'reset.el', 'final-empty.el',
                 'cleanup-empty.el', 'exact-audit.tsv', 'selection.tcl', 'inputs.txt', 'selected_tests.txt',
                 'DVEfiles/dve_gui.log', 'live-identity.json']
    artifacts += ['rooted_' + stage + '.csv' for stage in ('raw', 'applied', 'reset', 'reloaded', 'final')]
    for name in artifacts:
        pins[str(out / name)] = life.digest(out / name)
    require(native_records((out / 'first.el').read_text()) == expected == native_records((out / 'second.el').read_text()),
            'Native checksum/identity/signature/annotation differs')
    require(all((out / name).read_bytes() == b'' for name in ('initial.el', 'reset.el', 'final-empty.el', 'cleanup-empty.el')),
            'Exclusions were not fully cleared')
    audit_points(list(csv.reader((out / 'exact-audit.tsv').open(), delimiter='\t')), plan)
    status = life.read_bound(out / 'status.json', pins[str(out / 'status.json')])
    ordered_driver = ('EXACT66_CAPTURE_REQUIRES_NATIVE_SIGNATURE_REVIEW' if batch66 else
                      ('EXACT34_CAPTURE_REQUIRES_NATIVE_SIGNATURE_REVIEW' if transition_only else
                       'EXACT42_CAPTURE_REQUIRES_NATIVE_SIGNATURE_REVIEW'))
    serialization_order_only = status['status'] == 'FAILED' and status.get('reason') == 'EL serialization differs'
    # Exact semantic equality was already checked above, including duplicate rejection.
    require(status['status'] == ordered_driver or serialization_order_only, 'Capture did not complete')
    require((out / 'inputs.txt').read_text().splitlines() == plan['input_ledger'] and
            (out / 'selected_tests.txt').read_text().splitlines() == plan['selected'], 'Native input/test identities differ')
    log = (out / 'DVEfiles/dve_gui.log').read_text()
    require(log.splitlines().count('FSM741_EXACT_DONE') == 1 and 'FSM741_EXACT_FAILED' not in log and
            'DVE_COVERAGE_EXPORT_FAILED' not in log and not re.search(r'Error:|Fatal:|EK-CMD-|DVTC[0-9]+|UCAPI-DLMA|DVCDT136', log),
            'GUI execution error')
    require(log.splitlines().count('DVE_SELECTED_TESTS: ' + ' '.join(plan['selected'])) == 1, 'GUI selected identities differ')
    summaries = {}
    for stage in ('raw', 'applied', 'reset', 'reloaded', 'final'):
        rows = list(csv.DictReader((out / ('rooted_' + stage + '.csv')).open()))
        require(len(rows) == 1 and rows[0]['Stage'] == stage and
                rows[0]['Scope'] == rows[0]['Token'] == 'ara_tb.dut.i_ara_soc.i_system' and
                rows[0]['GUIPath'] == rows[0]['Name'] == 'i_system', 'Rooted system report identity differs')
        summaries[stage] = {m: rows[0][m] for m in METRICS}
    require(summaries['raw'] == summaries['reset'] == summaries['final'] and
            summaries['applied'] == summaries['reloaded'], 'Raw/reset or applied/reloaded report differs')
    require(all(summaries['raw'][m] == summaries['applied'][m] for m in ('Line', 'Toggle', 'Condition', 'Branch')),
            'Non-FSM coverage changed')
    if plan['population'] == 741:
        official = life.OUT / 'raw741-dve-parent-20261007-01/summary.csv'
        pins[str(official)] = '67356d1bbdf6ceb36a54080c3ac89cd6340897a2538e3b2e6feb4012a54cc7c7'
        current = capture.report.system_row(official)
        require(summaries['raw'] == {m: current[m] for m in METRICS}, 'Not the verified raw741 epoch')
    life.check(pins)
    result = dict(status='FULL741_EXACT_FSM_ADJUSTED_REPORT_VERIFIED' if plan['population'] == 741
                  else 'EXACT_NATIVE_CAPTURE_QUALIFIED_NOT_POPULATION_REPORT',
                  targets=target_count, protected=protected_count, native_records=expected, system=summaries,
                  tests=plan['population'], other_waivers_applied=False, input_pins=pins,
                  source_review_basis='Accepted port2 disabled producer, dispatcher blocked-decode, PTW PMP0 proofs',
                  original_driver_status=status, serialization_order_only_failure_preserved=serialization_order_only,
                  simulations_started=False)
    path = out / 'qualification.json'
    life.save(path, result)
    print(json.dumps(dict(status=result['status'], seal=life.digest(path), system=summaries)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    audit(parser.parse_args().output.absolute())
