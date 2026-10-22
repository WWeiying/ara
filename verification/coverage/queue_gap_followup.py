#!/usr/bin/env python3
"""Start a frozen coverage extension after a predecessor completes normally.

The systemd service stays idle while the existing eight workers run. It exits
on infrastructure failure or a bounded deadline; it never retries failed tests.
Exec preserves the service's MainPID for the scheduler's ownership checks.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--wait-seconds', type=int, default=7200)
    args = parser.parse_args()
    script = Path(__file__).with_name('extend_gap_coverage.py').resolve()
    previous = args.previous.resolve(strict=True)
    output = args.output.resolve()
    selection = args.selection.resolve(strict=True)
    if output.exists() or args.wait_seconds <= 0:
        parser.error('requires a fresh output directory and positive wait bound')
    deadline = time.monotonic() + args.wait_seconds
    print(f'Waiting for {previous}; no simulator started by this service', flush=True)
    while True:
        state = json.loads((previous / 'checkpoint.json').read_text())
        if state['status'] in ('PASS', 'COMPLETE_WITH_FAILURES'):
            if state['completed'] != state['total']:
                raise RuntimeError('predecessor marked complete with missing outcomes')
            break
        if state['status'] not in ('PREPARED', 'RUNNING'):
            raise RuntimeError(f'predecessor stopped: {state.get("reason", state["status"])}')
        if time.monotonic() >= deadline:
            raise TimeoutError('predecessor did not complete within wait bound')
        time.sleep(30)
    subprocess.run([sys.executable, str(script), '--output', str(output),
                    '--previous', str(previous), '--selection', str(selection)],
                   check=True, timeout=600)
    os.execv(sys.executable, [sys.executable, str(script), '--output', str(output),
                             '--execute', '--jobs', '8'])


if __name__ == '__main__':
    main()
