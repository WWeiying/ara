#!/usr/bin/env python3
"""Summarize an existing checked aggregate; never admit tests or run EDA."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

METRICS = ('Line', 'Condition', 'Branch', 'FSM', 'Toggle')
TARGETS = {'Line': 90.0, 'Condition': 90.0, 'Branch': 90.0, 'FSM': 90.0}
MODULES = {
    'i_dispatcher': 'RVV dispatch',
    'i_sequencer': 'RVV dependency/issue',
    'i_operand_queues': 'Lane operand queues',
    'i_vlsu': 'Vector memory and custom engines',
    'i_qbs_engine': 'QBS projection',
    'i_akv_engine': 'AKV attention',
    'controller_i': 'CVA6 control',
    'csr_regfile_i': 'CVA6 CSR/privilege',
    'i_cva6_mmu': 'CVA6 MMU',
    'i_itlb': 'Instruction TLB',
    'i_dtlb': 'Data TLB',
    'i_ptw': 'Page-table walker',
}
SYSTEM = 'ara_tb.dut.i_ara_soc.i_system'
VECTOR = SYSTEM + '.i_ara'
SCALAR = SYSTEM + '.i_ariane'
MMU = SCALAR + '.ex_stage_i.lsu_i.gen_mmu.i_cva6_mmu'
# The current admitted image is the four-lane, Sv39, QBS+AKV configuration.
EXPECTED_SCOPES = {
    *[VECTOR + '.gen_lanes[%d].i_lane.i_operand_queues' % lane for lane in range(4)],
    VECTOR + '.i_dispatcher', VECTOR + '.i_sequencer', VECTOR + '.i_vlsu',
    VECTOR + '.i_vlsu.i_qbs_engine', VECTOR + '.i_vlsu.i_akv_engine',
    SCALAR + '.controller_i', SCALAR + '.csr_regfile_i',
    MMU, MMU + '.i_itlb', MMU + '.i_dtlb', MMU + '.i_ptw',
}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def read(path):
    return json.loads(path.read_text())


def hierarchy(path):
    rows, stack = {}, []
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        require(set(('Name', 'Depth', *METRICS)) <= set(reader.fieldnames or []),
                'incomplete DVE CSV schema')
        for row in reader:
            depth = int(row['Depth'])
            require(depth >= 0, 'negative hierarchy depth')
            stack = stack[:depth]
            require(len(stack) == depth, 'missing hierarchy parent')
            stack.append(row['Name'])
            scope = '.'.join(stack)
            require(scope not in rows, 'duplicate hierarchy scope')
            values = {}
            for metric in METRICS:
                value = row[metric]
                if value == 'NA':
                    values[metric] = None
                else:
                    require(value.endswith('%'), 'not a DVE percentage')
                    number = float(value[:-1])
                    require(0 <= number <= 100, 'invalid percentage')
                    values[metric] = number
            rows[scope] = dict(name=row['Name'], values=values)
    require('ara_tb' in rows, 'missing testbench root')
    return rows


def scorecard(baseline, completion=None):
    baseline = baseline.resolve(strict=True)
    collection = read(baseline / 'collection.json')
    if completion is None:
        checkpoint = read(baseline / 'checkpoint.json')
    else:
        completion = completion.resolve(strict=True)
        checkpoint = read(completion / 'checkpoint.json')
        receipt_path = completion / 'completion.json'
        require(checkpoint.get('completion_sha256') == digest(receipt_path),
                'recovery completion receipt drift')
        receipt = read(receipt_path)
        require(receipt.get('schema') == 'gap65-report-only-recovery-v1' and
                receipt.get('status') == 'PASS' and receipt.get('source_runtime') == str(baseline)
                and receipt.get('aggregate_passed') == collection['passed'] == 651 and
                receipt.get('original_evidence_modified') is False and
                receipt['files'].get(str(baseline / 'collection.json')) == digest(baseline / 'collection.json'),
                'foreign/unbound recovery completion')
    require(collection['status'] in ('PASS', 'COMPLETE_WITH_FAILURES') and
            checkpoint.get('coverage_status') == 'COMPLETE' and
            checkpoint.get('aggregate_passed') == collection['passed'],
            'aggregate is not completed/admitted')
    reports = collection['reports']
    paths = [baseline / n for n in ('combined-dve/summary.csv',
             'all-passed-outcomes.json', 'combined-bits.json', 'combined-dve/inputs.txt',
             'combined-dve/waiver_status.json', 'combined-dve/selected_tests.txt')]
    for path in paths:
        require(reports.get(str(path)) == digest(path), 'published report drift: ' + str(path))
    ledger = read(paths[1])
    require(len(ledger) == collection['passed'] and
            len({r['name'] for r in ledger}) == len(ledger) and
            all(r['status'] == 'PASS' and r['passed_only'] is True and
                r['vdb_valid'] is True and r['reused'] is False for r in ledger),
            'unverified/duplicate ledger member')
    vdbs = [r['vdb'] for r in ledger]
    inputs = paths[3].read_text().splitlines()
    require(len(inputs) == len(vdbs) + 1 and inputs[1:] == vdbs and
            len(set(inputs)) == len(inputs) and read(paths[2])['tests'] == vdbs,
            'ledger/bitmap/report membership differs')
    require(paths[5].read_text().splitlines() ==
            [str(Path(r['vdb']).with_suffix('') / r['coverage_test']) for r in ledger],
            'actual DVE selected-test membership differs')
    rows = hierarchy(paths[0])
    modules = []
    for scope, row in rows.items():
        module_name = row['name'].rsplit('.', 1)[-1]
        if module_name not in MODULES:
            continue
        values = row['values']
        gaps = {m: round(max(0.0, target - values[m]), 2)
                for m, target in TARGETS.items() if values[m] is not None}
        measured = all(values[m] is not None for m in ('Line', 'Condition', 'Branch'))
        modules.append(dict(scope=scope, module=module_name, role=MODULES[module_name], raw=values,
            targets=TARGETS, gap_percentage_points=gaps,
            core_metrics_measured=measured,
            raw_target_met=measured and all(v == 0 for v in gaps.values())))
    require({m['scope'] for m in modules} == EXPECTED_SCOPES,
            'missing/foreign critical module or lane; this scorecard requires frozen four-lane image')
    return dict(schema='coverage-closure-scorecard-v1', baseline=str(baseline),
        completion_receipt=str(completion) if completion is not None else None,
        status='TARGET_MET_RAW' if all(m['raw_target_met'] for m in modules) else 'OPEN',
        passed=collection['passed'], global_raw=rows['ara_tb']['values'], modules=modules,
        waiver=read(paths[4]), report_pins={str(p): digest(p) for p in paths},
        interpretation='Reads completed admission evidence; does not re-admit or re-audit '
            'individual tests. Raw FSM values are native DVE arc scores, not reachable-state '
            'coverage. Toggle is diagnostic; no whole-datapath 90% target is asserted. '
            'Any reachable denominator requires separately reviewed, actually applied exclusions. '
            'Threshold attainment is not functional or Linux signoff.')


def markdown(report):
    lines = ['# Critical Module Coverage Targets', '',
        'Completed PASS cases: %d. Status: **%s**.' % (report['passed'], report['status']), '',
        'Raw DVE measurements; 90% targets for line, condition, branch and native FSM arcs.',
        'No reachable denominator is inferred from configuration analysis alone.', '',
        '| Scope | Line | Condition | Branch | FSM arcs | Toggle | Raw target met |',
        '| --- | ---: | ---: | ---: | ---: | ---: | --- |']
    for row in report['modules']:
        cells = [('NA' if row['raw'][m] is None else '%.2f%%' % row['raw'][m]) for m in METRICS]
        lines.append('| `%s` | %s | %s |' %
                     (row['scope'], ' | '.join(cells), 'Yes' if row['raw_target_met'] else 'No'))
    return '\n'.join([*lines, '', report['interpretation'], ''])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--completion', type=Path,
                        help='Independent report-only completion for gap65, not a replacement oracle')
    args = parser.parse_args()
    require(not args.output.exists(), 'new output directory required')
    report = scorecard(args.baseline, args.completion)
    args.output.mkdir(parents=True)
    with (args.output / 'scorecard.json').open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    with (args.output / 'scorecard.md').open('x') as stream:
        stream.write(markdown(report))
    print('%s: %d checked PASS; %d critical hierarchy rows' %
          (report['status'], report['passed'], len(report['modules'])))


if __name__ == '__main__':
    main()
