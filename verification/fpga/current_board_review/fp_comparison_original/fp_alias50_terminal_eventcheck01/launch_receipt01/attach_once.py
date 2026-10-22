"""Reviewed once-only eventcheck service attachment, never producer control."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import audit as a
HERE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--review',type=Path,required=True);p.add_argument('--review-sha256',required=True)
    args=p.parse_args()
    ready=a.read(a.HERE/'READY.json');digest=a.sha(a.HERE/'READY.json')
    a.require(digest=='7ab9c8c5f1d3a300797228167424918d202579f543c93ef5f4a0eb01c05e4db8'
        and a.sha(args.review)==args.review_sha256,'Actual sealed READY/review identity')
    a.require(not(HERE/'ATTACH_ATTEMPT_STARTED.json').exists(),'Once-only attach, no retries')
    a.verify(ready['pins'])
    proc=Path('/proc')/str(ready['worker_pid'])
    a.identity((proc/'cmdline').read_bytes().rstrip(b'\0').decode().split('\0'),
        (proc/'cgroup').read_text(),int((proc/'stat').read_text().rsplit(')',1)[1].split()[19]),ready)
    replace=dict(ACTUAL_AUDITOR_READY_SHA256=digest,
        ACTUAL_INDEPENDENT_TERMINAL_REVIEW_PATH=str(args.review.resolve()),
        ACTUAL_INDEPENDENT_TERMINAL_REVIEW_SHA256=args.review_sha256)
    command=[replace.get(x,x) for x in shlex.split(ready['service_command'])]
    a.save(HERE/'ATTACH_ATTEMPT_STARTED.json',dict(command=command,review=str(args.review.resolve()),
        review_sha256=args.review_sha256,ready_sha256=digest,producer_pid=ready['worker_pid'],
        authorized_by='Main explicit conditional attachment after independent clear',time=time.time()))
    started=time.monotonic()
    process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    stdout,stderr=process.communicate()
    a.save(HERE/'actual_attach_exit_unvalidated.json',dict(returncode=process.returncode,
        management_pid=process.pid,elapsed_s=time.monotonic()-started,command=command,
        DUT_architectural_acceptance=False))
    a.save(HERE/'attach_result.json',dict(returncode=process.returncode,stdout=stdout,stderr=stderr))
    a.require(process.returncode==0,'Attachment management failed, no retry')
    time.sleep(5)
    q=subprocess.run(['systemctl','--user','show','ara-fp-alias50-m6-terminal-eventcheck01.service',
        '--property=Id,LoadState,ActiveState,SubState,MainPID,ControlGroup,Restart,KillMode,RuntimeMaxUSec'],
        text=True,capture_output=True,timeout=10)
    a.save(HERE/'service_metadata.json',dict(returncode=q.returncode,stdout=q.stdout,stderr=q.stderr))
    a.require(q.returncode==0,'Observer service metadata unavailable')
    properties=dict(l.split('=',1) for l in q.stdout.splitlines())
    attached=a.read(a.OUT/'attached.json')
    a.require(properties['ActiveState']=='active' and properties['SubState']=='running'
        and properties['MainPID']==str(attached['observer_pid']) and properties['Restart']=='no'
        and properties['KillMode']=='control-group' and attached['producer_pid']==ready['worker_pid'],
        'Direct attached event worker identity')
    a.save(HERE/'ATTACHED_CONFIRMED.json',dict(observer_pid=attached['observer_pid'],
        producer_pid=ready['worker_pid'],unit=properties['Id'],
        ready_sha256=digest,review_sha256=args.review_sha256,service=properties,
        status='WAITING_PIDFD_NO_ACTIVE_CSV_READS',CSV_reads=0,producer_not_modified=True))
    print(a.read(HERE/'ATTACHED_CONFIRMED.json'),flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
