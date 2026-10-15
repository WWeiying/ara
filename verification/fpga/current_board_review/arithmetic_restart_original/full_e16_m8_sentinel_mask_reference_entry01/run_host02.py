from context import *
import subprocess,time
pins={str(p):sha(p) for p in HERE.glob('*.py')}
pins[str(HERE/'PROFILE02.json')]=sha(HERE/'PROFILE02.json')
save(HERE/'host02_preflight.json',pins)
start=time.monotonic();timed=False
with (HERE/'host02.log').open('x') as log:
    child=subprocess.Popen([sys.executable,'-B',str(HERE/'test_entry02.py')],stdout=log,stderr=subprocess.STDOUT)
    try:rc=child.wait(timeout=120)
    except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
    save(HERE/'host02_execution.json',dict(returncode=rc,pid=child.pid,elapsed_s=time.monotonic()-start,timed_out=timed,retries=0))
require(all(sha(p)==h for p,h in pins.items()),'Short Host code drift')
save(HERE/'host02_postflight.json',pins)
raise SystemExit(rc)
