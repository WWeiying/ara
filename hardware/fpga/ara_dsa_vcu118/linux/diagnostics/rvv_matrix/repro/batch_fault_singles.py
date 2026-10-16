"""Batch measured single-trial reductions without losing shape-level evidence."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from audit_fault_controls import audit
from audit_slide import require
from trace_masks import sha


def select(groups, excluded):
    names = [name for name, proof in groups]
    require(len(set(names)) == len(names), 'Duplicate group')
    require(set(excluded) <= set(names), 'Unknown excluded group')
    selected = []
    for name, proof in groups:
        require(Path(name).name == name and name not in ('.', '..'), 'Unsafe group name')
        if name in excluded:
            continue
        rows = proof['cases']
        require(len(rows) == 3 and all(r['aggregate_original_symptom_matches'] for r in rows),
                'Incomplete or mismatched control group: ' + name)
        selected.append(name)
    require(selected, 'No groups selected')
    return selected


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('controls', 'report', 'out'):
        p.add_argument('--' + key, type=Path, required=True)
    p.add_argument('--exclude', action='append', default=[])
    p.add_argument('--cross', required=True)
    a = p.parse_args()
    source = json.loads((a.controls / 'manifest.json').read_text())
    original = a.controls / 'original_report.json'
    checked = []
    for group in source['groups']:
        name = group['directory']
        require(Path(name).name == name and name not in ('.', '..'), 'Unsafe control directory')
        child = a.controls / name
        require(sha(child / 'manifest.json') == group['manifest_sha256'], 'Control group changed')
        checked.append((name, audit(child, original, a.report)))
    selected = select(checked, a.exclude)
    a.out.mkdir(exist_ok=False)
    shutil.copy2(a.report, a.out / 'controls_board_report.json')
    shutil.copy2(original, a.out / 'original_report.json')
    binaries = a.out / 'overlay/opt/ara-tests'; binaries.mkdir(parents=True)
    manifest = dict(scope='Single measured current-oracle trials across shapes',
                    original_failure_equivalence_proven=False, board_reproduction_confirmed=False,
                    controls_manifest_sha256=sha(a.controls / 'manifest.json'),
                    measured_report_sha256=sha(a.report), excluded=a.exclude, cases=[], groups=[])
    for name in selected:
        child = a.out / name
        subprocess.run([sys.executable, str(Path(__file__).with_name('reduce_fault.py')),
            '--controls', str(a.controls / name), '--original-report', str(original),
            '--trace-report', str(a.out / 'controls_board_report.json'), '--out', str(child),
            '--cross', a.cross], check=True)
        cm = json.loads((child / 'manifest.json').read_text())
        manifest['groups'].append(dict(directory=name, manifest_sha256=sha(child / 'manifest.json')))
        shutil.copytree(child / 'overlay/opt/ara-tests', child / 'binaries')
        for c in cm['cases']:
            require(not (binaries / c['name']).exists(), 'Duplicate single trial')
            shutil.copy2(child / 'binaries' / c['name'], binaries / c['name'])
            manifest['cases'].append(dict(c, source_group=name))
    shutil.copytree(binaries, a.out / 'binaries')
    (a.out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    with (a.out / 'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio', '-o', '-H', 'newc', '--owner=0:0'], cwd=a.out / 'overlay',
            input=('opt\nopt/ara-tests\n' + ''.join('opt/ara-tests/' + c['name'] + '\n'
                  for c in manifest['cases'])).encode(), stdout=stream, check=True)
    print('SHAPES', len(selected), 'SINGLE_ELFS', len(manifest['cases']))


if __name__ == '__main__':
    main()
