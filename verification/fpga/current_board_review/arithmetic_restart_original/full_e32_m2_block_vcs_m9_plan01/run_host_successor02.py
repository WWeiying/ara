"""Same600s Host budget, unchanged checker; preserve original stopped outcome."""
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
old=json.loads((HERE/'host01_process_exit.json').read_text())
assert type(old['returncode']) is int and old['returncode']!=0 and old['pins_unchanged'] is True
command=[sys.executable,'-B',str(HERE/'test_host_successor02.py')]
names=('checker.py','replay.py','test_host.py','host_records.py','reset_profile.json','run_host.py','lifecycle.py','context.py',
    'prepare_sources.py','test_host_successor02.py','run_host_successor02.py','HOST_STAGE_DIAGNOSIS01.md',
    'host01_process_exit.json','host01_command.json','host01.log','host01_stop.json')
pins={str(HERE/name):sha(HERE/name) for name in names}
save(HERE/'host02_command.json',dict(command=command,timeout_s=600,pins=pins,
    scope='Same complete5985 new-worker Host, immutable snapshot locator hoisted; no DUT/reference'))
start=time.monotonic();timed=False
with (HERE/'host02.log').open('x') as log:
    child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
    try:rc=child.wait(timeout=600)
    except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
unchanged=all(sha(Path(path))==digest for path,digest in pins.items())
save(HERE/'host02_process_exit.json',dict(returncode=rc,timed_out=timed,elapsed_s=time.monotonic()-start,
    pid=child.pid,pins_unchanged=unchanged,retries=0))
print(dict(returncode=rc,timed_out=timed,pins_unchanged=unchanged),flush=True)
raise SystemExit(rc if not timed and unchanged else 124)
