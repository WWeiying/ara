"""Bounded successor Host actual wait; old failure remains immutable."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
HERE=Path(__file__).resolve().parent
def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
names=('checker.py','replay.py','test_host.py','test_host02.py','host_records.py','byte_preflight02.py',
    'reset_profile.json','owner_policy.py','terminal_gate.py','reference_terminal_binding.json','owner_contract.json',
    'worker_lifecycle.py','lifecycle_context.py','soc_spec.json')
pins={str(HERE/n):hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in names}
command=[sys.executable,'-B',str(HERE/'test_host02.py')]
save(HERE/'host02_command.json',dict(command=command,timeout_s=600,input_pins=pins))
start=time.monotonic();timed=False
with (HERE/'host02.log').open('x') as log:
    child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
    try:rc=child.wait(timeout=600)
    except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
save(HERE/'host02_process_exit.json',dict(returncode=rc,timed_out=timed,elapsed_s=time.monotonic()-start,pid=child.pid))
raise SystemExit(rc if not timed else 124)
