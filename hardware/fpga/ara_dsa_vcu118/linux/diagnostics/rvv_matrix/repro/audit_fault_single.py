"""Compare measured current-oracle replay trials, not unobserved original tuples."""
import argparse
import json
from pathlib import Path
from audit_slide import require
from audit_fault_controls import summary
from classify_fault import classify
from trace_masks import sha
from trace_fault import unit_shape, segment_shape, strided_shape


def signature(trial):
    require(trial['completed'], 'Incomplete trial has no final signature')
    contexts = []
    for c in trial['contexts']:
        contexts.append(dict(
            **{k: c[k] for k in ('sig', 'code', 'vstart', 'expected_start', 'vl', 'vtype')},
            address_page_offset=c['address'] % 4096,
            expected_address_page_offset=c['expected_address'] % 4096,
            address_delta=c['address'] - c['expected_address'],
            pc_delta=c['pc'] - c['expected_pc']))
    return dict(trigger=trial['trigger'], contexts=contexts,
                returned=trial['returned'], errors=trial['errors'])


def audit(root, report_path):
    m = json.loads((root / 'manifest.json').read_text())
    measured_path = root / 'measured_report.json'
    require(sha(measured_path) == m['trace_report_sha256'], 'Measured report changed')
    measured = json.loads(measured_path.read_text()); measured = measured.get('report', measured)
    require(m['cases'], 'Empty single-trial manifest')
    layout = m.get('diagnostic_layout')
    resolver = strided_shape if layout and layout.get('strided') else segment_shape
    shapes = {(resolver(layout, dict(c, name=c['original_name'])) if layout else
               (unit_shape({}, dict(c, name=c['original_name'])), 1)) for c in m['cases']}
    require(len(shapes) == 1, 'Mixed replay shapes')
    (sew, lmul, _, _, _), fields = shapes.pop()
    trace_name = 'rvv_trace_fault_replay_' + (f'segment_nf{fields}_' if fields > 1 else '') + f'e{sew}_{lmul}'
    if layout and layout.get('strided'):
        parents = {c['original_name'] for c in m['cases']}
        require(len(parents) == 1, 'Mixed stride parents')
        trace_name = 'rvv_trace_fault_replay_' + parents.pop().removeprefix('rvv_fault_replay_')
    trace, = [r for r in measured['results'] if r['name'] == trace_name]
    prior = classify(trace['output'])
    require(prior['incomplete'] == 0, 'Incomplete measured sequence')
    raw = json.loads(report_path.read_text()); report = raw.get('report', raw)
    def index(items):
        result = {x['name']: x for x in items}
        require(len(result) == len(items), 'Duplicate case identity')
        return result
    inputs = index(report['inputs']['cases']); results = index(report['results'])
    index(m['cases'])
    rows = []
    for c in m['cases']:
        name = c['name']
        require(c['scenario_role'] == 'single_current_oracle_trial', 'Unsupported role')
        require(sha(root / 'binaries' / name) == c['sha256'], 'Local ELF changed')
        for file, digest in c['scenario_sources'].items():
            require(sha(root / name / file) == digest, 'Scenario source changed')
        old, = [t for t in prior['trials'] if t['trigger'] == c['selected_trial']]
        require(old == c['measured_trial'], 'Stored trial differs from measured report')
        require(old['errors'] > 0, 'Selected trial was not a failure')
        r = results.get(name)
        if name in inputs:
            require(inputs[name]['sha256'] == c['sha256'], 'Deployed ELF differs')
        require(r is None or name in inputs, 'Result without deployed identity')
        row = dict(name=name, status=r['status'] if r else 'not_started',
                   confirmed=False, expected_signature=signature(old))
        if r and r['status'] == 'failed' and r.get('exit_code') == 1:
            observed = classify(r.get('output', ''))
            if observed['completed'] == 1 and observed['incomplete'] == 0:
                t, = observed['trials']
                row['observed_signature'] = signature(t)
                s = summary(r['output'])
                row['confirmed'] = (s == dict(verdict='FAIL', sew=sew, cases=1,
                    signals=t['returned']['faults'], errors=t['errors']) and
                    row['observed_signature'] == row['expected_signature'])
        rows.append(row)
    return dict(scope='Single trial versus measured current-oracle sequence', cases=rows,
                confirmed=sum(r['confirmed'] for r in rows),
                pending=sum(not r['confirmed'] for r in rows),
                original_failure_equivalence_proven=False, internal_rtl_root_cause_proven=False,
                manifest_sha256=sha(root / 'manifest.json'), report_sha256=sha(report_path),
                measured_report_sha256=sha(measured_path))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('root', 'report', 'out'):
        p.add_argument('--' + key, type=Path, required=True)
    a = p.parse_args()
    result = audit(a.root, a.report)
    a.out.mkdir(exist_ok=False)
    (a.out / 'sampled_report.json').write_bytes(a.report.read_bytes())
    (a.out / 'symptoms.json').write_text(json.dumps(result, indent=2) + '\n')
    print('CONFIRMED', result['confirmed'], 'PENDING', result['pending'])


if __name__ == '__main__':
    main()
