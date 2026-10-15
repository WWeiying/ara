"""Persist the actual bounded inspection outcome, including any failure."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
H=Path(__file__).resolve().parent
def save(p,x):
    with p.open('x') as f:json.dump(x,f,indent=2);f.write('\n')
cmd=[sys.executable,'-B',str(H/'inspect.py')]
save(H/'command.json',dict(command=cmd,timeout_s=60,no_firmware_execution=True))
start=time.monotonic();timed=False
with (H/'execution.log').open('x') as f:
    child=subprocess.Popen(cmd,cwd=H,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
    try:rc=child.wait(timeout=60)
    except subprocess.TimeoutExpired:
        timed=True;os.killpg(child.pid,signal.SIGKILL);rc=child.wait()
save(H/'execution_receipt.json',dict(actual_wait_exit=rc,timed_out=timed,elapsed_s=time.monotonic()-start,pid=child.pid))
print(json.dumps(dict(actual_wait_exit=rc,timed_out=timed)))
sys.exit(0 if rc==0 and not timed else 1)
