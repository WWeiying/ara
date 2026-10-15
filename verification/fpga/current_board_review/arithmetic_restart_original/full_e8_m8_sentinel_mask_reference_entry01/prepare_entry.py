"""Bounded local preparation only; never invokes Spike, compiler or full checker."""
from context import *
import subprocess,time,os
def phase(name,script,seconds):
    pins={str(p):sha(p) for p in HERE.glob('*.py')}
    save(HERE/(name+'_preflight.json'),pins)
    command=[sys.executable,'-B',str(HERE/script)]
    save(HERE/(name+'_command.json'),dict(command=command,timeout_s=seconds,not_reference=True))
    t=time.monotonic();timed=False
    with (HERE/(name+'.log')).open('x') as log:
        child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
        try:rc=child.wait(timeout=seconds)
        except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
        with (HERE/(name+'_execution.json')).open('x') as f:
            json.dump(dict(actual_wait_returncode=rc,pid=child.pid,elapsed_s=time.monotonic()-t,timed_out=timed,retries=0),f,indent=2)
            f.flush();os.fsync(f.fileno())
    require(all(sha(p)==h for p,h in pins.items()),'Prep code drift')
    save(HERE/(name+'_postflight.json'),pins)
    require(rc==0 and not timed,'Actual preparation child failure '+name)
phase('profile','derive_profile.py',120)
phase('host01','test_entry.py',120)
