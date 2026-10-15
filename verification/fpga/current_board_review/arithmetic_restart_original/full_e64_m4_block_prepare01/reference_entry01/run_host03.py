"""One bounded small Host successor, with actual source identities and wait."""
import subprocess
import sys
import time
from context import HERE,save,sha
paths=[p for p in HERE.iterdir() if p.suffix in ('.py','.json') and not p.name.startswith(('host','entry'))]
pins={str(p):sha(p) for p in paths}
command=[sys.executable,'-B',str(HERE/'test_host03.py')]
save(HERE/'host03_command.json',dict(command=command,timeout_s=60,synthetic_observer_only=True,input_pins=pins))
began=time.monotonic();timed=False
with (HERE/'host03.log').open('x') as stream:
    child=subprocess.Popen(command,cwd=HERE,stdout=stream,stderr=subprocess.STDOUT)
    try:rc=child.wait(timeout=60)
    except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
unchanged=all(sha(p)==h for p,h in pins.items())
save(HERE/'host03_receipt.json',dict(actual_wait_exit=rc,timed_out=timed,pid=child.pid,elapsed_s=time.monotonic()-began,input_pins_unchanged=unchanged,input_pins=pins))
print(rc,timed,unchanged)
sys.exit(0 if rc==0 and not timed and unchanged else 1)
