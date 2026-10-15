"""Persist the real wait outcome of one authorized bounded child, never retry."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2); f.write('\n')

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--stem', type=Path, required=True)
    p.add_argument('--timeout', type=int, default=120)
    p.add_argument('--expected', type=int, default=0)
    p.add_argument('command', nargs=argparse.REMAINDER)
    a = p.parse_args()
    cmd = a.command[1:] if a.command[:1] == ['--'] else a.command
    assert cmd and 0 < a.timeout <= 120
    a.stem.parent.mkdir(parents=True, exist_ok=True)
    save(a.stem.with_suffix('.command.json'), dict(command=cmd, cwd=str(Path.cwd()), timeout_s=a.timeout))
    log = a.stem.with_suffix('.log')
    started = time.monotonic()
    rc, error, timed_out = None, None, False
    with log.open('x') as f:
        try:
            child = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
            try:
                rc = child.wait(timeout=a.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                child.kill(); rc = child.wait()
        except Exception as exc:
            error = repr(exc)
    receipt = dict(actual_wait_exit=rc, elapsed_s=time.monotonic()-started,
        timed_out=timed_out, error=error, expected_exit=a.expected,
        log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
    save(a.stem.with_suffix('.wait.json'), receipt)
    print(json.dumps(receipt), flush=True)
    raise SystemExit(0 if type(rc) is int and rc == a.expected and not timed_out and error is None else 1)
