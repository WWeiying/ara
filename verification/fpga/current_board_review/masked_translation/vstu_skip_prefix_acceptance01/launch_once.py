"""One direct systemd worker; persist real --wait outcome before result checks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
UNIT='ara-vstu-skip-prefix-acceptance01.service'

def save(path,value):
    with path.open('x') as f:
        json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

def main():
    command=['systemd-run','--user','--wait','--unit='+UNIT,
        '--property=RuntimeMaxSec=150','--property=KillMode=control-group','--property=Restart=no',
        '--property=WorkingDirectory='+str(HERE),
        '--property=StandardOutput=append:'+str(HERE/'service01.log'),
        '--property=StandardError=append:'+str(HERE/'service01.log'),
        sys.executable,'-B',str(HERE/'run.py'),'--variant','candidate',
        '--vstu-sha256','37880822b8066fa13e66619dd335cb42db84cdc5730c6f4dff9a3f2fd0af46a0']
    save(HERE/'outer_attempt_started.json',dict(command=command,started=time.time(),retries=0))
    start=time.monotonic()
    p=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    stdout,stderr=p.communicate()
    save(HERE/'outer_wait_actual_exit_unvalidated.json',dict(returncode=p.returncode,
        elapsed_s=time.monotonic()-start,control_process_pid=p.pid,command=command,
        receipt_origin='ACTUAL_SYSTEMD_RUN_WAIT_PROPAGATED_UNIT_RESULT',stdout=stdout,stderr=stderr,
        validated=False))
    if p.returncode!=0:
        print(stderr,flush=True)
        return p.returncode
    require_text='Main processes terminated with: code=exited/status=0'
    if require_text not in stdout+stderr:
        raise ValueError('Missing real worker code=exited/status=0; no retry')
    result=json.loads((HERE/'measurement_candidate01/result.json').read_text())
    if result['state']!='SKIP_PREFIX_ACCEPTED_NOT_SOC_ACCEPTANCE':
        raise ValueError('Actual scoped acceptance absent')
    save(HERE/'outer_worker_exit_verified.json',dict(unit=UNIT,worker_pid=result['pid'],
        worker_code='exited',worker_exit_status=0,systemd_wait_returncode=p.returncode,
        scope='One masked skip/prefix/delayed B/indexed misalignment module case, not SoC',
        evidence=str(HERE/'outer_wait_actual_exit_unvalidated.json'),retries=0))
    print(json.dumps(result,indent=2),flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
