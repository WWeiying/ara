"""One bounded Host and frozen-image prepare/dryrun; never launch mode."""
from scope import *
import os
import subprocess
import time
import replay_successor02 as replay


def command(argv,prefix,seconds):
    replay.durable(prefix.with_suffix('.command.json'),dict(command=argv,timeout_s=seconds))
    start=time.monotonic();timed=False
    with prefix.with_suffix('.log').open('x') as log:
        p=subprocess.Popen(argv,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
        try:rc=p.wait(timeout=seconds)
        except subprocess.TimeoutExpired:timed=True;p.kill();rc=p.wait()
        replay.durable(prefix.with_suffix('.wait.json'),dict(actual_wait_exit=rc,timed_out=timed,
            elapsed_s=time.monotonic()-start,pid=p.pid,validated=False))
    require(rc==0 and not timed,'Preparation command failed; preserve evidence '+str(prefix))


def main():
    command([sys.executable,'-B',str(HERE/'test_host.py')],HERE/'host',120)
    out=HERE/'prepared01'
    command([sys.executable,'-B',str(HERE/'replay_successor02.py'),'prepare','--out',str(out)],HERE/'prepare',180)
    digest=sha(out/'plan.json')
    command([sys.executable,'-B',str(HERE/'replay_successor02.py'),'dryrun','--out',str(out),
        '--plan-sha256',digest],HERE/'dryrun',180)
    print('READY_FOR_INDEPENDENT_ENTRY_PARENT_LAUNCH_ONLY',digest,flush=True)


if __name__=='__main__':main()
