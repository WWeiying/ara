"""Bounded Host process only; no simulator or reference execution."""
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent


def save(path,value):
    with path.open('x') as f:
        json.dump(value,f,indent=2); f.write('\n')


command = [sys.executable,'-B',str(HERE/'test_host.py')]
save(HERE/'host_command.json',dict(command=command,timeout_s=300))
start = time.monotonic()
with (HERE/'host01.log').open('x') as log:
    p = subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
    timed = False
    try:
        rc = p.wait(timeout=300)
    except subprocess.TimeoutExpired:
        timed = True; p.kill(); rc = p.wait()
save(HERE/'host_process_exit.json',dict(returncode=rc,timed_out=timed,elapsed_s=time.monotonic()-start,pid=p.pid))
raise SystemExit(rc if not timed else 124)
