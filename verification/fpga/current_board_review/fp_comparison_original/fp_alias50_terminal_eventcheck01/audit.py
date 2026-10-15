"""Pidfd conditional full50 terminal audit: no active CSV reads or DUT dispatch."""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
sys.dont_write_bytecode=True

HERE=Path(__file__).resolve().parent
WORK=HERE.parent/'fp_alias50_vcs_m6_realmarkers01'
RUN=WORK/'prepared01'
OUT=HERE/'run01'
PLAN_SHA='545cc6ae73198f80f334c1056fd7e76eccc22555c67ce84ea8f79599a5bc8560'
PARENT_SHA='04a894e41c597902939930d841b0c54e1917dc78dcb4ace39460d14ab775744f'
GENERIC=Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/verification/ara_verify/trace.py')
NAME='alias_v8_e16m8_prefix50'
WAIT_SECONDS=9000
AUDIT_SECONDS=1500

def require(ok,why):
    if not ok:raise ValueError(why)

def read(path):return json.loads(Path(path).read_text())

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def save(path,value):
    with Path(path).open('x') as f:
        json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    fd=os.open(Path(path).parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

def verify(pins,raws=()):
    for p,h in pins.items():
        if Path(p) not in raws:require(sha(p)==h,'Pin drift '+p)

def modules():
    sys.path.insert(0,str(WORK))
    import replay
    sp=importlib.util.spec_from_file_location('alias50_terminal_frozen_protocol',GENERIC)
    protocol=importlib.util.module_from_spec(sp);sp.loader.exec_module(protocol)
    sp=importlib.util.spec_from_file_location('alias50_terminal_lossless',HERE/'observer.py')
    mod=importlib.util.module_from_spec(sp);sp.loader.exec_module(mod)
    return replay,protocol,mod.Observer

def identity(argv,cgroup,start_ticks,ready):
    require(argv==ready['worker_command'] and cgroup.strip()=='0::'+ready['worker_cgroup']
        and start_ticks==ready['worker_start_ticks'],'Actual worker lifetime/command/group mismatch')

def empty_cgroup(group):
    root=Path('/sys/fs/cgroup')/group.lstrip('/')
    if not root.exists():return dict(state='removed',path=str(root))
    files=list(root.rglob('cgroup.procs'))
    require(root/'cgroup.procs' in files and all(not f.read_text().strip() for f in files),
            'Producer group still owns processes; terminal not closed')
    return dict(state='empty',path=str(root))

def terminal_gate(ready):
    worker,protocol,Observer=modules()
    require(sha(RUN/'plan.json')==PLAN_SHA and sha(WORK/'parent_review.json')==PARENT_SHA,'Exact producer plan/parent')
    worker.authorization_gate(PLAN_SHA,WORK/'parent_review.json',PARENT_SHA)
    terminal=read(RUN/'complete.json')
    require(terminal['status']==worker.PASS and terminal['plan_sha256']==PLAN_SHA
        and terminal['aborted'] is False and terminal['pins_unchanged'] is True
        and terminal['retries']==0 and not terminal.get('error'),'Whole first50 PASS required')
    require(not(RUN/'first_cause.json').exists(),'Sticky worker failure')
    plan=read(RUN/'plan.json');ledger=read(Path(plan['image'])/'image.json')
    require(terminal['results']==read(RUN/'replay/summary.json') and len(terminal['results'])==1,'Exact complete membership')
    results=[SimpleNamespace(**dict(r,artifact_dir=Path(r['artifact_dir']))) for r in terminal['results']]
    worker.worker.terminal_gate(results,read(RUN/'replay/run.json'),threading.Event(),ledger)
    result=results[0];root=RUN/'replay/tests'/NAME
    require(result.name==NAME and result.artifact_dir==root and result.status=='PASS'
        and type(result.returncode) is int and result.returncode==0 and not result.reason
        and 0<=result.elapsed_s<=7200 and not(root/'first_cause.json').exists(),'Exact numeric case PASS/no cause')
    child=read(root/'child_outcome.unvalidated.json')
    require(child['name']==NAME and child['source_label']==worker.HISTORICAL
        and type(child['returncode']) is int and child['returncode']==0
        and child['timed_out'] is False and child['failure_seen'] is False
        and child['architectural_acceptance'] is False and 0<=child['elapsed_s']<=7200
        and child['timeout_s']==7200,'Actual monitor rc0 before postcheck')
    command=read(root/'command.json')
    expected=dict(command=worker.monitor_command(root,ledger['simv'],NAME),cwd=str(root/'work'))
    require(command==expected and child['command']==expected['command'] and child['cwd']==expected['cwd'],'Actual private command')
    provenance=read(root/'child_command.provenance.json')
    require(provenance['command']==command and provenance['command_sha256']==sha(root/'command.json')
        and provenance['actual_monitor_command']==command['command'],'Durable command provenance')
    require(sha(RUN/'launch.json')==ready['launch_sha256']
        and read(RUN/'launch.json')['owner']['pid']==ready['worker_pid'],'Actual original launch identity')
    return worker,protocol,Observer,plan,terminal,result,ledger

class HashLines:
    def __init__(self,path):
        self.stream=path.open('rb');self.hash=hashlib.sha256();self.bytes=0
    def __iter__(self):return self
    def __next__(self):
        line=self.stream.readline()
        if not line:raise StopIteration
        self.hash.update(line);self.bytes+=len(line)
        return line.decode('utf-8')

def raw_identity(path):
    s=path.stat()
    return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]

