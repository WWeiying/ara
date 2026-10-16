"""Audit measured fflags reproductions with deployed ELF and source identities."""
import argparse
import json
from pathlib import Path
from audit_slide import require
from match_fp_compare import compare
from trace_masks import sha


def index(rows):
    result = {r['name']: r for r in rows}
    require(len(result) == len(rows), 'Duplicate case identity')
    return result


def audit(root, report_path):
    manifest = json.loads((root/'manifest.json').read_text())
    original_path = root/'original_board_report.json'
    require(sha(original_path) == manifest['original_report_sha256'], 'Original report changed')
    original = json.loads(original_path.read_text())
    original = original.get('report', original)
    report = json.loads(report_path.read_text())
    report = report.get('report', report)
    old_inputs = index(original['inputs']['cases'])
    old_results = index(original['results'])
    inputs, results = index(report['inputs']['cases']), index(report['results'])
    require(manifest['cases'], 'Empty candidate manifest')
    index(manifest['cases'])
    rows = []
    for case in manifest['cases']:
        name, parent = case['name'], case['original_name']
        require(old_inputs[parent]['sha256'] == case['original_elf_sha256'], 'Original ELF differs')
        require(sha(root/'binaries'/name) == case['sha256'], 'Candidate ELF changed')
        for file, digest in case['scenario_sources'].items():
            require(sha(root/name/file) == digest, 'Candidate source changed')
        require(sha(root/name/'scenario.S') == case['archived_assembly_sha256'],
                'Archived assembly differs')
        if name in inputs:
            require(inputs[name]['sha256'] == case['sha256'], 'Deployed candidate differs')
        result = results.get(name)
        require(result is None or name in inputs, 'Result without deployed identity')
        matched = (compare(old_results[parent], result, case['original_failure_detail'])
                   if result else dict(confirmed=False, reason='Not started'))
        rows.append(dict(name=name, original_name=parent,
                         status=result['status'] if result else 'not_started',
                         oracle_provenance=case['oracle_provenance'], **matched))
    return dict(cases=rows, confirmed=sum(r['confirmed'] for r in rows),
                pending=sum(not r['confirmed'] for r in rows),
                scope='Same measured stimulus and fflags mismatch, not original C-source equivalence',
                original_c_source_equivalence_proven=False,
                internal_rtl_root_cause_proven=False,
                manifest_sha256=sha(root/'manifest.json'), report_sha256=sha(report_path),
                original_report_sha256=sha(original_path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('root', 'report', 'out'):
        parser.add_argument('--'+key, type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.root, args.report)
    args.out.mkdir(exist_ok=False)
    (args.out/'sampled_report.json').write_bytes(args.report.read_bytes())
    (args.out/'symptoms.json').write_text(json.dumps(result, indent=2)+'\n')
    print('CONFIRMED', result['confirmed'], 'PENDING', result['pending'])


if __name__ == '__main__':
    main()
