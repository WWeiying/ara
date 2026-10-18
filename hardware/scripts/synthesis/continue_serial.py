#!/usr/bin/env python3
"""Run one frozen control after a specific live candidate completes successfully.

Never restart a run or infer completion from a timeout. Record failure instead
of launching the successor when the predecessor fails or its driver disappears.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def identity(pid):
    try:
        fields = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(') ', 1)[1].split()
        return None if fields[0] == 'Z' else fields[19]
    except FileNotFoundError:
        return None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--predecessor', type=Path, required=True)
    p.add_argument('--driver-pid', type=int, required=True)
    p.add_argument('--successor', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.predecessor, a.successor, a.out = [x.resolve() for x in (a.predecessor, a.successor, a.out)]
    a.out.mkdir(parents=True, exist_ok=False)
    flow = Path(__file__).with_name('flow.py')
    digest = hashlib.sha256(flow.read_bytes()).hexdigest()
    start = identity(a.driver_pid)
    if start is None:
        raise RuntimeError('Predecessor driver must be live when the queue is created')
    def state(value, **extra):
        target = a.out / 'status.json'
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps({'state': value, 'time': time.time(),
            'queue_pid': os.getpid(), 'predecessor': str(a.predecessor),
            'predecessor_driver': a.driver_pid, 'driver_start_ticks': start,
            'successor': str(a.successor), **extra}, indent=2) + '\n')
        temporary.replace(target)
    with (a.out / '.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        while True:
            try:
                previous = json.loads((a.predecessor / 'status.json').read_text())['state']
            except json.JSONDecodeError:
                time.sleep(1)
                continue
            if previous == 'COMPLETE':
                break
            if previous == 'FAILED' or identity(a.driver_pid) != start:
                state('STOPPED', reason='Predecessor failed or live driver disappeared', predecessor_state=previous)
                return 1
            state('WAITING_FOR_PREDECESSOR', predecessor_state=previous)
            time.sleep(30)
        if hashlib.sha256(flow.read_bytes()).hexdigest() != digest:
            state('STOPPED', reason='Flow driver changed after queue creation')
            return 1
        if json.loads((a.successor / 'status.json').read_text())['state'] != 'PREPARED':
            state('STOPPED', reason='Successor is no longer untouched PREPARED input')
            return 1
        state('VERIFYING_PREDECESSOR')
        with (a.out / 'driver.log').open('w') as log:
            checked = subprocess.run([sys.executable, str(flow), 'report', '--out', str(a.predecessor)], stdout=log, stderr=subprocess.STDOUT)
            if checked.returncode:
                state('STOPPED', reason='Predecessor completed artifact verification failed')
                return checked.returncode
            state('RUNNING_SUCCESSOR')
            result = subprocess.run([sys.executable, str(flow), 'run', '--out', str(a.successor)], stdout=log, stderr=subprocess.STDOUT)
        state('COMPLETE' if result.returncode == 0 else 'FAILED', returncode=result.returncode)
        return result.returncode


if __name__ == '__main__':
    sys.exit(main())
