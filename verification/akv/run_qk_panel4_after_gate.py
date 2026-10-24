#!/usr/bin/env python3
"""Wait for the existing focused owner to exit, then exec the Attention worker."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import sys

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prerequisite', type=Path, required=True)
    p.add_argument('--owner-pid', type=int, required=True)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--worker-sha256', required=True)
    p.add_argument('--wait-timeout', type=int, default=10800)
    a = p.parse_args()
    if not 1 <= a.wait_timeout <= 10800:
        raise ValueError('Wait bound must be 1..10800 seconds')
    gate = a.prerequisite.resolve(strict=True)
    worker = ROOT / 'verification/akv/run_qk_panel4_abba.py'
    if digest(worker) != a.worker_sha256:
        raise ValueError('Attention worker changed before scheduling')
    status = json.loads((gate / 'status.json').read_text())
    if status.get('pid') != a.owner_pid:
        raise ValueError('Focused owner identity mismatch')
    if status.get('state') != 'PASS':
        try:
            fd = os.pidfd_open(a.owner_pid)
        except ProcessLookupError:
            fd = None
        if fd is not None:
            try:
                proc = Path('/proc') / str(a.owner_pid)
                # Re-read after acquiring the process handle: a terminal owner
                # can exit between the initial status read and pidfd_open.
                status = json.loads((gate / 'status.json').read_text())
                if status.get('state') != 'PASS':
                    args = proc.joinpath('cmdline').read_bytes().split(b'\0')
                    if (Path(os.readlink(proc / 'cwd')).resolve() != ROOT or
                        not any(x.endswith(b'/qk_panel4_native/rtl_run.py') for x in args)):
                        raise ValueError('PID no longer identifies the focused worker')
                    print(json.dumps(dict(state='WAITING_GATE', owner_pid=a.owner_pid,
                                          prerequisite=str(gate))), flush=True)
                    if not select.select([fd], [], [], a.wait_timeout)[0]:
                        raise TimeoutError('Focused owner did not finish within wait bound')
            finally:
                os.close(fd)
    status = json.loads((gate / 'status.json').read_text())
    result = json.loads((gate / 'result.json').read_text())
    if (status.get('state') != 'PASS' or result.get('state') != 'PASS' or
        status.get('child_pid') is not None):
        raise ValueError('Focused gate failed; whole Attention was not launched')
    if digest(worker) != a.worker_sha256:
        raise ValueError('Attention worker changed while waiting')
    print(json.dumps(dict(state='EXEC_ATTENTION', prerequisite=str(gate))), flush=True)
    # The service keeps owning the long-running worker, not a detached child.
    os.execv(sys.executable, [sys.executable, '-B', str(worker),
             '--prerequisite', str(gate), '--build', str(a.build.resolve(strict=True)),
             '--output', str(a.output.resolve()), '--timeout', '10800'])


if __name__ == '__main__':
    main()
