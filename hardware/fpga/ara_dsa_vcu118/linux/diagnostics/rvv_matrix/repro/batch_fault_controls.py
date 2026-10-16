"""Batch archived failed unit-replay shapes without discarding their individual lineage."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from trace_masks import sha
from trace_fault import unit_shape, segment_shape, strided_shape
from audit_slide import require


def select(roots, report, excluded, layout='unit'):
    require(layout in ('unit', 'segment', 'strided'), 'Unsupported layout')
    resolver = {'unit': unit_shape, 'segment': segment_shape, 'strided': strided_shape}[layout]
    inputs = {c['name']: c for c in report['inputs']['cases']}
    results = {r['name']: r for r in report['results']}
    require(len(inputs) == len(report['inputs']['cases']) and
            len(results) == len(report['results']), 'Duplicate original identity')
    selected = []; seen = set()
    for root, manifest in roots:
        for c in manifest['cases']:
            resolver(manifest, c)
            name = c['name']
            require(name not in seen, 'Duplicate original shape')
            seen.add(name)
            require(name in inputs and inputs[name]['sha256'] == c['sha256'], 'Original ELF differs')
            require(name in results and results[name]['status'] == 'failed', 'No original failure')
            if name not in excluded:
                selected.append((root, c))
    require(set(excluded) <= seen, 'Unknown excluded shape')
    require(selected, 'No remaining shapes')
    return selected


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original', type=Path, action='append', required=True)
    p.add_argument('--exclude', action='append', default=[])
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--cross', required=True)
    p.add_argument('--layout', choices=('unit', 'segment', 'strided'), default='unit')
    a = p.parse_args()
    raw = json.loads(a.report.read_text()); report = raw.get('report', raw)
    selected = select([(r, json.loads((r / 'manifest.json').read_text())) for r in a.original],
                      report, a.exclude, a.layout)
    a.out.mkdir(exist_ok=False)
    binaries = a.out / 'overlay/opt/ara-tests'; binaries.mkdir(parents=True)
    manifest = dict(scope='Three-way replay controls across archived failed shapes', layout=a.layout,
                    original_report_sha256=sha(a.report), excluded=a.exclude,
                    original_failure_equivalence_proven=False, board_reproduction_confirmed=False,
                    cases=[], groups=[])
    for root, original in selected:
        child = a.out / original['name']
        options = [] if a.layout == 'unit' else ['--' + a.layout + '-controls']
        subprocess.run([sys.executable, str(Path(__file__).with_name('trace_fault.py')),
            '--original', str(root), '--report', str(a.report), '--out', str(child),
            '--case', original['name'], '--compare-current-oracle', '--cross', a.cross] + options, check=True)
        cm = json.loads((child / 'manifest.json').read_text())
        manifest['groups'].append(dict(directory=child.name, manifest_sha256=sha(child / 'manifest.json')))
        shutil.copytree(child / 'overlay/opt/ara-tests', child / 'binaries')
        for c in cm['cases']:
            shutil.copy2(child / 'binaries' / c['name'], binaries / c['name'])
            manifest['cases'].append(dict(c, source_group=child.name))
    shutil.copytree(binaries, a.out / 'binaries')
    (a.out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    shutil.copy2(a.report, a.out / 'original_report.json')
    with (a.out / 'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio', '-o', '-H', 'newc', '--owner=0:0'], cwd=a.out / 'overlay',
            input=('opt\nopt/ara-tests\n' + ''.join('opt/ara-tests/' + c['name'] + '\n'
                  for c in manifest['cases'])).encode(), stdout=stream, check=True)
    print('SHAPES', len(selected), 'CONTROL_ELFS', len(manifest['cases']))


if __name__ == '__main__':
    main()
