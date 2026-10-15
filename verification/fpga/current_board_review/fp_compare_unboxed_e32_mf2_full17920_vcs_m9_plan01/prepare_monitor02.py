"""Bounded narrow Host, then one successor plan and dryrun; no launch."""
import subprocess
import time
from scope import *
from replay_successor02 import durable

def child(label,command):
    durable(HERE/(label+'.command.json'),dict(command=command,timeout_s=120,no_DUT=True))
    start=time.monotonic();timed=False
    with (HERE/(label+'.log')).open('x') as log:
        proc=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
        try:rc=proc.wait(timeout=120)
        except subprocess.TimeoutExpired:timed=True;proc.kill();rc=proc.wait()
    durable(HERE/(label+'.wait.json'),dict(actual_wait_exit=rc,timed_out=timed,pid=proc.pid,
        elapsed_s=time.monotonic()-start,log_sha256=sha(HERE/(label+'.log'))))
    require(type(rc)is int and rc==0 and not timed,'Preserve first failure; no automatic retry')

def main():
    out=HERE/'prepared02'
    child('monitor_host01',[sys.executable,'-B',str(HERE/'test_monitor_successor.py')])
    child('prepare_monitor02',[sys.executable,'-B',str(HERE/'replay_successor02.py'),'prepare','--out',str(out)])
    child('dryrun_monitor02',[sys.executable,'-B',str(HERE/'replay_successor02.py'),'dryrun','--out',str(out),
                            '--plan-sha256',sha(out/'plan.json')])
if __name__=='__main__':main()
