#!/usr/bin/env python3
"""Production-binding successor of the sealed token-major ABBA worker."""
import argparse
import json
from pathlib import Path
import signal

from check_strided_native import check_strided_log
from run_strided_native import require_full_build

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def require_production_build(report):
    require_full_build(report)
    if report.get('kind') not in ('q4_0', 'q8_0'):
        raise ValueError('Unsupported capture kind')
    if report.get('value_binding') != 'shared_rvv_q8_0':
        raise ValueError('Production RVV V callback required')
    if report.get('canonical_prefill') != str(ROOT/'software/akv/experimental/quantized_kv/prefill/execute.h'):
        raise ValueError('Canonical Prefill source required')


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--build', type=Path, required=True)
    args, _ = parser.parse_known_args()
    require_production_build(json.loads((args.build/'build.json').read_text()))
    import run_native as worker
    worker.check_log = check_strided_log
    worker.main()


if __name__ == '__main__':
    def interrupted(signum, _frame):
        raise InterruptedError(f'Signal {signum}')
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)
    main()
