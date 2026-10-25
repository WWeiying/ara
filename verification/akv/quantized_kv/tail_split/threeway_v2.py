#!/usr/bin/env python3
"""Unchanged H/S/B execution with profile-bound tail prerequisite receipts."""
import argparse
from pathlib import Path
import signal
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from verification.akv.quantized_kv.tail_split import threeway as original
from verification.akv.quantized_kv.tail_split import combine_v2

ACCEPTANCE = 'TAIL_SPLIT_COMBINED_PASS_V2'
original_checked_tails = original.checked_tails


def checked_tails(directory, target, pins):
    receipt = original_checked_tails(directory, target, pins)
    original.s.require(receipt['acceptance'] == 'TAIL_SPLIT_COMBINED_PASS',
                       'Unexpected predecessor admission schema')
    receipt.update(acceptance=ACCEPTANCE,
                   query_identity_policy='capture-bound within profile; no cross-profile equality')
    return receipt


def configure():
    original.checked_combined = combine_v2.checked_combined
    original.checked_run = combine_v2.checked_run
    original.validate_matrix = combine_v2.validate_matrix
    original.checked_tails = checked_tails


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('build', 'prerequisite', 'tail-combined', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=10800)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()

    def interrupted(sig, _frame):
        raise InterruptedError(f'Signal {sig}')

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    configure()
    original.run(args)


if __name__ == '__main__':
    main()
