"""Bound the one synthetic profile and persist actual numeric wait first."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent


def save(name, value):
    with (HERE / name).open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


command = [sys.executable, '-B', str(HERE / 'profile_short.py')]
save('command.json', dict(command=command, cwd=str(HERE), timeout_s=120,
    retries=0, raw_access=False, code_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (HERE / 'profile_short.py', Path(__file__))}))
started = time.monotonic()
timed_out = False
with (HERE / 'profile.log').open('x') as log:
    child = subprocess.Popen(command, cwd=HERE, stdout=log, stderr=subprocess.STDOUT,
                             start_new_session=True)
    try:
        rc = child.wait(timeout=120)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(child.pid, signal.SIGKILL)
        rc = child.wait()
    save('actual_wait.json', dict(actual_wait_returncode=rc, timed_out=timed_out,
        elapsed_s=time.monotonic()-started, pid=child.pid, retries=0, validated=False))
print('ACTUAL_PROFILE_WAIT', rc, timed_out, flush=True)
raise SystemExit(124 if timed_out else rc)
