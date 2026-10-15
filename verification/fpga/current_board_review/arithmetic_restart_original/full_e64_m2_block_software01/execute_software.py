"""One bounded Host/GCC child; preserve actual numeric wait before metadata checks."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
H=Path(__file__).resolve().parent
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')
assert not (H/'execution_command.json').exists(),'No auto retry'
cmd=[sys.executable,'-B',str(H/'prepare.py'),'software']
pins=json.loads((H/'source_entry.json').read_text())['pins']
for p,h in pins.items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,p
save(H/'execution_command.json',dict(command=cmd,timeout_s=180,pins=pins,reference=False,DUT=False))
started=time.monotonic();timed=False
with (H/'execution.log').open('x') as f:
    child=subprocess.Popen(cmd,cwd=H,stdout=f,stderr=subprocess.STDOUT)
    save(H/'execution_pid.json',dict(pid=child.pid))
    try:rc=child.wait(timeout=180)
    except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
save(H/'execution_receipt.json',dict(returncode=rc,timed_out=timed,elapsed_s=time.monotonic()-started,pid=child.pid))
changed=[p for p,h in pins.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h]
save(H/'execution_terminal.json',dict(status='HOST_COMPILE_COMPLETE' if rc==0 and not timed and not changed else 'STOPPED',returncode=rc,pin_drift=changed,reference=False,DUT=False))
print(json.dumps(dict(returncode=rc,timed_out=timed,changed=changed)),flush=True)
sys.exit(0 if rc==0 and not timed and not changed else 1)
