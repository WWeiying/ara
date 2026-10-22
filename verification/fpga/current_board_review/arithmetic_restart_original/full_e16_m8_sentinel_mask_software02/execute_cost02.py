"""Actual static auditor wait receipt first, no ELF execution."""
import json,subprocess,sys,time,hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')
command=[sys.executable,'-B',str(HERE/'linked_cfg_cost02.py')]
save(HERE/'cfg02_command.json',dict(command=command,timeout_s=600,code_sha256=hashlib.sha256((HERE/'linked_cfg_cost02.py').read_bytes()).hexdigest()))
start=time.monotonic();timed=False
with (HERE/'cfg02.log').open('x') as f:
    child=subprocess.Popen(command,stdout=f,stderr=subprocess.STDOUT)
    try:rc=child.wait(timeout=600)
    except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
    save(HERE/'cfg02_execution.json',dict(returncode=rc,pid=child.pid,elapsed_s=time.monotonic()-start,timed_out=timed,retries=0))
raise SystemExit(rc if not timed else 124)

