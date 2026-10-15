"""Bounded, exclusive offline artifact finish; never compiles or runs a model."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
OUT=HERE/'finish_execution01'
OUT.mkdir(exist_ok=False)
def save(name,value):
    with (OUT/name).open('x') as f:json.dump(value,f,indent=2);f.write('\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
command=[sys.executable,'-B','-u',str(HERE/'closed_audit01.py')]
save('command.json',dict(command=command,wrapper_pid=os.getpid(),start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    timeout_seconds=180,script_sha256=sha(HERE/'closed_audit01.py'),supervisor_sha256=sha(Path(__file__).resolve()),
    scope='Existing artifacts only: no Host rerun, compile, Spike or DUT'))
begin=time.monotonic();timed_out=False
with (OUT/'stdout.log').open('x') as out:
    child=subprocess.Popen(command,cwd=HERE,stdout=out,stderr=subprocess.STDOUT)
    save('pid.json',dict(pid=child.pid))
    try:rc=child.wait(timeout=180)
    except subprocess.TimeoutExpired:
        timed_out=True;child.kill();rc=child.wait()
result=HERE/'closed_audit01/RESULT.json'
save('exit.json',dict(returncode=rc,timed_out=timed_out,elapsed_seconds=time.monotonic()-begin,
    stdout_sha256=sha(OUT/'stdout.log'),result_sha256=sha(result) if result.is_file() else None))
raise SystemExit(0 if rc==0 and not timed_out else 1)
