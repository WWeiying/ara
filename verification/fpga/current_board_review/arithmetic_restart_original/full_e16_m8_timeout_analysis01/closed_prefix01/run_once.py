#!/usr/bin/env python3
"""Persist actual OS wait; one closed-file process, no retries."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
HERE=Path(__file__).resolve().parent
def save(path,value):
    with path.open('x') as f:
        json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
mode=sys.argv[1]
assert mode in ('host','diagnose')
if mode=='diagnose':
    assert not (HERE/'run01').exists() and json.loads((HERE/'host.json').read_text())['status']=='HOST_ONLY_PASS'
target=HERE/('test_small.py' if mode=='host' else 'diagnostic.py')
bound=120 if mode=='host' else 600
command=[sys.executable,'-B',str(target)]
save(HERE/(mode+'_command.json'),dict(command=command,bound_s=bound,
    script_sha256=sha(target),runner_sha256=sha(Path(__file__)),attempt=1,no_retry=True))
start=time.monotonic();timeout=False
with (HERE/(mode+'.log')).open('x') as log:
    child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,cwd=HERE,start_new_session=True)
    try:rc=child.wait(timeout=bound)
    except subprocess.TimeoutExpired:
        timeout=True;os.killpg(child.pid,9);rc=child.wait()
save(HERE/(mode+'_wait.json'),dict(actual_wait_returncode=rc,pid=child.pid,
    elapsed_s=time.monotonic()-start,timed_out=timeout,bound_s=bound,retries=0))
print(mode,'actual_wait_returncode',rc,'timeout',timeout,flush=True)
raise SystemExit(0 if rc==0 and not timeout else 1)
