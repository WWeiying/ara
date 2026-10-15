"""Actual service exit facts then one bounded metadata collector child."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
import checker as c
import replay as r
parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
out=args.out.resolve();c.require(out.parent==c.HERE,'Owned hook output')
r.durable(out/'service_exit.json',dict({key:os.environ.get(key) for key in ('SERVICE_RESULT','EXIT_CODE','EXIT_STATUS')},
    observed_at=time.time(),hook_pid=os.getpid(),kind='SYSTEMD_EXEC_STOP_POST_ACTUAL_ENVIRONMENT'))
plan=c.read(out/'plan.json');path=c.HERE/'collect.py'
c.require(plan['pins'][str(path)]==c.sha(path),'Frozen terminal collector code')
command=[sys.executable,'-B',str(path),'--out',str(out)]
r.durable(out/'collector_command.json',dict(command=command,timeout_s=300,collector_sha256=c.sha(path)))
start=time.monotonic();timed=False
with (out/'collector.log').open('x') as stream:
    child=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT)
    try:rc=child.wait(timeout=300)
    except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
    r.durable(out/'collector_exit.json',dict(actual_wait_returncode=rc,pid=child.pid,elapsed_s=time.monotonic()-start,timed_out=timed,retries=0))
raise SystemExit(rc if not timed else 124)

