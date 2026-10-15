#!/usr/bin/env python3
"""Prepare/dryrun only unless a new pinned parent review authorizes the direct worker."""
import argparse
from contextlib import contextmanager
from dataclasses import asdict
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import threading
import time

sys.dont_write_bytecode=True
import checker
import nf2_gate
from checker import HERE, ROOT, common, read, sha, require


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m


frozen=load('nf7_common_checked_worker',ROOT/'ordered_reduction/original_remaining9_vcs_m6_plan01/replay.py')
IMAGE=Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image')
JOBS,TIMEOUT,GROUP_BOUND,WORKER_BOUND,OUTER=4,2400,2700,16200,16800
UNIT='ara-nf7-current96-m6-02.service'
PASS='PASS_M6_NF7_SOURCE_DERIVED96_GROUPS24_NOT_LINUX'
NF2=ROOT/'masked_translation/segment_review/nf2_remaining34_vcs_m6_plan01/prepared01'


def validate_contract(plan,cases):
    require(plan['status']=='PREPARED_NOT_RUN' and plan['image']==str(IMAGE) and
            plan['image_sha256']==checker.IMAGE_SHA,'Exact M6 identity')
    require(plan['cases']==cases and len(cases)==24 and [c['id'] for c in cases]==checker.SHAPES and
            [t for c in cases for t in c['trials']]==list(range(96)),'Exact24/96 membership/order')
    require(plan['jobs']==JOBS and plan['timeout_s']==TIMEOUT and plan['group_timeout_s']==GROUP_BOUND and
            plan['worker_timeout_s']==WORKER_BOUND and plan['service_timeout_s']==OUTER and plan['unit']==UNIT,
            'Original limits / direct owner')
    require(all(plan[k] is True for k in ('no_build','no_retry','no_fsdb','no_coverage','stop_first_fail')),
            'No-build/no-retry/no-probe contract')
    require(plan['old_manifest_sha256']==checker.READY_SHA and plan['old_acceptance_sha256']==checker.AUDIT_SHA,
            'M2 source acceptance binding')
    require(type(plan['reserved_slots']) is int and 0<=plan['reserved_slots']<=24,'Unused reservations only')
    require(plan['nf2_prerequisite']==nf2_gate.contract(),'Exact NF2 independent prerequisite contract')


def disk_gate(out,digest):
    require(digest and sha(out/'plan.json')==digest,'Fresh disk plan SHA mismatch')
    plan=read(out/'plan.json');validate_contract(plan,checker.scope())
    require(sha(IMAGE/'image.json')==checker.IMAGE_SHA,'Frozen image drift')
    common.base.verify_pins(plan['pins'])
    require(sha(out/'plan.json')==digest,'Plan changed during verification')
    return plan


