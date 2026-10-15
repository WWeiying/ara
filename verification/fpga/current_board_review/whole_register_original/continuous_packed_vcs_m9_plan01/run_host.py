"""One bounded owned Host process; preserve numeric wait before result inspection."""
import os
from pathlib import Path
import subprocess
import sys
import time
sys.dont_write_bytecode=True
import checker as c

def main():
    command=[sys.executable,'-B',str(c.HERE/'test_host.py')]
    start=time.monotonic();timed=False
    with (c.HERE/'host02.log').open('x') as log:
        p=subprocess.Popen(command,cwd=c.HERE,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:rc=p.wait(timeout=600)
        except subprocess.TimeoutExpired:
            timed=True;os.killpg(p.pid,9);rc=p.wait()
    c.save(c.HERE/'host02_process_exit.json',dict(command=command,pid=p.pid,returncode=rc,timed_out=timed,elapsed_s=time.monotonic()-start))
    print('HOST_NUMERIC_EXIT',rc,'timeout',timed,flush=True)
    return int(timed or rc!=0)

if __name__=='__main__':raise SystemExit(main())
