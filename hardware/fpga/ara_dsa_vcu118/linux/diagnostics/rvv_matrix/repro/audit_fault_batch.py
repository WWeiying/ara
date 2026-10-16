"""Audit every child of a replay-single batch, retaining incomplete cases."""
import argparse
import json
from pathlib import Path
import shutil
from audit_fault_single import audit as audit_single
from audit_slide import require
from trace_masks import sha


def audit(root, report):
    m = json.loads((root / 'manifest.json').read_text())
    require(m['groups'] and m['cases'], 'Empty batch')
    require(len({c['name'] for c in m['cases']}) == len(m['cases']), 'Duplicate batch case')
    expected = []; groups = []; seen = set()
    for g in m['groups']:
        name = g['directory']
        require(Path(name).name == name and name not in ('.', '..'), 'Unsafe group directory')
        require(name not in seen, 'Duplicate batch group'); seen.add(name)
        child = root / name
        require(sha(child / 'manifest.json') == g['manifest_sha256'], 'Child manifest changed')
        cm = json.loads((child / 'manifest.json').read_text())
        require(cm['trace_report_sha256'] == m['measured_report_sha256'], 'Child measured report differs')
        for c in cm['cases']:
            require(Path(c['name']).name == c['name'] and c['name'] not in ('.', '..'), 'Unsafe case name')
            require(sha(root / 'binaries' / c['name']) == c['sha256'], 'Batch ELF changed')
            expected.append(dict(c, source_group=name))
        groups.append(dict(directory=name, proof=audit_single(child, report)))
    require(expected == m['cases'], 'Batch and child membership differ')
    require(sha(root / 'controls_board_report.json') == m['measured_report_sha256'],
            'Batch measured report changed')
    return dict(groups=groups, total=len(expected),
                confirmed=sum(g['proof']['confirmed'] for g in groups),
                pending=sum(g['proof']['pending'] for g in groups),
                manifest_sha256=sha(root / 'manifest.json'), report_sha256=sha(report),
                original_failure_equivalence_proven=False, internal_rtl_root_cause_proven=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('root', 'report', 'out'):
        p.add_argument('--' + key, type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(exist_ok=False)
    frozen = a.out / 'sampled_report.json'
    shutil.copy2(a.report, frozen)
    checked = audit(a.root, frozen)
    for g in checked['groups']:
        child = a.out / g['directory']; child.mkdir()
        shutil.copy2(frozen, child / 'sampled_report.json')
        (child / 'symptoms.json').write_text(json.dumps(g['proof'], indent=2) + '\n')
    (a.out / 'symptoms.json').write_text(json.dumps(checked, indent=2) + '\n')
    print('CONFIRMED', checked['confirmed'], 'PENDING', checked['pending'], 'TOTAL', checked['total'])


if __name__ == '__main__':
    main()
