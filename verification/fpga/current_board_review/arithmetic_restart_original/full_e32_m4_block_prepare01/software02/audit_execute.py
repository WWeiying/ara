import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
HERE=Path(__file__).resolve().parent
OUT=HERE/'audit_execution01'
OUT.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,x):
    with (OUT/n).open('x') as f:json.dump(x,f,indent=2);f.write('\n')
command=[sys.executable,'-B','-u',str(HERE/'audit.py')]
save('command.json',dict(command=command,supervisor_pid=os.getpid(),timeout_seconds=300,start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    scripts={n:sha(HERE/n) for n in ('audit.py','audit_execute.py','leaf_cfg.py','main_cfg.py')},scope='Closed linked artifact/CFG analysis only; no reference or DUT'))
start=time.monotonic();timed_out=False
with (OUT/'stdout.log').open('x') as f:
    child=subprocess.Popen(command,cwd=HERE,stdout=f,stderr=subprocess.STDOUT)
    save('pid.json',dict(pid=child.pid))
    try:rc=child.wait(timeout=300)
    except subprocess.TimeoutExpired:timed_out=True;child.kill();rc=child.wait()
result=HERE/'artifact01/RESULT.json'
save('exit.json',dict(returncode=rc,timed_out=timed_out,elapsed_seconds=time.monotonic()-start,stdout_sha256=sha(OUT/'stdout.log'),result_sha256=sha(result) if result.is_file() else None))
raise SystemExit(0 if rc==0 and not timed_out else 1)
