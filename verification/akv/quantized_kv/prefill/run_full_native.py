#!/usr/bin/env python3
"""Whole-call successor worker; reuse the sealed native protocol/identity gates.

Without --execute-reviewed this only validates the build and simulator inputs.
The original scheduler worker and its checker remain unchanged on disk.
"""
import argparse
import json
from pathlib import Path
import signal

from check_full_native import check_full_log


def require_full_build(report):
    expected = dict(whole_call=True, rebuilt_objects=15, reused_objects=0,
                    commands_per_trial=4, outputs_per_trial=1024,
                    value_decodes=[74, 20, 20, 74])
    for key, value in expected.items():
        if type(report.get(key)) is not type(value) or report[key] != value:
            raise ValueError('Whole-call build contract: ' + key)
    if report.get('state') != 'BUILT_NOT_EXECUTED':
        raise ValueError('Whole-call build state')


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--build', type=Path, required=True)
    args, _ = parser.parse_known_args()
    require_full_build(json.loads((args.build / 'build.json').read_text()))

    # A private process selects the stronger checker before invoking the common
    # worker. This does not modify the module/file in another running process.
    import run_native as worker
    worker.check_log = check_full_log
    worker.main()


if __name__ == '__main__':
    def interrupted(signum, _frame):
        raise InterruptedError(f'Signal {signum}')
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)
    main()
