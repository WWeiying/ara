"""Audit three-way replay controls without asserting original source equivalence."""
import argparse
import json
from pathlib import Path
import re
from trace_masks import sha
from audit_slide import require
from classify_fault import classify


def summary(output):
    rows = []
    for line in output.splitlines():
        match = re.fullmatch(r'RVV_FAULT_REPLAY_(PASS|FAIL) sew=(\d+) cases=(\d+) signals=(\d+) errors=(\d+)', line)
        if match:
            rows.append(dict(verdict=match[1], **dict(zip(('sew', 'cases', 'signals', 'errors'),
                                                        map(int, match.groups()[1:])))))
    require(len(rows) <= 1, 'Multiple replay summaries')
    return rows[0] if rows else None


def audit(root, original_path, report_path):
    m = json.loads((root / 'manifest.json').read_text())
    require(sha(original_path) == m['original_report_sha256'], 'Original report changed')
    original = json.loads(original_path.read_text()); original = original.get('report', original)
    raw = json.loads(report_path.read_text()); report = raw.get('report', raw)
    def index(items):
        data = {x['name']: x for x in items}
        require(len(data) == len(items), 'Duplicate case identity')
        return data
    original_inputs = index(original['inputs']['cases']); original_results = index(original['results'])
    inputs = index(report['inputs']['cases']); results = index(report['results'])
    rows = []
    for case in m['cases']:
        name, ancestor = case['name'], case['original_name']
        require(sha(root / 'binaries' / name) == case['sha256'], 'Candidate ELF changed')
        require(original_inputs[ancestor]['sha256'] == case['original_elf_sha256'], 'Original ELF differs')
        if case['scenario_role'] == 'immutable_original_control':
            require(case['sha256'] == case['original_elf_sha256'], 'Original control is not immutable')
        directory = root / case.get('source_directory', name)
        for file, digest in case.get('scenario_sources', {}).items():
            require(sha(directory / file) == digest, 'Candidate source changed')
        result = results.get(name)
        if name in inputs:
            require(inputs[name]['sha256'] == case['sha256'], 'Deployed ELF differs')
        require(result is None or name in inputs, 'Result has no deployed identity')
        row = dict(name=name, role=case['scenario_role'], elf_sha256=case['sha256'],
                   status=result['status'] if result else 'not_started',
                   aggregate_original_symptom_matches=False)
        if result:
            row['summary'] = summary(result.get('output', ''))
            parent = original_results[ancestor]
            row['original_summary'] = summary(parent.get('output', ''))
            row['aggregate_original_symptom_matches'] = (
                result['status'] == parent['status'] == 'failed' and
                result.get('exit_code') == parent.get('exit_code') == 1 and
                row['summary'] is not None and row['summary'] == row['original_summary'])
            if case['scenario_role'] == 'original_sequence_trace':
                row['diagnostic'] = classify(result.get('output', ''))
                if row['summary'] is not None:
                    require(row['diagnostic']['incomplete'] == 0 and
                            row['diagnostic']['completed'] == row['summary']['cases'],
                            'Trace count and summary differ')
                    require(sum(t['errors'] for t in row['diagnostic']['trials']) == row['summary']['errors'],
                            'Trace error total and summary differ')
        rows.append(row)
    return dict(scope='Three independent controls; matching aggregate totals do not prove per-trial equivalence',
                cases=rows, original_failure_equivalence_proven=False,
                original_source_equivalence_confirmed=m.get('original_source_equivalence_confirmed', False),
                manifest_sha256=sha(root / 'manifest.json'), original_report_sha256=sha(original_path),
                report_sha256=sha(report_path))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('root', 'original', 'report', 'out'):
        p.add_argument('--' + key, type=Path, required=True)
    a = p.parse_args()
    result = audit(a.root, a.original, a.report)
    a.out.mkdir(exist_ok=False)
    (a.out / 'sampled_report.json').write_bytes(a.report.read_bytes())
    (a.out / 'symptoms.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps([dict(name=c['name'], status=c['status'],
                          aggregate_match=c['aggregate_original_symptom_matches']) for c in result['cases']]))


if __name__ == '__main__':
    main()
