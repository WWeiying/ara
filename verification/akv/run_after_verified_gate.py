#!/usr/bin/env python3
"""Wait on a verified owner pidfd, then exec a pinned downstream worker."""
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


def terminal_pass(gate):
    status = json.loads((gate / 'status.json').read_text())
    result = json.loads((gate / 'result.json').read_text())
    if (status.get('state') != 'PASS' or result.get('state') != 'PASS' or
            status.get('child_pid') is not None):
        raise ValueError('Prerequisite is not checked terminal PASS')
    return status


def owner_identity(pid):
    proc = Path('/proc') / str(pid)
    return ((proc / 'cmdline').read_bytes().split(b'\0'),
            Path(os.readlink(proc / 'cwd')).resolve())


def wait_owner(gate, pid, owner_script, timeout):
    status = json.loads((gate / 'status.json').read_text())
    if status.get('pid') != pid:
        raise ValueError('Prerequisite owner PID mismatch')
    if status.get('state') == 'PASS':
        terminal_pass(gate)
        return
    try:
        fd = os.pidfd_open(pid)
    except ProcessLookupError:
        terminal_pass(gate)
        return
    try:
        # Open the kernel handle before inspecting /proc, so PID reuse cannot
        # silently turn an observation timeout into a replacement launch.
        try:
            cmd, cwd = owner_identity(pid)
        except FileNotFoundError:
            terminal_pass(gate)
            return
        allowed = {os.fsencode(owner_script), os.fsencode(owner_script.relative_to(ROOT))}
        if cwd != ROOT or not any(arg in allowed for arg in cmd):
            raise ValueError('PID does not identify the expected gate worker')
        print(json.dumps(dict(state='WAITING_GATE', owner_pid=pid,
                              prerequisite=str(gate))), flush=True)
        if not select.select([fd], [], [], timeout)[0]:
            raise TimeoutError('Gate owner exceeded the event-wait bound')
    finally:
        os.close(fd)
    terminal_pass(gate)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('prerequisite', 'owner-script', 'worker', 'build', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--owner-pid', type=int, required=True)
    p.add_argument('--worker-sha256', required=True)
    p.add_argument('--wait-timeout', type=int, default=10800)
    a = p.parse_args()
    if not 1 <= a.wait_timeout <= 10800:
        raise ValueError('Wait bound must be 1..10800 seconds')
    gate, owner, worker, build = (x.resolve(strict=True) for x in
        (a.prerequisite, a.owner_script, a.worker, a.build))
    for script in (owner, worker):
        script.relative_to(ROOT)
    if digest(worker) != a.worker_sha256:
        raise ValueError('Downstream worker identity changed')
    wait_owner(gate, a.owner_pid, owner, a.wait_timeout)
    if digest(worker) != a.worker_sha256:
        raise ValueError('Downstream worker changed while waiting')
    print(json.dumps(dict(state='EXEC_DOWNSTREAM', worker=str(worker))), flush=True)
    # The downstream worker performs its own typed evidence/image acceptance.
    # exec preserves direct service ownership of it and its simulator children.
    os.execv(sys.executable, [sys.executable, '-B', str(worker),
             '--prerequisite', str(gate), '--build', str(build),
             '--output', str(a.output.resolve()), '--timeout', '10800'])


if __name__ == '__main__':
    main()
