"""Focused checker lifecycle tests only; never launches a reference."""
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
if __name__=='__main__':
    command=[sys.executable,'-B','-m','unittest','-v','test_text02']
    began=time.monotonic()
    with (HERE/'host_text02.log').open('x') as log:
        child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
        timedout=False
        try:rc=child.wait(timeout=120)
        except subprocess.TimeoutExpired:
            timedout=True;child.kill();rc=child.wait()
    receipt=dict(command=command,pid=child.pid,returncode=rc,timeout=timedout,
        elapsed_s=time.monotonic()-began,attempt=1)
    with (HERE/'host_text02_receipt.json').open('x') as f:
        json.dump(receipt,f,indent=2);f.write('\n')
    print(json.dumps(receipt),flush=True)
    if rc!=0 or timedout:raise SystemExit(1)
