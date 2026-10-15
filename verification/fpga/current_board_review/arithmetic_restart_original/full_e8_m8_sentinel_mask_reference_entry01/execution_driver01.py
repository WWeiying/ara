"""Outer wait journal for the uniquely parent-authorized sealed executor."""
import hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
REVIEW=HERE.parent/'e8_m8_sentinel_mask_reference_review01/review.json'
PARENT=HERE/'parent_execution_authorization01.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def durable(path,value):
    with path.open('x') as f:
        json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    fd=os.open(str(path.parent),os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
pins={
    str(HERE/'ENTRY.json'):'6e1591fafa4a90c637a1db9f71c34f090f7b52090c8a2436351d826c8c1ba832',
    str(REVIEW):'4b21b0b556d6a9ad2bc7febd3d82d748e6a38a79d8346bc75d290b8425bc6a60',
    str(PARENT):'03823e9b74053232c0748a1ef16d5566c86e73bb1d9d5ae36217f3b27c579066'}
for p,h in pins.items():
    if sha(Path(p))!=h:raise ValueError('STOP actual launch pin '+p)
command=[sys.executable,'-B',str(HERE/'reference02.py'),'execute',
    '--review',str(REVIEW),'--review-sha',pins[str(REVIEW)],
    '--parent-authorization',str(PARENT),'--parent-sha',pins[str(PARENT)]]
durable(HERE/'outer_command01.json',dict(command=command,pins=pins,
    outer_timeout_s=780,reference_timeout_s=120,audit_timeout_s=600,
    script_sha256=sha(Path(__file__)),executor_sha256=sha(HERE/'reference02.py'),
    one_attempt=True,DUT_authorized=False))
start=time.monotonic();timed=False
with (HERE/'outer01.log').open('x') as log:
    child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    try:rc=child.wait(timeout=780)
    except subprocess.TimeoutExpired:
        timed=True;os.killpg(child.pid,signal.SIGKILL);rc=child.wait()
    durable(HERE/'outer_execution01.json',dict(actual_wait_returncode=rc,pid=child.pid,
        elapsed_s=time.monotonic()-start,timed_out=timed,retries=0,validated=False))
print('actual_outer_wait',rc,'timed_out',timed,flush=True)
raise SystemExit(rc if not timed else 124)
