"""Actual offline child wait recorded before checker/report handling."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
HERE=Path(__file__).resolve().parent
def main():
    cmd=[sys.executable,'-B',str(HERE/'fullparse.py')];start=time.monotonic()
    with (HERE/'stdout.log').open('x') as log:
        child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT);rc=child.wait()
        with (HERE/'execution.json').open('x') as f:
            json.dump(dict(actual_wait_exit=rc,child_pid=child.pid,elapsed_s=time.monotonic()-start,command=cmd,automatic_retry=False),f,indent=2)
            f.write('\n');f.flush();os.fsync(f.fileno())
    print('ACTUAL_OFFLINE_WAIT',rc,flush=True)
    return rc
if __name__=='__main__':raise SystemExit(main())



