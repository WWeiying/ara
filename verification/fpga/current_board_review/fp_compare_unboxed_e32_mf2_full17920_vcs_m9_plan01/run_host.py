"""Bounded actual Host receipt for the independent FP32 worker."""
import subprocess
import time
from scope import *
from replay import durable,owned_pins

def main():
    command=[sys.executable,'-B',str(HERE/'test_host.py')]
    durable(HERE/'host01.command.json',dict(command=command,timeout_s=120))
    before=owned_pins();durable(HERE/'host01.inputs_before.json',before)
    start=time.monotonic();timed=False
    with (HERE/'host01.log').open('x') as f:
        child=subprocess.Popen(command,cwd=HERE,stdout=f,stderr=subprocess.STDOUT)
        try:rc=child.wait(timeout=120)
        except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
    durable(HERE/'host01.wait.json',dict(actual_wait_exit=rc,timed_out=timed,elapsed_s=time.monotonic()-start,
                                      log_sha256=sha(HERE/'host01.log'),pid=child.pid))
    after=owned_pins();durable(HERE/'host01.inputs_after.json',after)
    require(before==after,'Host code drift');require(rc==0 and not timed,'Host failed; preserve')
if __name__=='__main__':main()
