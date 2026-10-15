"""One authorized software phase, durable actual producer exit before checks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
HERE=Path(__file__).resolve().parent
REVIEW=HERE.parent/'full_e16_mf2_source_review01/REVIEW02.json'
SHA='ec54230268ca482c05f3936a97e4255c19069deb5a6bdf7c93d68c5a8fd4c1ef'
def save(path,value):
    with path.open('x') as stream:
        json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
command=[sys.executable,'-B',str(HERE/'prepare.py'),'software',str(REVIEW),SHA]
save(HERE/'software_command.json',dict(command=command,timeout_s=300,attempt=1,DUT_runs=0))
start=time.monotonic();timed=False
with (HERE/'software.log').open('x') as log:
    child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
    try:rc=child.wait(timeout=300)
    except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
    save(HERE/'software_execution.json',dict(actual_wait_returncode=rc,pid=child.pid,
        elapsed_s=time.monotonic()-start,timed_out=timed,retries=0,validated=False))
raise SystemExit(rc if not timed else 124)
