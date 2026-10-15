#!/usr/bin/env python3
import json
from pathlib import Path
import subprocess
import sys
import time
HERE=Path(__file__).resolve().parent
command=[sys.executable,'-B',str(HERE/'prepare.py')]
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
