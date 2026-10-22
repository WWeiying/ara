"""Persist actual systemd exit facts, including failure; never infer from GC."""
import argparse
import json
import os
from pathlib import Path
import time
import hashlib
import subprocess
import sys
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
here=Path(__file__).resolve().parent
assert a.out.resolve().parent==here
facts={k:os.environ.get(k) for k in ('SERVICE_RESULT','EXIT_CODE','EXIT_STATUS')}
facts.update(observed_at=time.time(),hook_pid=os.getpid(),kind='SYSTEMD_EXEC_STOP_POST_ACTUAL_ENVIRONMENT')
with (a.out/'service_exit.json').open('x') as f:
    json.dump(facts,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
collector=here/'collect.py'
assert hashlib.sha256(collector.read_bytes()).hexdigest()=='36221eec75a206d7cd22edb4c97260afaa22af95f2469696a3aab6536e010fc9'
command=[sys.executable,'-B',str(collector),'--out',str(a.out)]
began=time.monotonic();timed=False
with (a.out/'collector.log').open('x') as log:
    child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
    try:rc=child.wait(timeout=300)
    except subprocess.TimeoutExpired:
        timed=True;child.kill();rc=child.wait()
with (a.out/'collector_exit.json').open('x') as f:
    json.dump(dict(command=command,pid=child.pid,returncode=rc,timed_out=timed,
                   elapsed_s=time.monotonic()-began,collector_sha256='36221eec75a206d7cd22edb4c97260afaa22af95f2469696a3aab6536e010fc9'),f,indent=2)
    f.write('\n');f.flush();os.fsync(f.fileno())
raise SystemExit(rc if not timed else 124)
