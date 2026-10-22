"""One small Host entry test invocation with a durable actual wait receipt."""
import subprocess
import sys
import time
from context import HERE,save
command=[sys.executable,'-B',str(HERE/'test_host.py')]
save(HERE/'host_command.json',dict(command=command,timeout_s=60,synthetic_observer_only=True))
began=time.monotonic();timed=False
with (HERE/'host.log').open('x') as stream:
    child=subprocess.Popen(command,cwd=HERE,stdout=stream,stderr=subprocess.STDOUT)
    try:rc=child.wait(timeout=60)
    except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
save(HERE/'host_receipt.json',dict(actual_wait_exit=rc,timed_out=timed,pid=child.pid,elapsed_s=time.monotonic()-began))
print(rc,timed)
sys.exit(0 if rc==0 and not timed else 1)