def child(ready_sha):
    require(sys.flags.optimize==0,'Mature assertions must remain enabled')
    require(sha(HERE/'READY.json')==ready_sha,'Sealed auditor READY')
    ready=read(HERE/'READY.json');verify(ready['pins'])
    worker,protocol,Observer,plan,terminal,result,ledger=terminal_gate(ready)
    complete_sha=sha(RUN/'complete.json')
    require(complete_sha==read(OUT/'terminal_gate.json')['complete_sha256'],'Closed wholePASS identity')
    root=result.artifact_dir;raw=root/'commit_trace.csv'
    pins=worker.merge_pins(plan['pins'],terminal['evidence_pins'],ready['pins'],
        {str(RUN/'complete.json'):complete_sha,str(HERE/'READY.json'):ready_sha,
         str(WORK/'parent_review.json'):PARENT_SHA})
    verify(pins,[raw]);save(OUT/'pins_pre.json',pins)
    case=plan['cases'][0];spec=plan['specs'][NAME]
    require(spec==worker.checker.specification(Path(case['elf'])),'Actual immutable source ELF/spec')
    worker.common.check_artifacts(result,case,ledger)
    for p in (root/'console.log',root/'work/run.vcs.log'):worker.checker.console_gate(p.read_text())
    before=raw_identity(raw);stream=HashLines(raw);observer=Observer(protocol)
    try:
        strict=worker.checker.source.audit(worker.checker.convert(observer.rows(csv.DictReader(stream))),spec)
        generic=observer.finish()
    finally:stream.stream.close()
    require(raw_identity(raw)==before and stream.bytes==before[2],'Closed raw stable inode/size/time/EOF')
    require(stream.hash.hexdigest()==terminal['evidence_pins'][str(raw)],'Whole raw hash in sole parse')
    require(strict['retired']==generic['retire_count']
        and [strict[k] for k in ('target_calls','full_result_bit_checks','guard_checks',
                                'returned_vstart_zero','returned_flags_checked','helper_instructions',
                                'actual_initialization_stores','unused_helper_retirements')]==
            [50,25600,100,50,50,800,64100,0],'Full original source oracle, no scope shrink')
    generated=dict(strict=strict,generic=generic,csv_sha256=stream.hash.hexdigest(),
        scope='All25600 source bits/100guards/50flags/vstarts; scalar CSV, not direct vector-port payload')
    require(json.loads(json.dumps(generated))==read(root/'strict_original.json'),'Independent full result agreement')
    require(dict(generic,status='VALID')==read(root/'trace_summary.json'),'Frozen six-event protocol result agreement')
    verify(pins,[raw]);save(OUT/'pins_post.json',pins)
    save(OUT/'result.json',dict(status='INDEPENDENT_ORIGINAL_ALIAS50_ARCHITECTURAL_ACCEPTED_NOT_FULL_PARENT',
        generated=generated,csv_parses=1,raw_identity=before,raw_bytes=stream.bytes,
        row_delivery_unchanged=observer.before.digest()==observer.after.digest(),
        pins_pre_post_unchanged=True,full_parent_accepted=False,reference_used_as_DUT_evidence=False,
        direct_vector_payload_claimed=False,source_scope='original first50/49 predecessors, not682/fullparent/Linux',
        old_cancelled_attempt_unchanged=True,no_DUT_REF_build=True))

def wait_child(process,started,seconds):
    timed_out=False
    try:code=process.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        timed_out=True;process.kill();code=process.wait()
    # Actual numeric outcome is durable before any result/pin/metadata checks.
    save(OUT/'actual_exit_unvalidated.json',dict(returncode=code,child_pid=process.pid,
        elapsed_s=time.monotonic()-started,timed_out=timed_out,validated=False))
    return code,timed_out

