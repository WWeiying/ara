"""Bounded actual Host receipt for the independent FP32 worker."""
import subprocess
import time
from scope import *
from replay import durable,owned_pins

def main():
    command=[sys.executable,'-B',str(HERE/'host_supplement.py')]
    durable(HERE/'host_supplement.command.json',dict(command=command,timeout_s=120))
    before=owned_pins();durable(HERE/'host_supplement.inputs_before.json',before)
    start=time.monotonic();timed=False
    with (HERE/'host_supplement.log').open('x') as f:
        child=subprocess.Popen(command,cwd=HERE,stdout=f,stderr=subprocess.STDOUT)
        try:rc=child.wait(timeout=120)
        except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
    durable(HERE/'host_supplement.wait.json',dict(actual_wait_exit=rc,timed_out=timed,elapsed_s=time.monotonic()-start,
                                      log_sha256=sha(HERE/'host_supplement.log'),pid=child.pid))
    after=owned_pins();durable(HERE/'host_supplement.inputs_after.json',after)
    require(before==after,'Host code drift');require(rc==0 and not timed,'Host failed; preserve')
if __name__=='__main__':main()
