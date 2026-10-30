#!/usr/bin/env python3
"""Accept explicit generic producer diagnostics without weakening RVV checks."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'verification/qbs'))
from run_half_scale_soc import hashes, digest, atomic_json

CHECKER = HERE / 'packed_stride/rvv_fallback/repair_accept/check.py'


def check(text):
    kept, count = [], 0
    pending = None
    for line in text.splitlines():
        if line.startswith('GGML_RISCV_QBS_M4_SELECTED '):
            fields = dict(item.split('=', 1) for item in line.split()[1:])
            if pending is None or fields != dict(source='direct', tag='0', path='generic', k=pending):
                raise ValueError('Unexpected producer selection')
            count += 1
            pending = None
            continue
        if pending is not None:
            raise ValueError('Missing immediately paired selection')
        if line.startswith('GGML_RISCV_QBS_Q8K_M4_PREPARE '):
            fields = dict(item.split('=', 1) for item in line.split()[1:])
            if fields.get('enabled') != '0' or fields.get('path') != 'generic':
                raise ValueError('Non-generic producer')
            pending = fields['k']
        kept.append(line)
    if pending is not None or count != 16:
        raise ValueError('Incomplete producer records')
    spec = importlib.util.spec_from_file_location('accepted_stride_check', CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.check('\n'.join(kept))
    if any(case['mismatches'] for case in result['cases']):
        raise ValueError('Numerical mismatch')
    return dict(result, generic_selection_records=count)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run, out = args.run.resolve(strict=True), args.output.resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'verification/out'):
        raise ValueError('Fresh output required')
    pins = json.loads((run / 'manifest.json').read_text())
    if hashes(map(Path, pins)) != pins:
        raise ValueError('Execution inputs changed')
    text = (run / 'qemu.log').read_text()
    result = check(text)
    for bad in (text.replace('tag=0', 'tag=1', 1), text.replace('source=direct tag=0', 'source=cache tag=0', 1),
                text.replace('path=generic k=512', 'path=rvv k=512', 1)):
        try:
            check(bad)
        except ValueError:
            continue
        raise ValueError('Negative checker test accepted')
    out.mkdir(parents=True)
    pins.update(hashes([Path(__file__), CHECKER, run / 'qemu.log', run / 'result.json']))
    atomic_json(out / 'manifest.json', pins)
    atomic_json(out / 'result.json', dict(state='PASS', measured=result, mutations_rejected=3,
        log_sha256=digest(run / 'qemu.log'), reran_simulation=False, performance_measured=False))


if __name__ == '__main__':
    main()