def attach(ready_sha,review_path,review_sha):
    require(sha(HERE/'READY.json')==ready_sha and review_path and review_sha
        and sha(review_path)==review_sha,'Actual reviewed sealed eventcheck required')
    ready=read(HERE/'READY.json');verify(ready['pins'])
    require(Path('/proc/sys/kernel/random/boot_id').read_text().strip()==ready['worker_boot_id'],'Same worker boot')
    require(not OUT.exists(),'Fresh once-only attachment');OUT.mkdir()
    save(OUT/'ATTACH_AUTHORITY.json',dict(
        scope='Main explicitly authorized conditional attach after independent no-blocker review',
        review_path=str(review_path),review_sha256=review_sha,ready_sha256=ready_sha,
        actual_main_parent_path=str(WORK/'parent_review.json'),actual_main_parent_sha256=PARENT_SHA,
        no_DUT_retry=True,CSV_content_reads=0,conditional_audit_only_after_closed_wholePASS_numeric0=True))
    try:
        fd=os.pidfd_open(ready['worker_pid'])
        try:
            proc=Path('/proc')/str(ready['worker_pid'])
            identity((proc/'cmdline').read_bytes().rstrip(b'\0').decode().split('\0'),
                (proc/'cgroup').read_text(),
                int((proc/'stat').read_text().rsplit(')',1)[1].split()[19]),ready)
            save(OUT/'attached.json',dict(producer_pid=ready['worker_pid'],observer_pid=os.getpid(),
                status='PIDFD_ATTACHED_NO_ACTIVE_CSV_READ',wait_seconds=WAIT_SECONDS,time=time.time()))
            poller=select.poll();poller.register(fd,select.POLLIN)
            events=poller.poll(WAIT_SECONDS*1000)
            require(events and any(f&select.POLLIN for _,f in events)
                and all(not f&select.POLLNVAL for _,f in events),'Pidfd timeout/invalid; no retry')
        finally:os.close(fd)
        save(OUT/'worker_exit_event.json',dict(pid=ready['worker_pid'],pidfd_exit=True,
            worker_numeric_exit_unavailable=True,service_exit_inferred=False,time=time.time()))
        membership=empty_cgroup(ready['worker_cgroup'])
        terminal_gate(ready)
        digest=sha(RUN/'complete.json')
        save(OUT/'terminal_gate.json',dict(status='CLOSED_ORIGINAL50_PASS_MONITOR0',
            complete_sha256=digest,cgroup=membership,CSV_parses=0,actual_monitor_rc=0))
        command=[sys.executable,'-B',str(HERE/'audit.py'),'child','--ready-sha256',ready_sha]
        save(OUT/'AUDIT_ATTEMPT_STARTED.json',dict(command=command,timeout_s=AUDIT_SECONDS,retries=0))
        with (OUT/'audit.log').open('x') as log:
            start=time.monotonic()
            p=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
            code,timed_out=wait_child(p,start,AUDIT_SECONDS)
        require(code==0 and not timed_out,'Audit actual child failure; no retry')
        require(read(OUT/'pins_pre.json')==read(OUT/'pins_post.json'),'Audit pin snapshots unchanged')
        require(read(OUT/'result.json')['status']=='INDEPENDENT_ORIGINAL_ALIAS50_ARCHITECTURAL_ACCEPTED_NOT_FULL_PARENT','Actual independent acceptance')
        save(OUT/'TERMINAL.json',dict(status='ACCEPTED_ORIGINAL_ALIAS50_NOT_FULL_PARENT',
            result_sha256=sha(OUT/'result.json'),actual_execution_sha256=sha(OUT/'actual_exit_unvalidated.json'),
            complete_sha256=digest,plan_sha256=PLAN_SHA,full_parent_accepted=False,CSV_parses=1))
    except BaseException as e:
        save(OUT/'STOPPED.json',dict(status='NOT_ACCEPTED_FIRST_ERROR_NO_RETRY',error=repr(e),
            producer_not_stopped=True,no_new_DUT_REF=True))
        raise

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['attach','child']);p.add_argument('--ready-sha256',required=True)
    p.add_argument('--review',type=Path);p.add_argument('--review-sha256')
    a=p.parse_args()
    if a.mode=='child':child(a.ready_sha256)
    else:attach(a.ready_sha256,a.review,a.review_sha256)
