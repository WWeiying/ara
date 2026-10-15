import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
def save(name,value):
    with (HERE/name).open('x') as f:json.dump(value,f,indent=2);f.write('\n')

command=[sys.executable,'-B','-u',str(HERE/'prepare.py')]
save('execution_command.json',dict(command=command,wrapper_pid=os.getpid(),start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    timeout_seconds=600,script_sha256=hashlib.sha256((HERE/'prepare.py').read_bytes()).hexdigest(),scope='Host/compile only, no reference/DUT'))
begin=time.monotonic();timed_out=False
with (HERE/'execution.log').open('x') as out:
    child=subprocess.Popen(command,cwd=HERE,stdout=out,stderr=subprocess.STDOUT)
    save('execution_pid.json',dict(pid=child.pid))
    try:rc=child.wait(timeout=600)
    except subprocess.TimeoutExpired:
        timed_out=True;child.kill();rc=child.wait()
save('execution_receipt.json',dict(returncode=rc,timed_out=timed_out,elapsed_seconds=time.monotonic()-begin))
raise SystemExit(0 if rc==0 and not timed_out else 1)
