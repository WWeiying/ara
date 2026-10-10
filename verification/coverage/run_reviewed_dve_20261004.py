#!/usr/bin/env python3
"""Apply the exact offline-reviewed waivers to an admitted current-image corpus.

This is report-only: no VCS run, no input VDB edits, no frozen helper edits.
Raw scores must round-trip unchanged; adjusted scores come only from DVE.
"""
import argparse
import copy
import csv
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

import coverage_evidence

HERE = Path(__file__).resolve().parent
REVIEW = HERE / 'reviewed_20261004'
spec = importlib.util.spec_from_file_location('reviewed_native_audit', REVIEW / 'audit_readonly.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
require = audit.require


def native_points(policy):
    lines = []
    for point in policy['allowed_points']:
        lines.extend(['CHECKSUM: "' + ' '.join(point['checksum']) + '"',
                      'INSTANCE: ' + point['scope'],
                      'ANNOTATION: "Reviewed constant input; see bound audit.json"',
                      point['native_directive']])
    text = '\n'.join(lines) + '\n'
    require(audit.native_entries(text) == policy['allowed_points'],
            'Native point serialization differs from exact review')
    return text


def validate_native(text, policy, observers):
    actual = audit.native_entries(text)
    expected = list(policy['allowed_points'])
    if observers:
        expected.extend(dict(scope=p['scope'], point='INSTANCE', checksum=p['checksum'],
                             native_directive=None, nativepointchecksum=None,
                             native_signature=None) for p in policy['allowed_observers'])
    key = lambda p: (p['scope'], p['point'])
    require(sorted(actual, key=key) == sorted(expected, key=key),
            'DVE native saved exclusions differ in scope, identity or signature')
    return {(p['scope'], p['point']) for p in actual}


def guard_review():
    policy, record = audit.jread(REVIEW / 'policy.json'), audit.jread(REVIEW / 'audit.json')
    audit.validate_policy(policy, record)
    require(audit.sha(REVIEW / 'audit.json') == policy['audit_sha256'], 'Review hash differs')
    pins = {}
    for entries in record['evidence'].values():
        for item in entries:
            path, digest = item['path'], item['sha256']
            require(path not in pins or pins[path] == digest, 'Contradictory review input')
            pins[path] = digest
    audit.verify_hashes(pins)
    design = audit.Design(Path(record['identity']['design_vdb']))
    require(audit.sha(design.db / 'design/verilog.design.xml') == policy['design_sha256'],
            'Reviewed design differs')
    for point in record['points']:
        require(design.point(point) == point['current'], 'Reviewed point identity differs')
    for observer in record['observers']:
        scope = observer['scope']
        require(design.source(scope) == observer['current'], 'Reviewed observer differs')
        require(not any(p.startswith(scope + '.') for p in design.hierarchy),
                'Recursive observer gained descendants')
        for metric, shape in observer['metric_shapes'].items():
            require(audit.tree_digest(design.definition(scope, metric)) == shape['sha256'],
                    'Observer metric shape differs')
    for name in ('audit.json', 'policy.json', 'audit_readonly.py'):
        pins[str(REVIEW / name)] = audit.sha(REVIEW / name)
    return policy, record, pins


def admitted_inputs(baseline, design):
    proof = coverage_evidence.Evidence()
    plan = proof.plan(baseline)
    require(Path(plan['design_vdb']) == design, 'Corpus uses another compiled design')
    rows = proof.ledger(baseline, plan['image'])
    inputs = proof.pin(baseline / 'combined-dve/inputs.txt')
    require(inputs.read_text().splitlines() == [str(design), *[r['vdb'] for r in rows]],
            'Corpus input membership differs from admitted ledger')
    for row in rows:
        require(row['status'] == 'PASS' and row['passed_only'] is True and
                row['vdb_valid'] is True and row['vdb_rejection'] is None and
                row['returncode'] == 0, 'Non-passing test in report')
        proof.hashes(row['vdb_files'])
    return rows, inputs, proof.files


def snapshot(bundle, policy, record, pins, design, baseline):
    bundle.mkdir(parents=True)
    (bundle / 'dve_hierarchy').mkdir()
    (bundle / 'waivers').mkdir()
    for target, source in {
        'waiver_base.py': HERE / 'prepare_dve_waivers.py',
        'prepare_dve_waivers.py': REVIEW / 'prepare_native.py',
        'audit_readonly.py': REVIEW / 'audit_readonly.py',
        'dve_waivers.tcl': HERE / 'dve_waivers.tcl',
        'dve_hierarchy/run_dve_coverage.sh': HERE / 'dve_hierarchy/run_dve_coverage.sh',
        'dve_hierarchy/export_dve_coverage.tcl': HERE / 'dve_hierarchy/export_dve_coverage.tcl',
    }.items():
        shutil.copyfile(source, bundle / target)
        pins[str(source)] = audit.sha(source)
    (bundle / 'waivers/operand_flush.el').write_text(native_points(policy))
    shapes = {p.name: audit.sha(p) for p in sorted((design / 'snps/coverage/db/shape').iterdir())
              if p.is_file()}
    context = dict(policy=policy, observers=record['observers'], pins=pins,
                   design=str(design), shape_files=shapes,
                   raw_reference=str(baseline / 'combined-dve/summary.csv'))
    (bundle / 'context.json').write_text(json.dumps(context, indent=2) + '\n')
    hashes = {str(p.relative_to(bundle)): audit.sha(p) for p in sorted(bundle.rglob('*'))
              if p.is_file()}
    (bundle / 'snapshot.json').write_text(json.dumps(hashes, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    args = parser.parse_args()
    output, baseline = args.output.resolve(), args.baseline.resolve(strict=True)
    bundle = Path(str(output) + '.tools')
    require(not output.exists() and not bundle.exists(), 'Fresh output/snapshot required')
    policy, record, pins = guard_review()
    print('Reviewed 94 exact points and 10 observer identities: PASS', flush=True)
    design = Path(record['identity']['design_vdb'])
    rows, inputs, admitted = admitted_inputs(baseline, design)
    pins.update(admitted)
    # Re-check unreachable points against ALL admitted tests, not just the old
    # 625-test review. This rejects an observed hit rather than excluding it.
    selected = copy.deepcopy(record['points'])
    audit.merge_selected([Path(r['vdb']) for r in rows], selected,
                         {p: h for r in rows for p, h in r['vdb_files'].items()})
    pins[str(Path(__file__).resolve())] = audit.sha(__file__)
    snapshot(bundle, policy, record, pins, design, baseline)
    print(f'Native DVE export: {len(rows)} checked PASS, report-only', flush=True)
    result = subprocess.call(['bash', str(bundle / 'dve_hierarchy/run_dve_coverage.sh'),
                              str(output), '--inputs-file', str(inputs)],
                             env=dict(os.environ, DVE_WAIVERS='auto'))
    if result:
        return result
    status = audit.jread(output / 'waiver_status.json')
    require(status['status'] == 'APPLIED', 'Native application incomplete')
    validate_native((output / 'exclusions.el').read_text(), policy, observers=True)
    with (output / 'summary.csv').open() as stream:
        raw = list(csv.DictReader(stream))
    with (baseline / 'combined-dve/summary.csv').open() as stream:
        require(raw == list(csv.DictReader(stream)), 'Raw report changed during waiver export')
    audit.verify_hashes(pins)
    print(f'APPLIED: {len(rows)} PASS; raw report unchanged; exact 94 points + 10 observers', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
