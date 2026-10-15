"""Save actual audit wait before any result interpretation."""
import json
from pathlib import Path
import subprocess
import sys
import time
H=Path(__file__).resolve().parent
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')
assert not (H/'execution_command.json').exists()
cmd=[sys.executable,'-B',str(H/'audit.py')];save(H/'execution_command.json',dict(command=cmd,timeout_s=60))
start=time.monotonic();timed=False
with (H/'execution.log').open('x') as f:
    c=subprocess.Popen(cmd,cwd=H.parent,stdout=f,stderr=subprocess.STDOUT)
    try:rc=c.wait(timeout=60)
    except subprocess.TimeoutExpired:timed=True;c.kill();rc=c.wait()
save(H/'execution_receipt.json',dict(returncode=rc,timed_out=timed,elapsed_s=time.monotonic()-start,pid=c.pid))
print(json.dumps(dict(returncode=rc,timed_out=timed)),flush=True)
sys.exit(0 if rc==0 and not timed else 1)
