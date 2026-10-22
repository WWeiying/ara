"""Attach-only pidfd event worker. Never opens CSV or dispatches audit/DUT."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import sys
import time

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
AUDITOR=HERE.parent/'nan_min_soc_terminal_audit01'
WORK=HERE.parent/'nan_min_soc_vcs_m6_plan01'
RUN=WORK/'prepared01'
OUT=HERE/'run01'
PID=1745502
GROUP='/user.slice/user-1002.slice/user@1002.service/app.slice/ara-nan-min-two-source-singles-m6-01.service'
PLAN_SHA='d695a5bdcbc72c1d411859fb4dc800899a71848adbd6fd7bf86927c77c875c5f'
PARENT_SHA='2ad535ba669ae50f8bfc3ad39bb3615faa604512fabcd52fbc1643d5ddaea992'
LAUNCH_SHA='4199a32c18f7fd94e72dd8d8d9e07236f48263460c116a1517eb6be46ed0bf08'
AUDITOR_READY_SHA='6d3852c74105e0b9c133ad391157d7bbe90783bcb775d7de212f49a868dfb0e6'
WAIT_SECONDS=7200


def require(ok,why):
    if not ok: raise ValueError(why)


def read(path): return json.loads(Path(path).read_text())


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,value):
    with Path(path).open('x') as stream:
        json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    fd=os.open(Path(path).parent,os.O_RDONLY|os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def identity(argv,cgroup,start_ticks,ready):
    expected=read(RUN/'ready.json')['command']
    expected=[str(WORK/'parent_review.json') if s=='UNRESOLVED_PARENT_REVIEW_JSON' else
              PARENT_SHA if s=='UNRESOLVED_PARENT_REVIEW_SHA256' else s for s in expected]
    require(argv==expected and cgroup.strip()=='0::'+GROUP and
            start_ticks==ready['worker_start_ticks'],'Exact approved worker lifetime/command/cgroup')


def wait_fd(fd,seconds):
    poller=select.poll();poller.register(fd,select.POLLIN)
    events=poller.poll(int(seconds*1000))
    require(events and all(not flags & select.POLLNVAL for _,flags in events) and
            any(flags & select.POLLIN for _,flags in events),'PIDFD timeout/invalid event; no retry')


def empty_cgroup(root=Path('/sys/fs/cgroup')):
    group=root/GROUP.lstrip('/')
    if not group.exists(): return dict(state='removed',path=str(group))
    files=list(group.rglob('cgroup.procs'))
    require(group/'cgroup.procs' in files and all(not f.read_text().strip() for f in files),
            'Residual/unreadable producer cgroup; no closed-terminal claim')
    return dict(state='empty',path=str(group),membership_files=len(files))


def run():
    ready=read(HERE/'READY.json')
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip()==ready['worker_boot_id'],
            'Pinned producer boot identity')
    for p,digest in ready['pins'].items(): require(sha(p)==digest,'Waiter pin drift: '+p)
    require(sha(AUDITOR/'READY.json')==AUDITOR_READY_SHA and sha(RUN/'plan.json')==PLAN_SHA and
            sha(RUN/'launch.json')==LAUNCH_SHA and sha(WORK/'parent_review.json')==PARENT_SHA,
            'Actual sealed auditor/plan/launch/parent identity')
    launch=read(RUN/'launch.json')
    require(launch['owner']['pid']==PID and launch['owner']['properties']['ControlGroup']==GROUP and
            launch['plan_sha256']==PLAN_SHA,'Actual producer launch identity')
    require(not OUT.exists(),'Fresh once-only event worker')
    OUT.mkdir()
    save(OUT/'ATTACH_AUTHORITY.json',dict(scope='User requested metadata-only event worker attached',
         auditor_dispatch_authorized=False,CSV_content_reads=0,producer_budget_unchanged=True))
    try:
        fd=os.pidfd_open(PID)
        try:
            proc=Path('/proc')/str(PID)
            argv=(proc/'cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
            cgroup=(proc/'cgroup').read_text()
            ticks=int((proc/'stat').read_text().rsplit(')',1)[1].split()[19])
            identity(argv,cgroup,ticks,ready)
            save(OUT/'attached.json',dict(status='PIDFD_ATTACHED_NO_CSV_READS',producer_pid=PID,
                producer_start_ticks=ticks,producer_command=argv,producer_cgroup=cgroup,
                observer_pid=os.getpid(),wait_seconds=WAIT_SECONDS,time=time.time()))
            wait_fd(fd,WAIT_SECONDS)
        finally: os.close(fd)
        save(OUT/'worker_exit_event.json',dict(pid=PID,pidfd_exit=True,
             worker_numeric_exit_unavailable=True,service_exit_inferred=False,time=time.time()))
        membership=empty_cgroup()
        spec=importlib.util.spec_from_file_location('sealed_MIN_audit_metadata_gate',AUDITOR/'audit.py')
        audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
        audit.verify(read(AUDITOR/'READY.json')['pins'])
        complete_sha=sha(RUN/'complete.json')
        auth=dict(run_parent_review=str(WORK/'parent_review.json'),run_parent_review_sha256=PARENT_SHA,
                  complete_sha256=complete_sha)
        audit.terminal_gate(auth)
        require(sha(RUN/'complete.json')==complete_sha,'Terminal changed during metadata gate')
        save(OUT/'TERMINAL_METADATA_READY_FOR_MAIN_AUDIT.json',dict(status='CLOSED_TWO_MIN_PASS_METADATA_ONLY',
            complete_sha256=complete_sha,plan_sha256=PLAN_SHA,parent_review_sha256=PARENT_SHA,
            auditor_ready_sha256=AUDITOR_READY_SHA,cgroup=membership,actual_monitor_codes=[0,0],
            active_CSV_reads=0,CSV_parses=0,auditor_started=False,
            actual_audit_approval='REQUIRES_INDEPENDENT_ENTRY_ACCEPTANCE_AND_MAIN_AUTHORIZATION',
            DUT_acceptance_claim=False,service_exit_inferred=False))
    except BaseException as error:
        save(OUT/'STOPPED.json',dict(status='STOPPED_FIRST_ERROR_NO_RETRY',error=repr(error),
             CSV_parses=0,auditor_started=False))
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--attach-only',action='store_true',required=True)
    p.parse_args();run()
