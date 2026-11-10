#!/usr/bin/env python3
"""Scoped console-prefix repair; preserve matrix01 and every original check."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import types

HERE = Path(__file__).resolve().parent
ORIGINAL = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage2_matrix_vcs_20261109_01')
LEGACY_SHA = '573cd0fcb24c4a97e636291e5a1e5becec6019c5ef4480922790f248269a63cf'
PINS_SHA = '239b399a3b948390188b22873b04ab2472328f1e471020baa0a6c2aa5c21e004'
REPORT_SHA = 'b44c526e7e2dfda17b145fbf6045e5eab026c5e95a87a25ae97d813222c1db4d'
SCHEMAS = {
    'STAGE2_MATRIX_COMMAND ': 'seq cooperative m n profile success fault native_issues native_useful native_products loan_issues loan_useful loan_products loan_returns latency',
    'STAGE2_MATRIX_RESET ': 'seq native_issues loan_issues loan_returns',
    'STAGE2_MATRIX_LENDERS_DONE ': 'commands native_issues loan_issues loan_returns reset_commands reset_flushed latency instances scope',
    'QBS phase ': 'case setup activation weight compute overlap drain scheduler commit terminal',
    'QBS FP probe ': 'case blocked sparse_slot conflict issued no_eligible backpressure occupancy_max full_cycles cast_issue dual_issue half_issue',
    'QBS traffic ': 'case weight activation payload ranges dot prefetch_wait',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def legacy():
    path = HERE / 'run_matrix.py'
    if sha(path) != LEGACY_SHA:
        raise ValueError('Unreviewed original checker')
    spec = importlib.util.spec_from_file_location('matrix01_checker', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_fields(line):
    # Strip an exact record prefix, not arbitrary non-field words/punctuation.
    matches = [prefix for prefix in SCHEMAS if line.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError('Unknown record prefix')
    prefix, = matches
    result = {}
    for token in line[len(prefix):].split():
        match = re.fullmatch(r'([a-z_]+)=([0-9]+|engine_not_soc)', token)
        if not match or match[1] in result:
            raise ValueError('Malformed/duplicate log field: ' + token)
        key, value = match.groups()
        if key == 'scope':
            if value != 'engine_not_soc':
                raise ValueError('Wrong scope')
            result[key] = value
        elif not value.isdecimal():
            raise ValueError('Non-numeric counter')
        else:
            result[key] = int(value)
    if set(result) != set(SCHEMAS[prefix].split()):
        raise ValueError('Missing/unknown record fields')
    return result


def check_log(text, cases, cooperative, suite):
    old = legacy()
    # An isolated globals dictionary changes only the field tokenizer. No edit
    # or monkey-patch of the sealed module, checker code or canonical SV bench.
    fixed = types.FunctionType(old.check_log.__code__,
                               {**vars(old), 'fields': parse_fields}, 'check_log')
    result = fixed(text, cases, cooperative, suite)
    if suite != 'synthetic':
        expected = [case['id'] for case in cases]
        for key in ('phases', 'fp', 'traffic'):
            if [row['case'] for row in result[key]] != expected:
                raise ValueError('Missing/duplicate original probe records: ' + key)
    return result


def audit_original(original=ORIGINAL):
    old = legacy()
    if sha(original / 'source-pins.json') != PINS_SHA or sha(original / 'report.json') != REPORT_SHA:
        raise ValueError('Not the preserved matrix01 failure')
    report = json.loads((original / 'report.json').read_text())
    if (report['state'], report['error']) != ('FAIL', 'Malformed/duplicate log field'):
        raise ValueError('Original failure changed')
    source_pins = json.loads((original / 'source-pins.json').read_text())
    old.verify(source_pins)
    for image in report['images'].values():
        old.verify(image)
    service = original / 'service.log'
    for name, expected in report['artifacts'].items():
        if Path(name) == service:
            terminal = f'STAGE2_MATRIX_FAIL {original / "report.json"}\n'.encode()
            data = service.read_bytes()
            if not data.endswith(terminal) or hashlib.sha256(data[:-len(terminal)]).hexdigest() != expected:
                raise ValueError('Unexpected service-log change')
        elif sha(name) != expected:
            raise ValueError('Original artifact drift: ' + name)
    config = json.loads((original / 'selection.json').read_text())
    results = {}
    checked = (('synthetic', 'baseline', 0), ('synthetic', 'candidate', 1), ('context', 'baseline', 0))
    for suite, arm, enable in checked:
        log = original / arm / f'{suite}.log'
        vector = Path(config['vectors'][suite][arm])
        results[f'{suite}_{arm}'] = check_log(log.read_text(), old.vectors(vector.read_text()), enable, suite)
    try:
        old.check_log((original / 'baseline/context.log').read_text(),
                      old.vectors(Path(config['vectors']['context']['baseline']).read_text()), 0, 'context')
    except ValueError as exc:
        if str(exc) != 'Malformed/duplicate log field':
            raise
    else:
        raise ValueError('Did not reproduce the original parser failure')
    old.verify(source_pins)
    for image in report['images'].values():
        old.verify(image)
    if sha(original / 'report.json') != REPORT_SHA:
        raise ValueError('Original report changed during audit')
    evidence = {str(original / name): sha(original / name) for name in ('report.json', 'status.json', 'source-pins.json', 'selection.json', 'service.log')}
    for suite, arm, _ in checked:
        for path in (original / arm / f'{suite}.log', Path(config['vectors'][suite][arm])):
            evidence[str(path)] = sha(path)
    return dict(state='OFFLINE_RECHECK_PASS_PARTIAL', original_worker_state='FAIL',
                original_report_sha256=REPORT_SHA, original_report_preserved=True,
                explanation='Exact multi-word record prefixes; no numeric/RTL/image change',
                service_log_note='Original artifact hash predates its one exact final FAIL line; prefix hash verified',
                source_pins_checked=len(source_pins), image_pins_checked={k: len(v) for k, v in report['images'].items()},
                original_static_artifacts_match=True, original_parser_failure_reproduced=True,
                runs=results, evidence_pins=evidence,
                not_executed=['context_candidate', 'm4a_both', 'm4b_both', 'm8a_both', 'm8b_both'],
                scope='engine_not_soc; not a completed cooperative M8/performance gate')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', type=Path, default=ORIGINAL)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(state='FAIL', original_worker_state='FAIL')
    try:
        report = audit_original(args.original.resolve())
    except Exception as exc:
        report['error'] = str(exc)
    report['checker_pins'] = {str(p): sha(p) for p in (Path(__file__), HERE / 'test_check_matrix_v2.py', HERE / 'run_matrix.py')}
    legacy().save(args.output / 'report.json', report)
    print(json.dumps({k: report[k] for k in ('state', 'original_worker_state')}))
    return int(report['state'] != 'OFFLINE_RECHECK_PASS_PARTIAL')


if __name__ == '__main__':
    raise SystemExit(main())
