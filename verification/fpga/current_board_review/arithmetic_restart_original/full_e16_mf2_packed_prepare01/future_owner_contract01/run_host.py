"""Bounded static contract Host; never instantiates a worker or parses raw."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from policy import sha,SOURCE,DISPATCHER,contract
HERE=Path(__file__).resolve().parent
def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
pins={str(p):sha(p) for p in (HERE/'policy.py',HERE/'test_host.py',HERE/'run_host.py',
    SOURCE/'proof.json',SOURCE/'sequence.json',DISPATCHER)}
command=[sys.executable,'-B',str(HERE/'test_host.py')]
save(HERE/'preflight.json',dict(pins=pins,command=command,timeout_s=30,reference_runs=0,DUT_runs=0,CSV_reads=0))
start=time.monotonic();timed=False
with (HERE/'host.log').open('x') as log:
    child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
    try:rc=child.wait(timeout=30)
    except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
    save(HERE/'execution.json',dict(actual_wait_returncode=rc,pid=child.pid,
        elapsed_s=time.monotonic()-start,timed_out=timed,retries=0))
assert all(sha(p)==digest for p,digest in pins.items())
if rc==0 and not timed:
    c=contract();c.pop('target_ledger')
    save(HERE/'result.json',dict(status='STATIC_OWNER_ELIGIBILITY_HOST_PASS_NOT_WORKER_NOT_DUT',
        tests=6,contract=c,pins=pins,pins_pre_post_unchanged=True,reference_entry_unchanged=True,
        reference_runs=0,DUT_runs=0,CSV_reads=0))
raise SystemExit(rc if not timed else 124)
