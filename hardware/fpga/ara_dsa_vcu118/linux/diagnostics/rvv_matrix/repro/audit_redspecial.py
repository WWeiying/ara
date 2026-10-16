"""Compare measured reduction flags, with exact deployed ELF provenance."""
import argparse
import json
from pathlib import Path
import re
from trace_masks import sha
from audit_slide import require


KEYS = {'scenario', 'op', 'vl', 'mask', 'frm', 'flags', 'expected_flags'}


def details(output):
    rows = []
    for line in output.splitlines():
        if not line.startswith('RVV_FP_REDSPECIAL_DETAIL '):
            continue
        tokens = line.split()[1:]
        if any(re.fullmatch(r'\w+=\d+', token) is None for token in tokens):
            raise ValueError('Malformed reduction detail')
        pairs = [token.split('=') for token in tokens]
        row = {k: int(v) for k, v in pairs}
        require(len(row) == len(pairs) and KEYS <= row.keys(), 'Incomplete or duplicate reduction fields')
        rows.append(row)
    return rows


def compare(original, small, selected):
    targets = details(selected)
    require(len(targets) == 1, 'Expected one original reduction detail')
    target = targets[0]
    require(target['flags'] != target['expected_flags'], 'Selected detail is not a flags mismatch')
    def matches(result):
        return (result.get('status') == 'failed' and result.get('exit_code') == 1 and
                any(all(row[k] == target[k] for k in KEYS) for row in details(result.get('output', ''))))
    return dict(confirmed=matches(original) and matches(small), tuple=target,
                raw_result_bits_equivalence_proven=False,
                internal_rtl_root_cause_proven=False)


def audit(root, original, report_path):
    m = json.loads((root / 'manifest.json').read_text())
    require(sha(original) == m['original_report_sha256'], 'Original report changed')
    parent = json.loads(original.read_text()); parent = parent.get('report', parent)
    raw = json.loads(report_path.read_text()); report = raw.get('report', raw)
    def indexed(items):
        out = {c['name']: c for c in items}
        require(len(out) == len(items), 'Duplicate case identity')
        return out
    inputs = indexed(report['inputs']['cases']); results = indexed(report['results'])
    old_inputs = indexed(parent['inputs']['cases']); old_results = indexed(parent['results'])
    rows = []
    for case in m['cases']:
        name, ancestor = case['name'], case['original_name']
        require(sha(root / 'binaries' / name) == case['sha256'], 'Candidate ELF changed')
        require(old_inputs[ancestor]['sha256'] == case['original_elf_sha256'] ==
                sha(root / name / 'original_rebuilt.elf'), 'Original ELF lineage mismatch')
        for file, digest in case['scenario_sources'].items():
            require(sha(root / name / file) == digest, 'Candidate source changed')
        if name in inputs:
            require(inputs[name]['sha256'] == case['sha256'], 'Deployed ELF mismatch')
        result = results.get(name)
        require(result is None or name in inputs, 'Result has no deployed identity')
        row = dict(name=name, original_name=ancestor, original_elf_sha256=case['original_elf_sha256'],
                   reduced_elf_sha256=case['sha256'], confirmed=False,
                   status=result['status'] if result else 'not_started')
        if result:
            row.update(compare(old_results[ancestor], result, case['original_failure_detail']))
        rows.append(row)
    return dict(scope='Recorded reduction trigger and flag mismatch only; raw result bits were not printed',
                cases=rows, confirmed=sum(r['confirmed'] for r in rows),
                pending=sum(r['status'] in ('running', 'not_started') for r in rows),
                manifest_sha256=sha(root / 'manifest.json'), original_report_sha256=sha(original),
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
    print(json.dumps({k: result[k] for k in ('confirmed', 'pending')}))


if __name__ == '__main__':
    main()