def prepare(out,reserved):
    require(not out.exists(),'Fresh owned preparation only')
    host=read(HERE/'host01/status.json')
    require(host['status']=='PASS_HOST_ONLY_NOT_DUT' and host['failures']==0,'Host acceptance missing')
    common.base.verify_pins(host['pins'])
    cases=checker.scope();pins=checker.source_pins(cases);pins.update(nf2_gate.static_pins())
    require(sha(IMAGE/'image.json')==checker.IMAGE_SHA,'Exact immutable M6')
    ledger,repo,_=common.image_context(IMAGE)
    pins.update(common.image_pins(IMAGE,ledger,repo));pins.update(host['pins'])
    for m in list(sys.modules.values()):
        p=getattr(m,'__file__',None)
        if p and Path(p).is_file() and str(Path(p).resolve()).startswith('/home/wangwy/'):
            pins[str(Path(p).resolve())]=sha(Path(p))
    for n in ('checker.py','observer.py','replay.py','nf2_gate.py','test_nf2_gate.py','test_host.py','README.md','host01/status.json','host01/log.txt'):
        pins[str(HERE/n)]=sha(HERE/n)
    plan=dict(status='PREPARED_NOT_RUN',image=str(IMAGE),image_sha256=checker.IMAGE_SHA,
        snapshot_sha256=ledger['snapshot_sha256'],cases=cases,pins=pins,jobs=JOBS,timeout_s=TIMEOUT,
        group_timeout_s=GROUP_BOUND,worker_timeout_s=WORKER_BOUND,service_timeout_s=OUTER,unit=UNIT,
        reserved_slots=reserved,no_build=True,no_retry=True,no_fsdb=True,no_coverage=True,stop_first_fail=True,
        nf2_prerequisite=nf2_gate.contract(),
        old_manifest_sha256=checker.READY_SHA,old_acceptance_sha256=checker.AUDIT_SHA,
        budget=dict(original_case_s=2400,original_group_s=2700,waves=6,
                    worker_s=6*2700,original_four_job_service_s=16800,outer_headroom_s=600,
                    observed_M2_ordered_four_job_estimate_s=9689.74754808098,completion_guaranteed=False),
        unresolved_launch_gates=['new pinned parent review','NF2 whole-batch terminal and independent review',
                                 'live capacity24 / available32GiB / parent reservations','direct owning cgroup'],
        resource_queries_during_prepare=False,new_reference_required=False,
        raw_child_outcome_before_all_runner_postchecks=True,scope='same24 ELFs,96 source-derived trials; not Linux')
    validate_contract(plan,cases);common.base.verify_pins(pins)
    out.mkdir();common.save(out/'plan.json',plan);digest=sha(out/'plan.json')
    worker=[sys.executable,'-B',str(HERE/'replay.py'),'run','--out',str(out),'--authorize-run',
            '--plan-sha256',digest,'--parent-review','PARENT_REVIEW_JSON','--parent-review-sha256','PARENT_REVIEW_SHA256']
    command=['systemd-run','--user','--unit='+UNIT,'--property=RuntimeMaxSec='+str(OUTER),
        '--property=KillMode=control-group','--property=Restart=no','--property=WorkingDirectory='+str(HERE),
        '--property=StandardOutput=append:'+str(out/'service.log'),
        '--property=StandardError=append:'+str(out/'service.log'),*worker]
    common.save(out/'ready.json',dict(status='PREPARED_NOT_ADMITTED_NO_DUT',plan_sha256=digest,
        worker_command=worker,service_command=shlex.join(command),pins=len(pins),VCS_started=False,
        parent_launch_gates='UNRESOLVED'))
    print('PREPARED_NOT_ADMITTED_NO_DUT',digest,flush=True)


def persist_child(command,cwd,result):
    code,elapsed,timed_out,failure_seen=result
    root=Path(cwd).parent
    record=dict(schema='UNVALIDATED_SIMULATOR_OUTCOME_V1',architectural_acceptance=False,
        returncode=code,elapsed_s=elapsed,timed_out=timed_out,failure_seen=failure_seen,
        command=[str(x) for x in command],cwd=str(cwd),command_sha256=None)
    try:record['command_sha256']=sha(root/'command.json')
    except OSError as error:record['command_identity_error']=f'{type(error).__name__}: {error}'
    with (root/'child_outcome.unvalidated.json').open('x') as stream:
        json.dump(record,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())


def monitored(original,abort):
    def run(command,cwd,console,timeout,cancel=None):
        try:
            result=original(command,cwd,console,timeout,cancel)
            persist_child(command,cwd,result)
            return result
        except BaseException:
            abort.set();raise
    return run


@contextmanager
def engine_hooks(engine,abort):
    old_monitor,old_fail=engine._run_monitored,engine.FAIL_RE
    engine._run_monitored=monitored(old_monitor,abort)
    engine.FAIL_RE=re.compile(old_fail.pattern+'|'+checker.VETO.pattern,re.I)
    try:yield
    finally:engine._run_monitored,engine.FAIL_RE=old_monitor,old_fail


def owner_gate(p,cgroup,pid):
    fields={'Id','LoadState','ActiveState','SubState','MainPID','ControlGroup','RuntimeMaxUSec','KillMode','Restart'}
    require(set(p)==fields and p['Id']==UNIT and p['LoadState']=='loaded' and p['ActiveState']=='active' and
        p['SubState']=='running' and p['MainPID']==str(pid) and p['ControlGroup'].endswith('/'+UNIT) and
        p['ControlGroup'] in [x.split(':',2)[-1] for x in cgroup.splitlines()] and
        p['RuntimeMaxUSec']=='4h 40min' and p['KillMode']=='control-group' and p['Restart']=='no',
        'Direct owning service / unchanged outer bound required')


