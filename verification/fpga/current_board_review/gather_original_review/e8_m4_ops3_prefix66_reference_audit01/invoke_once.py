#!/usr/bin/env python3
"""One bounded offline auditor child; never retry or launch a simulator."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent


def save(name, value):
    with (HERE / name).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def main():
    pins = json.loads((HERE / 'auditor_pins.json').read_text())
    for path, expected in pins.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Auditor input drift: ' + path)
    command = [sys.executable, '-B', str(HERE / 'audit.py'), '--authorized-once']
    save('execution_started.json', dict(command=command, timeout_s=600, time=time.time(),
                                      retries=0, wrapper_pid=os.getpid()))
    started = time.monotonic()
    with (HERE / 'audit.stdout.log').open('x') as stdout, (HERE / 'audit.stderr.log').open('x') as stderr:
        child = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        timed_out = False
        try:
            rc = child.wait(timeout=600)
        except subprocess.TimeoutExpired:
            timed_out = True
            child.kill()
            rc = child.wait()
    save('execution.json', dict(command=command, child_pid=child.pid, returncode=rc,
         timed_out=timed_out, elapsed_s=time.monotonic()-started, retries=0,
         audit_pins_sha256=hashlib.sha256((HERE/'auditor_pins.json').read_bytes()).hexdigest()))
    print('actual audit exit', rc, 'timed_out', timed_out, flush=True)
    return 1 if timed_out or rc != 0 else 0


if __name__ == '__main__':
    sys.exit(main())
