"""Persist actual focused Host wait before reading its result."""
from pathlib import Path
import subprocess
import sys
import time
import prepare as p
command=[sys.executable,'-B',str(p.HERE/'test_reference_host.py')]
p.save(p.HERE/'reference_host_command.json',dict(command=command,timeout_s=30))
start=time.monotonic();timed=False
with (p.HERE/'reference_host.log').open('x') as log:
    child=subprocess.Popen(command,cwd=p.HERE,stdout=log,stderr=subprocess.STDOUT)
    try:rc=child.wait(timeout=30)
    except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
    p.save(p.HERE/'reference_host_execution.json',dict(actual_wait_returncode=rc,pid=child.pid,elapsed_s=time.monotonic()-start,timed_out=timed))
raise SystemExit(rc)
