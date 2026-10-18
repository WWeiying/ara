#!/usr/bin/env python3
"""Validate root/nonroot requester arithmetic-forwarding ablations."""
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
    references = set()
    for line in (directory/'filelist').read_text().splitlines():
        if not line.startswith('/'):
            continue
        for parent in Path(line).parents:
            if parent.name=='sources' and (parent.parent/'manifest.json').is_file():
                if sha(parent.parent/'manifest.json')==manifest['reference_manifest_sha256']:
                    references.add(parent.parent)
    assert len(references)==1,'Missing or ambiguous frozen synthesis reference'
    reference=references.pop()
    assert sha(reference / 'manifest.json') == manifest['reference_manifest_sha256']
    frozen = json.loads((reference / 'manifest.json').read_text())
    for item in frozen['frozen_files']:
        assert sha(reference / item['snapshot']) == item['sha256']
    for item in manifest['libraries']:
        assert sha(Path(item['path'])) == item['sha256']
    assert manifest['mechanism']=='arithmetic_forward'
    groups=[('root','root_reference','root_arithmetic'),
            ('nonroot','nonroot_reference','nonroot_arithmetic')]
    for name,baseline,candidate in groups:
        scripts=[(directory/mode/'run.tcl').read_text() for mode in [baseline,candidate]]
        assert 'ArithmeticOnly=0' in scripts[0] and 'ArithmeticOnly=1' in scripts[1]
        normalized=[re.sub(r'ArithmeticOnly=[01]','ArithmeticOnly=MODE',s) for s in scripts]
        assert normalized[0]==normalized[1],'Constraints or other parameters differ'
    rows = []
    for mode in ['root_reference','root_arithmetic','nonroot_reference','nonroot_arithmetic']:
        state = manifest['results'].get(mode, {})
        assert state.get('complete') and state.get('returncode') == 0, 'Incomplete ' + mode
        run = directory / mode
        log = (run / 'console.log').read_text()
        assert sha(run / 'console.log') == state['log_sha256']
        assert 'REQUESTER_PPA_COMPLETE' in log.splitlines()
        assert not re.search(r'^Error:', log, re.M)
        timing = (run / 'timing.rpt').read_text()
        qor = (run / 'qor.rpt').read_text()
        slacks = lambda text: [float(s) for s in re.findall(
            r'slack\s+\((?:MET|VIOLATED)\)\s+([-+\d.]+)', text)]
        assert slacks(timing), 'Missing timing paths'
        rows.append({'mode': mode,
                     'area_um2': field((run / 'area.rpt').read_text(), 'Total cell area'),
                     'worst_reported_setup_slack_ns': min(slacks(timing)),
                     'qor_hold_violation_ns': field(qor, 'Worst Hold Violation'),
                     'hold_violations': field(qor, 'No. of Hold Violations'),
                     'report_hashes': {name: sha(run / name) for name in
                         ['area.rpt', 'qor.rpt', 'timing.rpt', 'check_timing.rpt']}})
    indexed={r['mode']:r for r in rows}
    pairs=[]
    for name,b,c in groups:
        before,after=indexed[b]['area_um2'],indexed[c]['area_um2']
        pairs.append({'lane':name,'baseline_area_um2':before,'candidate_area_um2':after,
                      'area_saved_um2':before-after,'area_saved_percent':100*(1-after/before)})
    result={'complete':True,'results':rows,'pairs':pairs,'scope':manifest['scope'],
            'limits':'Matched local requester only; no integrated area/Fmax claim; QoR hold precision is limited. Performance tradeoff must be reported separately.'}
    (directory / 'comparison.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
