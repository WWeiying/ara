#!/usr/bin/env python3
import json
from pathlib import Path
import subprocess
import sys
import time
HERE=Path(__file__).resolve().parent
review=HERE.parents[1]/'e32_m1_packed_source_review01/SOFTWARE02_SOURCE_REVIEW.md'
command=[sys.executable,'-B',str(HERE/'prepare.py'),'--source-review',str(review),
    '--source-review-sha256','3f73028df84a0a2b8e9bc6c38c751bf2d36c7930a2fae26c47dc60836ab765fe']
with (HERE/'execution_command.json').open('x') as f:
    json.dump(dict(command=command,timeout_s=600,reference=False,DUT=False),f,indent=2)
start=time.monotonic();timedout=False;rc=None
with (HERE/'execution.log').open('x') as log:
    child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
    with (HERE/'execution_pid.json').open('x') as f:json.dump(dict(pid=child.pid),f)
    print('Host/compile PID',child.pid,flush=True)
    try:rc=child.wait(timeout=600)
    except subprocess.TimeoutExpired:
        timedout=True;child.kill();rc=child.wait()
with (HERE/'execution_receipt.json').open('x') as f:
    json.dump(dict(returncode=rc,timed_out=timedout,elapsed_s=time.monotonic()-start),f,indent=2)
print('Host/compile returncode',rc,'timed_out',timedout,flush=True)
raise SystemExit(rc if not timedout else 124)
