"""Once-only bounded preparation and command dryrun; never launches a service."""
import subprocess
import time
from scope import *
from replay_successor import durable

def child(label,command):
    durable(HERE/(label+'.command.json'),dict(command=command,timeout_s=180,no_DUT=True))
    start=time.monotonic();timed=False
    with (HERE/(label+'.log')).open('x') as log:
        proc=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
        try:rc=proc.wait(timeout=180)
        except subprocess.TimeoutExpired:timed=True;proc.kill();rc=proc.wait()
    durable(HERE/(label+'.wait.json'),dict(actual_wait_exit=rc,timed_out=timed,pid=proc.pid,
        elapsed_s=time.monotonic()-start,log_sha256=sha(HERE/(label+'.log'))))
    require(type(rc)is int and rc==0 and not timed,'Preparation failed; preserve, no auto retry')

def main():
    out=HERE/'prepared01'
    child('prepare_contract',[sys.executable,'-B',str(HERE/'test_prepare_contract.py')])
    child('prepare02',[sys.executable,'-B',str(HERE/'replay_successor.py'),'prepare','--out',str(out)])
    child('dryrun02',[sys.executable,'-B',str(HERE/'replay_successor.py'),'dryrun','--out',str(out),
                     '--plan-sha256',sha(out/'plan.json')])

if __name__=='__main__':main()
