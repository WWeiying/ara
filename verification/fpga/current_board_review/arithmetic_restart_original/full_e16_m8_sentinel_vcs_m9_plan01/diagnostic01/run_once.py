"""Actual numeric wait first; host once, reviewed diagnostic once, no retry."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
mode=sys.argv[1];assert mode in ('host','diagnose')
if mode=='diagnose':
    assert len(sys.argv)==4,'Actual independent review path and SHA required'
    path=Path(sys.argv[2]).resolve();digest=sys.argv[3]
    assert sha(path)==digest
    review=read(path);entry=HERE/'ENTRY.json'
    assert review['status']=='NO_BLOCKER_ONE_CLOSED_TIMEOUT_DIAGNOSTIC' and review['entry_sha256']==sha(entry)
    assert review['DUT_authorized'] is False and review['max_scans']==1 and review['scan_timeout_s']==600
    assert not (HERE/'run01').exists()
    save(HERE/'review_binding.json',dict(path=str(path),sha256=digest,entry_sha256=sha(entry),execution_scope='ONE_CLOSED_SCAN_ONLY'))
target=HERE/('test_small.py' if mode=='host' else 'diagnostic.py');bound=120 if mode=='host' else 600
command=[sys.executable,'-B',str(target)]
save(HERE/(mode+'_command.json'),dict(command=command,timeout_s=bound,attempt=1,no_retry=True,
    target_sha256=sha(target),driver_sha256=sha(Path(__file__))))
started=time.monotonic();timed=False
with (HERE/(mode+'.log')).open('x') as log:
    child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    try:rc=child.wait(timeout=bound)
    except subprocess.TimeoutExpired:timed=True;os.killpg(child.pid,9);rc=child.wait()
    save(HERE/(mode+'_wait.json'),dict(actual_wait_returncode=rc,pid=child.pid,elapsed_s=time.monotonic()-started,
        timed_out=timed,retries=0,validated=False))
print(mode,'actual_wait',rc,'timed_out',timed,flush=True)
raise SystemExit(rc if not timed else 124)
