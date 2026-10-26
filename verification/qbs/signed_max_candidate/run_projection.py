#!/usr/bin/env python3
"""Reuse the bounded current-image worker with the vector-pair checker."""
import argparse
import importlib.util
from pathlib import Path
import signal
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    'signed_max_projection_worker', HERE.parent/'combined_zvfh_m4/projection/run.py')
worker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = worker
spec.loader.exec_module(worker)
# Import before sealing: the worker records all loaded repository modules.
import check_projection
worker.HERE = HERE


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=10800)
    parser.add_argument('--execute-reviewed', action='store_true')
    def interrupted(signum, _frame):
        raise InterruptedError(f'Signal {signum}')
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    worker.run(parser.parse_args())


if __name__ == '__main__':
    main()
