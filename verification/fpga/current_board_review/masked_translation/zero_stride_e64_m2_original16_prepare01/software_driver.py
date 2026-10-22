#!/usr/bin/env python3
"""One bounded reference executor, with numeric wait durable before checking."""
import subprocess
import sys
import time
import prepare as p

def main():
    p.logged([sys.executable,'-B',p.HERE/'host_tests.py'],p.OUT/'host_tests.log')
    p.logged([sys.executable,'-B',p.HERE/'bound.py'],p.OUT/'bound.log')
    cmd=[sys.executable,'-B',str(p.HERE/'prepare.py'),'run']
    start=time.monotonic()
    with (p.HERE/'executor.log').open('x') as log:
        child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
        rc=child.wait()
        p.save(p.HERE/'reference01/executor_wait.json',dict(observed_executor_wait_exit_code=rc,child_pid=child.pid,elapsed_s=time.monotonic()-start,command=cmd,actual_popen_wait=True))
    p.require(rc==0,'Actual reference executor failed; no retry')
    p.logged([sys.executable,'-B',p.HERE/'seal.py'],p.HERE/'seal.log')
if __name__=='__main__':main()

