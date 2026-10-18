#!/usr/bin/env python3
"""Validate matched VMFPU stream-pruning area/timing evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def field(text, label):
    match = re.search(re.escape(label) + r'\s*:\s*([-+\d.eE]+)', text)
    if not match:
        raise ValueError('Missing field: ' + label)
    return float(match[1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    manifest = json.loads((directory / 'manifest.json').read_text())
    for name, digest in manifest['new_sources'].items():
        assert sha(Path(name)) == digest, 'Local source changed'
    origin = Path(manifest['config_function_origin'])
    assert sha(origin) == manifest['config_function_origin_sha256']
    reference = origin
    while reference.name != 'sources':
        reference = reference.parent
        assert reference != reference.parent, 'Missing frozen reference root'
    reference = reference.parent
    assert sha(reference / 'manifest.json') == manifest['reference_manifest_sha256']
    frozen = json.loads((reference / 'manifest.json').read_text())
    for item in frozen['frozen_files']:
        assert sha(reference / item['snapshot']) == item['sha256']
    for item in manifest['libraries']:
        assert sha(Path(item['path'])) == item['sha256']
    lists = [(directory / mode / 'filelist').read_text().splitlines()
             for mode in ['baseline', 'scalar']]
    assert lists[1] == lists[0] + ['+define+ARA_RED_PRUNE_LEGACY_FP_STREAM=1']
    scripts = [(directory / mode / 'run.tcl').read_text().replace(
        str(directory / mode / 'filelist'), 'MATCHED_FILELIST')
        for mode in ['baseline', 'scalar']]
    assert scripts[0] == scripts[1], 'Constraints or synthesis options differ'
    rows = []
    for mode in ['baseline', 'scalar']:
        state = manifest['results'].get(mode, {})
        assert state.get('complete') and state.get('returncode') == 0, 'Incomplete ' + mode
        run = directory / mode
        log = (run / 'console.log').read_text()
        assert sha(run / 'console.log') == state['log_sha256']
        assert 'VMFPU_STREAM_PPA_COMPLETE' in log.splitlines()
        assert not re.search(r'^Error:', log, re.M)
        timing = (run / 'timing.rpt').read_text()
        hold = (run / 'hold.rpt').read_text()
        qor = (run / 'qor.rpt').read_text()
        slacks = lambda text: [float(s) for s in re.findall(
            r'slack\s+\((?:MET|VIOLATED)\)\s+([-+\d.]+)', text)]
        assert slacks(timing) and slacks(hold), 'Missing timing paths'
        rows.append({'mode': mode,
                     'area_um2': field((run / 'area.rpt').read_text(), 'Total cell area'),
                     'worst_reported_setup_slack_ns': min(slacks(timing)),
                     'worst_reported_hold_slack_ns': min(slacks(hold)),
                     'hold_violations': field(qor, 'No. of Hold Violations'),
                     'report_hashes': {name: sha(run / name) for name in
                         ['area.rpt', 'qor.rpt', 'timing.rpt', 'hold.rpt', 'check_timing.rpt']}})
    result = {'complete': True, 'results': rows,
              'area_saved_um2': rows[0]['area_um2'] - rows[1]['area_um2'],
              'area_saved_percent': 100 * (1 - rows[1]['area_um2'] / rows[0]['area_um2']),
              'scope': manifest['scope'],
              'limits': 'Local synthesis; dynamic Lane ID; no integrated area or Fmax claim. Functional and cycle evidence is separate.'}
    (directory / 'comparison.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
