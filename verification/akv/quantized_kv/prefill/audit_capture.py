#!/usr/bin/env python3
"""Audit captured data while separating mutable launcher status from inputs."""
import argparse
import json
from pathlib import Path
from capture import ROOT, validate, hashes, digest, atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run, out = args.run.resolve(strict=True), args.output.resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'verification/out'):
        raise ValueError('Fresh audit output required')
    recorded = json.loads((run / 'manifest.json').read_text())
    actual = hashes(map(Path, recorded))
    changed = [p for p in recorded if recorded[p] != actual[p]]
    # The capture writer sealed CAPTURING status before replacing it with its
    # final status. Preserve that receipt; exempt only this exact metadata file.
    if changed != [str(run / 'status.json')]:
        raise ValueError('Unexpected drift: ' + repr(changed))
    result = json.loads((run / 'result.json').read_text())
    status = json.loads((run / 'status.json').read_text())
    if result != status or result['state'] != 'PASS' or result['child_pid'] is not None:
        raise ValueError('Terminal receipt mismatch')
    reconstructed = {kind: validate(run / kind, kind) for kind in ('q4_0', 'q8_0')}
    if reconstructed != result['captures']:
        raise ValueError('Captured tensors disagree with report')
    for capture in reconstructed.values():
        d, m, h, batch = capture['query_shape']
        if capture['output_shape'] != [d * h, m, batch, 1]:
            raise ValueError('Golden output shape')
    frozen = {p: value for p, value in recorded.items() if p != str(run / 'status.json')}
    frozen.update(hashes([Path(__file__), run / 'manifest.json', run / 'result.json']))
    out.mkdir(parents=True)
    atomic_json(out / 'manifest.json', frozen)
    atomic_json(out / 'result.json', dict(state='PASS', captures=reconstructed,
        immutable_files_checked=len(frozen), source_manifest_sha256=digest(run / 'manifest.json'),
        excluded_mutable_metadata=changed, reran_model=False, rtl_performance=False,
        scope='Real host quantized Prefill capture; original status-hash bookkeeping defect retained'))


if __name__ == '__main__':
    main()
