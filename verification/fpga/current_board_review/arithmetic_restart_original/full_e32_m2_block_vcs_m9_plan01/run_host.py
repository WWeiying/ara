"""One bounded new-worker Host with stage logs and actual numeric receipt."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
HERE=Path(__file__).resolve().parent
def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
command=[sys.executable,'-B',str(HERE/'test_host.py')]
pins={str(HERE/name):sha(HERE/name) for name in ('checker.py','replay.py','test_host.py','host_records.py','reset_profile.json','run_host.py','lifecycle.py','context.py','prepare_sources.py')}
save(HERE/'host01_command.json',dict(command=command,timeout_s=600,pins=pins,
    scope='New worker constructed full5985 only; no previous software Host/compile/reference'))
start=time.monotonic();timed=False
with (HERE/'host01.log').open('x') as log:
    child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
    try:rc=child.wait(timeout=600)
    except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
unchanged=all(sha(Path(path))==digest for path,digest in pins.items())
save(HERE/'host01_process_exit.json',dict(returncode=rc,timed_out=timed,elapsed_s=time.monotonic()-start,
    pid=child.pid,pins_unchanged=unchanged,retries=0))
print(dict(returncode=rc,timed_out=timed,pins_unchanged=unchanged),flush=True)
raise SystemExit(rc if not timed and unchanged else 124)
