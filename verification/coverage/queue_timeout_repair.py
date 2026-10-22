#!/usr/bin/env python3
"""Queue AKV repairs only after the first repair wave and matrix audit pass."""
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
    args = parser.parse_args()
    previous, output = args.previous.resolve(strict=True), args.output.resolve()
    selection = args.selection.resolve(strict=True)
    here = Path(__file__).resolve().parent
    if output.exists():
        parser.error('requires fresh output')
    deadline = time.monotonic() + 10800
    print('WAITING: first repair wave; no additional simulators started', flush=True)
    while True:
        state = json.loads((previous / 'checkpoint.json').read_text())
        if state['status'] in ('PASS', 'COMPLETE_WITH_FAILURES'):
            if state['completed'] != state['total'] or any(
                    not c.get('reused') and c['status'] != 'PASS'
                    for c in state['cases'].values()):
                raise RuntimeError('first repair wave has unresolved new cases')
            break
        if state['status'] not in ('RUNNING', 'PREPARED'):
            raise RuntimeError(f'first repair wave stopped: {state.get("reason")}')
        if time.monotonic() > deadline:
            raise TimeoutError('first repair wave exceeded three-hour queue bound')
        time.sleep(30)
    subprocess.run([sys.executable, str(here / 'audit_fp16_repair_shards.py'),
                    '--campaign', str(previous), '--output', str(previous / 'fp16_union.json')],
                   check=True, timeout=120)
    script = here / 'run_timeout_repair.py'
    subprocess.run([sys.executable, str(script), '--output', str(output),
                    '--previous', str(previous), '--selection', str(selection)],
                   check=True, timeout=600)
    os.execv(sys.executable, [sys.executable, str(script), '--output', str(output),
                             '--execute', '--jobs', '8'])


if __name__ == '__main__':
    main()
