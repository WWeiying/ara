"""One review-gated finite Spike and one audit; durable actual waits first."""
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def save(path,value):
    with Path(path).open('x') as f:
        json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())


def limited():
    resource.setrlimit(resource.RLIMIT_FSIZE,(768*1024*1024,768*1024*1024))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))


def wait(command,prefix,seconds,limits=None):
    save(prefix.with_suffix('.command.json'),dict(command=command,cwd=str(HERE),limit_s=seconds))
    start=time.monotonic();timed=False
    with prefix.with_suffix('.log').open('x') as log:
        child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT,
            start_new_session=True,preexec_fn=limits)
        try:rc=child.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            timed=True;os.killpg(child.pid,signal.SIGKILL);rc=child.wait()
        result=dict(actual_wait_exit=rc,timed_out=timed,elapsed_s=time.monotonic()-start,pid=child.pid,retries=0,validated=False)
        save(prefix.with_suffix('.wait.json'),result)
    return result


def run():
    review_path=Path(sys.argv[1]).resolve();assert sha(review_path)==sys.argv[2]
    review=read(review_path);entry=read(HERE/'ENTRY.json')
    assert review['status']=='NO_BLOCKER_MASKED_FULL17920_REFERENCE_ONCE'
    assert review['entry_sha256']==sha(HERE/'ENTRY.json')
    assert review['input_pins_sha256']==sha(HERE/'input_pins.json')
    pins=read(HERE/'input_pins.json')
    pins.update({str(p):sha(p) for p in (review_path,HERE/'ENTRY.json',HERE/'input_pins.json')})
    assert all(sha(p)==v for p,v in pins.items())
    spec=read(HERE/'spec.json');out=HERE/'run01';out.mkdir()
    save(out/'inputs_before.json',pins)
    try:
        debug=out/'spike.cmd';debug.write_text('rs 4000000\nquit\n')
        command=[entry['spike'],'-d','--debug-cmd='+str(debug),'--isa=rv64gcv_zfh_zvfh_zvl1024b',
            '-m2','--log-commits','--log='+str(out/'commits.log'),spec['elf']]
        actual=wait(command,out/'spike',120,limited)
        assert actual['actual_wait_exit']==0 and not actual['timed_out'],'Spike outcome'
        raw=out/'commits.log';assert 0<raw.stat().st_size<=768*1024*1024
        assert all(sha(p)==v for p,v in pins.items()),'Inputs before audit'
        audited=wait([sys.executable,'-B',str(HERE/'audit_once.py'),str(raw),str(out/'audit01')],out/'audit',600)
        assert audited['actual_wait_exit']==0 and not audited['timed_out'],'Audit outcome'
        result=read(out/'audit01/result.json')
        assert result['status']=='REFERENCE_FULL17920_PASS_SOURCE_ONLY_NOT_DUT'
        assert result['calls']==17920 and result['record_LD']==8960 and result['firmware_to_HTIF']<=3000000
        assert result['closed_raw_parses']==1 and result['EOF_pure_park']
        assert all(sha(p)==v for p,v in pins.items()),'Post-input pins'
        save(out/'inputs_after.json',pins)
        save(out/'COMPLETE.json',dict(status='MASKED_FULL17920_REFERENCE_PASS_NOT_DUT',
            actual_spike=actual,actual_audit=audited,result=result,
            result_sha256=sha(out/'audit01/result.json'),pins_unchanged=True,
            attempts=1,reference_executed=True,DUT_executed=False))
        print('MASKED_REFERENCE_PASS',result['firmware_to_HTIF'],flush=True)
    except BaseException as error:
        save(out/'STOPPED.json',dict(status='NOT_ACCEPTED_NO_RETRY',firstcause=repr(error)))
        raise


if __name__=='__main__':run()
