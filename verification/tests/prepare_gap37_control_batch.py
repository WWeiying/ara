#!/usr/bin/env python3
"""Compose two reviewed control cases on a completed, checked PASS corpus."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    baseline = args.baseline.resolve(strict=True)
    collection = read(baseline / 'collection.json')
    if collection['status'] not in ('PASS', 'COMPLETE_WITH_FAILURES'):
        raise ValueError('Baseline coverage is not complete')
    bits = baseline / 'combined-bits.json'
    if not bits.is_file():
        raise ValueError('Missing completed baseline bitmaps')
    fence_path = OUT / 'gap36-analysis-20261004-01/selection-fence.json'
    csr_path = OUT / 'gap37-csr-analysis-20261004-01/selection-checked.json'
    fence, csr = read(fence_path), read(csr_path)
    cases = fence['cases'] + csr['cases']
    if {c['name'] for c in cases} != {'app:fence_t_gap36_smoke', 'rvv:gap37_csr_alias_tvm'} or len(cases) != 2:
        raise ValueError('Unexpected or duplicate control case')
    if any(not 0 < c['timeout_s'] <= 600 for c in cases):
        raise ValueError('Unbounded control case')
    result = {'status': 'REVIEWED_SELECTION_NOT_LAUNCHED', 'baseline': str(baseline),
              'baseline_bits': str(bits), 'cases': cases,
              'composition': {'fence': str(fence_path), 'csr': str(csr_path),
                              'script': str(Path(__file__).resolve())},
              'note': 'New FENCE RVFI admission and CSR alias/TVM checks; old failed VDBs excluded. '
                      'Same frozen RTL; no claim of DUT PASS at selection time.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(args.output)


if __name__ == '__main__':
    main()
