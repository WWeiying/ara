#!/usr/bin/env python3
"""Attach checked rebuild tools to an already frozen combined source bundle."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

from check_rebuild_reports import synthesis, cdc_rows


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(bundle, synth, cdc, reference, reference_hash):
    snapshot = json.loads((bundle/'snapshot.json').read_text())
    inventory = bundle/'package/SHA256SUMS'
    if snapshot['profile'] != 'host_ethernet' or digest(inventory) != snapshot['inventory_sha256']:
        raise ValueError('Snapshot mismatch')
    if len(reference_hash) != 64 or any(c not in '0123456789abcdef' for c in reference_hash):
        raise ValueError('Invalid reference hash')
    synthesis(synth.read_text(), synth.read_text())
    cdc_rows(cdc.read_text())
    here = Path(__file__).resolve().parent
    sources = {name: here/name for name in
               ('rebuild_mainrtl.ps1', 'rebuild_mainrtl.tcl', 'check_rebuild_reports.py')}
    sources.update({'baseline_synth.rpt': synth, 'baseline_cdc.rpt': cdc})
    policy = bundle/'rebuild_inputs.json'
    if policy.exists() or any((bundle/name).exists() for name in sources):
        raise ValueError('Rebuild inputs already exist; do not overwrite')
    for name, path in sources.items():
        shutil.copyfile(path, bundle/name)
    files = {name: digest(bundle/name) for name in sources}
    files['package/SHA256SUMS'] = digest(inventory)
    policy.write_text(json.dumps({
        'Files': files, 'Reference': reference, 'ReferenceSHA256': reference_hash,
        'SynthesisPolicy': 'Setup must pass; only reviewed non-worsened hold/skew groups deferred',
        'CDCPolicy': 'No new Critical/Warning detail rows; existing findings are NOT signoff',
        'BoardProgramming': False, 'HardwareValidated': False}, indent=2)+'\n')
    archive = bundle.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(bundle.rglob('*')):
            if path.is_file():
                output.write(path, path.relative_to(bundle).as_posix())
    print(json.dumps({'archive': str(archive), 'sha256': digest(archive),
                      'inventory_sha256': digest(inventory), 'files': len(files)}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--synth', type=Path, required=True)
    parser.add_argument('--cdc', type=Path, required=True)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--reference-sha256', required=True)
    args = parser.parse_args()
    prepare(args.bundle, args.synth, args.cdc, args.reference, args.reference_sha256)
