#!/usr/bin/env python3
"""One 600-second offline child; persist actual wait outcome, never retry."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent

def save(path,value):
    with path.open('x') as stream:
        json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())

def main():
    out=HERE/'execution01';out.mkdir(exist_ok=False)
    command=[sys.executable,'-B',str(HERE/'audit.py'),'--authorize-full-parse',
        '--approved-checker-sha256','428fdb8e7a4f67ec20f0d1d1a37f4960beb58caa2607ec8ab5a28de7892f3d33',
        '--approved-host-sha256','4d4b6b8b68594b94d7003d5df9f2aaa3ca650729d1eccf87fdcc4ee6cdf60fc3']
    save(out/'command.json',dict(command=command,cwd=str(HERE),timeout_s=600,attempt=1,offline_only=True))
    started=time.time();clock=time.monotonic();timedout=False
    with (out/'output.log').open('x') as stream:
        child=subprocess.Popen(command,cwd=HERE,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        try:rc=child.wait(timeout=600)
        except subprocess.TimeoutExpired:
            timedout=True;os.killpg(child.pid,signal.SIGKILL);rc=child.wait()
    result=dict(status='OFFLINE_CHILD_ZERO_UNVALIDATED' if rc==0 and not timedout else 'OFFLINE_CHILD_FAILED',
        returncode=rc,timeout=timedout,pid=child.pid,started=started,finished=time.time(),
        elapsed_s=time.monotonic()-clock,attempt=1,reference_invocations=0,DUT_invocations=0)
    save(out/'outcome.json',result);print(json.dumps(result),flush=True)
    return 0 if rc==0 and not timedout else 1

if __name__=='__main__':raise SystemExit(main())