def authorization(digest,path,path_sha):
    require(path and path_sha and sha(path)==path_sha,'New pinned parent authorization required')
    r=read(path)
    require(r['decision']=='AUTHORIZE_NF7_CURRENT96_M6_ONCE' and r['plan_sha256']==digest and r['unit']==UNIT and
            r['image_sha256']==checker.IMAGE_SHA and r['budget_risk_accepted'] is True,'Parent scope/budget binding')
    # Isolate the sealed NF2 admission's module imports from this worker/checker.
    pins=json.loads(subprocess.check_output([sys.executable,'-B',str(HERE/'nf2_gate.py'),
        '--parent-review',str(path)],cwd=HERE,text=True))
    require(sha(path)==path_sha,'Parent authorization changed during NF2 validation')
    require(str(path) not in pins or pins[str(path)]==path_sha,'Conflicting authorization pin')
    pins[str(path)]=path_sha
    return pins


def options(cls,repo,out,image,dry=False):
    return cls(repo_root=repo,output_root=out/('dryrun' if dry else 'replay'),config='default',
        jobs=JOBS,seed=1,dry_run=dry,build_only=False,skip_build=True,simv=Path(image['simv']),
        commit_trace=True,timeout_s=TIMEOUT,code_coverage=False)


def tests(cls,cases):
    return [cls(c['id'],'app','',Path(c['elf']),c['id'],TIMEOUT) for c in cases]


def dryrun(out,digest):
    plan=disk_gate(out,digest);require(not (out/'dryrun').exists(),'Fresh dryrun only')
    image,repo,(parent,opts,testcase,_)=common.image_context(IMAGE)
    results=parent(options(opts,repo,out,image,True),tests(testcase,plan['cases']),sys.argv).run()
    require([r.name for r in results]==checker.SHAPES and all(r.status=='DRY_RUN' for r in results),'Exact24 dryrun')
    disk_gate(out,digest)
    common.save(out/'dryrun_gate.json',dict(status='DRYRUN24_PASS_NOT_DUT',plan_sha256=digest,
        cases=[r.name for r in results],jobs=JOBS,timeout_s=TIMEOUT,no_build=True,launch_gates='UNRESOLVED'))


def terminal_gate(results,metadata,abort,image,cases):
    common.check_stage(results,metadata,cases,abort)
    require(metadata['tests']==checker.SHAPES and metadata['completed_at'] and metadata['jobs']==JOBS and
        metadata['timeout_s']==TIMEOUT and metadata['simv']==image['simv'] and metadata['seed']==1 and
        metadata['commit_trace'] is True and metadata['code_coverage'] is False,'Exact COMPLETE contract')
    for r,c in zip(results,cases):
        require(r.name==c['id'] and type(r.returncode) is int and r.returncode==0 and not r.reason and
                0<=r.elapsed_s<=TIMEOUT,'Actual numeric exit / original budget')


