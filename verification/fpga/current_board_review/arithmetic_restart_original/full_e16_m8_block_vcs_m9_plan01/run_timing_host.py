"""One narrow timing successor Host, actual numeric exit before inspecting reports."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
HERE=Path(__file__).resolve().parent
def save(path,value):
    with path.open('x') as stream:
        json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
command=[sys.executable,'-B',str(HERE/'test_timing_successor.py')]
save(HERE/'timing_host_command.json',dict(command=command,timeout_s=120,fullHost_reruns=0))
start=time.monotonic();timed=False
with (HERE/'timing_host.log').open('x') as log:
    child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
    try:rc=child.wait(timeout=120)
    except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
    save(HERE/'timing_host_execution.json',dict(actual_wait_returncode=rc,pid=child.pid,
        elapsed_s=time.monotonic()-start,timed_out=timed,retries=0))
raise SystemExit(rc if not timed else 124)

