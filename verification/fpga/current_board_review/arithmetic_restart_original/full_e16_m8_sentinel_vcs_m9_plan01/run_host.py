"""One bounded full constructed Host with pre/post pins and numeric-first wait."""
import subprocess,sys,time
from pathlib import Path
import checker as c
import replay as r
HERE=c.HERE
pins={str(HERE/n):c.sha(HERE/n) for n in ('checker.py','replay.py','host_records.py','test_host.py',
    'reset_profile.json','soc_profile.json','owner_policy.py','run_host.py')}
r.durable(HERE/'host01_preflight.json',pins)
command=[sys.executable,'-B',str(HERE/'test_host.py')]
r.durable(HERE/'host01_command.json',dict(command=command,timeout_s=600))
start=time.monotonic();timed=False
with (HERE/'host01.log').open('x') as log:
    child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
    try:rc=child.wait(timeout=600)
    except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
    r.durable(HERE/'host01_process_exit.json',dict(returncode=rc,timed_out=timed,
        elapsed_s=time.monotonic()-start,pid=child.pid,retries=0))
c.common.base.verify_pins(pins);r.durable(HERE/'host01_postflight.json',pins)
raise SystemExit(rc if not timed else 124)