def run(out,digest,allowed,review,review_sha):
    require(allowed,'No launch authorization')
    plan=disk_gate(out,digest);approvals=authorization(digest,review,review_sha)
    image,repo,(parent,opts,testcase,_)=common.image_context(IMAGE)
    frozen.UNIT=UNIT;frozen.owner_gate=owner_gate
    owner=frozen.service_identity()
    capacity=common.resources(out,JOBS,plan['reserved_slots'])
    require(not (out/'replay').exists() and not (out/'launch.json').exists(),'No retry / fresh output only')
    with (out/'launch.json').open('x') as f:
        json.dump(dict(owner=owner,admission=capacity,approval_pins=approvals,plan_sha256=digest,started=time.time()),f,indent=2)
    abort=threading.Event();lock=threading.Lock();deadline=time.monotonic()+WORKER_BOUND;deadlines={}
    terminal=dict(status='NOT_PASS',plan_sha256=digest,image_sha256=checker.IMAGE_SHA,
                  results=[],retries=0,pins_unchanged=False)
    def fail(name,error):
        abort.set()
        with lock:
            if not (out/'firstfailure.json').exists():
                common.save(out/'firstfailure.json',dict(case=name,error=str(error),time=time.time()))
    timer=threading.Timer(WORKER_BOUND,lambda:fail('worker','16200s worker envelope'));timer.daemon=True
    entries={c['id']:c for c in plan['cases']}
    def admit(name):
        require(name in entries and not abort.is_set(),'Unknown/aborted dispatch')
        require(time.monotonic()+GROUP_BOUND<=deadline,'Insufficient budget for unchanged2700s group; no retry')
    def check(result):
        report=checker.artifacts(result,entries[result.name],image,deadlines[result.name])
        common.save(result.artifact_dir/'strict_original.json',report)
    checked=frozen.checked_runner(parent,abort,check,admit)
    class Runner(checked):
        def _run_test(self,test,simv):
            started=time.monotonic();deadlines[test.name]=started+GROUP_BOUND
            clock=threading.Timer(GROUP_BOUND,lambda:fail(test.name,'Original2700s group bound'))
            clock.daemon=True;clock.start()
            try:
                r=super()._run_test(test,simv)
                if time.monotonic()>=deadlines[test.name]:fail(test.name,'Group elapsed exceeded')
                if r.status!='PASS':fail(test.name,r.reason)
                if abort.is_set() and r.status=='PASS':r.status,r.reason='CANCELLED','Sticky abort'
                return r
            except BaseException as e:fail(test.name,e);raise
            finally:clock.cancel();clock.join()
    import ara_verify.runner as engine
    with common.abort_signals(abort),engine_hooks(engine,abort):
        timer.start()
        try:
            results=Runner(options(opts,repo,out,image),tests(testcase,plan['cases']),sys.argv).run()
            terminal['results']=[dict(asdict(r),artifact_dir=str(r.artifact_dir)) for r in results]
            terminal_gate(results,read(out/'replay/run.json'),abort,image,plan['cases'])
            require(read(out/'replay/summary.json')==terminal['results'],'Summary drift')
            disk_gate(out,digest);common.image_context(IMAGE);common.base.verify_pins(approvals)
            evidence={str(p):sha(p) for p in (out/'launch.json',out/'replay/run.json',out/'replay/summary.json')}
            for c in plan['cases']:
                root=out/'replay/tests'/c['id']
                for n in ('input.elf','inputs.json','command.json','console.log','work/run.vcs.log',
                          'commit_trace.csv','trace_summary.json','child_outcome.unvalidated.json',
                          'observer.command.json','observer.stdout','observer.stderr','observer.json','strict_original.json'):
                    evidence[str(root/n)]=sha(root/n)
            require(sha(out/'plan.json')==digest,'Late disk plan drift')
            terminal.update(status=PASS,pins_unchanged=True,evidence_pins=evidence,
                            trials=list(range(96)),groups=24,checks=284816,checkpoints=168,Linux_replay=False)
        except BaseException as e:
            fail('terminal',e);terminal.update(status='NOT_PASS',error=f'{type(e).__name__}: {e}')
            if (out/'replay/summary.json').exists():terminal['results']=read(out/'replay/summary.json')
        finally:
            frozen.quiesce_deadline(timer,abort,deadline)
            terminal['finished']=time.time();common.publish(out,terminal,abort)
    print(terminal['status'],flush=True);return int(terminal['status']!=PASS)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['prepare','dryrun','run'])
    p.add_argument('--out',type=Path,required=True);p.add_argument('--reserved-slots',type=int,default=0)
    p.add_argument('--authorize-prepare',action='store_true');p.add_argument('--authorize-run',action='store_true')
    p.add_argument('--plan-sha256');p.add_argument('--parent-review',type=Path);p.add_argument('--parent-review-sha256')
    a=p.parse_args();out=a.out.resolve();require(out.parent==HERE,'Only owned direct child output')
    env=common.base.shared.environment();os.environ.clear();os.environ.update(env)
    if a.mode=='prepare':require(a.authorize_prepare,'Prepare authorization missing');prepare(out,a.reserved_slots);return 0
    if a.mode=='dryrun':dryrun(out,a.plan_sha256);return 0
    return run(out,a.plan_sha256,a.authorize_run,a.parent_review,a.parent_review_sha256)


if __name__=='__main__':raise SystemExit(main())
