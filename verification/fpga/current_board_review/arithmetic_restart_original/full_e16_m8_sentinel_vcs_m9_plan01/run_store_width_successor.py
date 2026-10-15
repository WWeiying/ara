"""One short source-width successor; no full4095 stream."""
import subprocess,sys,time
import checker as c
import replay as r
files=('checker.py','replay.py','test_store_width_successor.py','run_store_width_successor.py','soc_profile.json',
    'host01_frozen_code/checker.py','host01_frozen_code/replay.py')
pins={str(c.HERE/n):c.sha(c.HERE/n) for n in files}
r.durable(c.HERE/'width_successor_preflight.json',pins)
command=[sys.executable,'-B',str(c.HERE/'test_store_width_successor.py')]
r.durable(c.HERE/'width_successor_command.json',dict(command=command,timeout_s=120))
start=time.monotonic();timed=False
with (c.HERE/'width_successor.log').open('x') as log:
    child=subprocess.Popen(command,cwd=c.HERE,stdout=log,stderr=subprocess.STDOUT)
    try:rc=child.wait(timeout=120)
    except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
    r.durable(c.HERE/'width_successor_execution.json',dict(actual_wait_returncode=rc,pid=child.pid,
        elapsed_s=time.monotonic()-start,timed_out=timed,retries=0))
c.common.base.verify_pins(pins);r.durable(c.HERE/'width_successor_postflight.json',pins)
raise SystemExit(rc if not timed else 124)
