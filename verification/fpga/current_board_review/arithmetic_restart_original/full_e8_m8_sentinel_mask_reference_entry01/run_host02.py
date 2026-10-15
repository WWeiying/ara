"""Run changed short gates once, preserving failed host01 and profile derivation."""
from context import *
import os,subprocess,time
pins={str(p):sha(p) for p in HERE.glob('*.py')}
pins[str(HERE/'PROFILE.json')]=sha(HERE/'PROFILE.json')
save(HERE/'host02_preflight.json',pins)
command=[sys.executable,'-B',str(HERE/'test_entry02.py')]
save(HERE/'host02_command.json',dict(command=command,timeout_s=120))
start=time.monotonic();timed=False
with (HERE/'host02.log').open('x') as log:
    child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
    try:rc=child.wait(timeout=120)
    except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
    with (HERE/'host02_execution.json').open('x') as f:
        json.dump(dict(actual_wait_returncode=rc,pid=child.pid,elapsed_s=time.monotonic()-start,timed_out=timed,retries=0),f,indent=2)
        f.flush();os.fsync(f.fileno())
require(all(sha(p)==h for p,h in pins.items()),'Short successor code drift')
save(HERE/'host02_postflight.json',pins)
raise SystemExit(rc if not timed else 124)
