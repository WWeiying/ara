#!/usr/bin/env python3
"""Ten no-build NF2 jobs; prepare/dryrun do not query live simulators."""
import argparse
from dataclasses import asdict
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import sys
import threading
import time
sys.dont_write_bytecode=True
import checker
import gates
from checker import HERE,ROOT,REF,READY_SHA,IMAGE_SHA,common,read,sha,require

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module

frozen=load('nf2_immutable_batch_worker',ROOT/'ordered_reduction/original_remaining9_vcs_m6_plan01/replay.py')
outcome=load('nf2_immutable_outcome',ROOT/'fp_compare_unboxed_prefix265_vcs_m6_plan01/provenance_recovery01/adapter.py')
IMAGE=Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image')
JOBS,MAX_CASE,WORKER_BOUND,OUTER=3,6300,25200,27000
UNIT='ara-nf2-remaining34-j4-m6-01.service'
PASS='PASS_M6_NF2_REMAINING34_PLUS_J4_NOT_LINUX'
PILOT_AUDIT=HERE.parent/'nf2_remaining4_terminal_audit01/terminal01/result.json'
PILOT_SHA='79037611e05a12289eb6734b836f8cbcb5c28658bd0a88f3002fc895d5bb51ee'
PILOT_COMPLETE_SHA='39c697f34c0db5b827cdebb428e7e5181ce0631715cfe8cc71f2d63bf554fcbe'

def validate(plan,image):
    require(image==IMAGE and plan['status']=='PREPARED_NOT_RUN' and plan['image']==str(image) and
            plan['image_sha256']==sha(image/'image.json')==IMAGE_SHA,'Exact M6 image/plan')
    require(plan['cases']==checker.scope() and plan['jobs']==JOBS and plan['timeout_s']==MAX_CASE and
            plan['worker_timeout_s']==WORKER_BOUND and plan['service_timeout_s']==OUTER and
            plan['unit']==UNIT and all(plan[k] is True for k in ('no_build','no_retry','no_fsdb','stop_first_fail')),
            'Exact scope/per-ELF budgets/concurrency/ownership')
    require(plan['reference_ready_sha256']==READY_SHA and plan['independent_reference_pins']==gates.accepted_reference()
            and plan['pilot_audit_sha256']==PILOT_SHA and plan['pilot_complete_sha256']==PILOT_COMPLETE_SHA and
            plan['pilot_contract']==gates.PILOT_CONTRACT,'Actual prerequisite binding')
    require(type(plan['reserved_slots']) is int and 0<=plan['reserved_slots']<=24,'Unused reserved slots only')
    require(plan['pins'].get(str(HERE/'replay.py'))==sha(HERE/'replay.py'),'Worker drift')
    common.base.verify_pins(plan['pins'])

def terminal_plan_gate(out,digest,image):
    require(sha(out/'plan.json')==digest,'Fresh disk plan drift')
    validate(read(out/'plan.json'),image)
    require(sha(out/'plan.json')==digest,'Plan changed during pin validation')

def prepare(image,out,reserved):
    require(image==IMAGE and not out.exists(),'Fresh owned output / exact M6')
    audit_pins=gates.accepted_reference()
    pilot_pins=gates.pilot_gate(PILOT_AUDIT,PILOT_SHA)
    require(sha(gates.PILOT/'complete.json')==PILOT_COMPLETE_SHA,'Exact accepted pilot terminal')
    host=read(HERE/'host01/status.json')
    require(host['status']=='PASS_HOST_ONLY_NOT_DUT' and host['failures']==0,'Host gate')
    common.base.verify_pins(host['pins'])
    ledger,repo,_=common.image_context(image)
    pins={**checker.source_pins(),**audit_pins,**pilot_pins,**host['pins'],**common.image_pins(image,ledger,repo)}
    for module in list(sys.modules.values()):
        p=getattr(module,'__file__',None)
        if p and Path(p).is_file() and Path(p).resolve().is_relative_to(ROOT.parents[2]):
            pins[str(Path(p).resolve())]=sha(Path(p))
    for p in [HERE/n for n in ('checker.py','gates.py','replay.py','test_host.py','README.md','host01/status.json','host01/log.txt')]:
        pins[str(p)]=sha(p)
    plan=dict(status='PREPARED_NOT_RUN',image=str(image),image_sha256=IMAGE_SHA,
        snapshot_sha256=ledger['snapshot_sha256'],cases=checker.scope(),pins=pins,
        jobs=JOBS,timeout_s=MAX_CASE,worker_timeout_s=WORKER_BOUND,service_timeout_s=OUTER,unit=UNIT,
        reserved_slots=reserved,no_build=True,no_retry=True,no_fsdb=True,stop_first_fail=True,
        reference_ready_sha256=READY_SHA,independent_reference_pins=audit_pins,
        pilot_audit_sha256=PILOT_SHA,pilot_complete_sha256=PILOT_COMPLETE_SHA,pilot_contract=gates.PILOT_CONTRACT,
        budget=dict(proxy_records_per_second=273,proxy_margin=1.2,round_up_s=300,
            per_case_validation_reserve_s=600,global_worst_case_protection_not_expected_duration=True,
            list_schedule_cost_bound_s=25000,service_teardown_headroom_s=OUTER-WORKER_BOUND,
            completion_guaranteed=False,no_runtime_budget_increase=True),
        source_failures_new34=34,J4_source_failures=2,J4_positive_controls=2,
        accepted_pilot_source_failures=4,current40_requires_all_ten_jobs_PASS=True,
        J4_previous_acceptance='M2_ONLY_NOT_M6',Linux_signalframe_proved=False,
        resources_checked_only_at_authorized_run=True,unvalidated_child_outcome_before_postcheck=True)
    validate(plan,image);out.mkdir();common.save(out/'plan.json',plan)
    digest=sha(out/'plan.json')
    worker=[sys.executable,'-B',str(HERE/'replay.py'),'run','--image',str(image),'--out',str(out),
        '--authorize-run','--plan-sha256',digest,'--parent-review','PARENT_REVIEW_JSON',
        '--parent-review-sha256','PARENT_REVIEW_SHA256']
    cmd=['systemd-run','--user','--unit='+UNIT,'--property=RuntimeMaxSec='+str(OUTER),
        '--property=KillMode=control-group','--property=Restart=no','--property=WorkingDirectory='+str(HERE),
        '--property=StandardOutput=append:'+str(out/'service.log'),
        '--property=StandardError=append:'+str(out/'service.log'),*worker]
    common.save(out/'ready.json',dict(status='PREPARED_NOT_ADMITTED_NO_DUT',plan_sha256=digest,
        command=worker,service_command=shlex.join(cmd),pins=len(pins),VCS_started=False))
    print('PREPARED_NOT_ADMITTED_NO_DUT',digest,flush=True)

def owner_gate(props,cgroup,pid):
    fields={'Id','LoadState','ActiveState','SubState','MainPID','ControlGroup','RuntimeMaxUSec','KillMode','Restart'}
    require(set(props)==fields and props['Id']==UNIT and props['LoadState']=='loaded' and
        props['ActiveState']=='active' and props['SubState']=='running' and props['MainPID']==str(pid) and
        props['ControlGroup'].endswith('/'+UNIT) and props['ControlGroup'] in [l.split(':',2)[-1] for l in cgroup.splitlines()] and
        props['RuntimeMaxUSec']=='7h 30min' and props['KillMode']=='control-group' and props['Restart']=='no',
        'Direct owning service / hard bound')

def service_identity():
    frozen.UNIT=UNIT;frozen.owner_gate=owner_gate
    return frozen.service_identity()

def authorization_gate(plan,digest,path,path_sha):
    require(path and path_sha and sha(path)==path_sha,'New pinned parent authorization required')
    r=read(path)
    require(r['decision']=='AUTHORIZE_NF2_REMAINING34_J4_M6_ONCE' and r['plan_sha256']==digest and
        r['unit']==UNIT and r['pilot_audit_sha256']==PILOT_SHA and r['budget_risk_accepted'] is True and
        r['independent_reference_pins']==plan['independent_reference_pins'],'Parent identity/scope/budget gate')
    return {str(path):path_sha}

def checked_runner(parent,abort,check,admission):
    class DurableParent(parent):
        def _run_test(self,test,image):
            result=super()._run_test(test,image)
            outcome.persist_unvalidated_outcome(result)
            return result
    return frozen.checked_runner(DurableParent,abort,check,admission)

def deadline_gate(case,now,deadline):
    require(now+case['timeout_s']+checker.VALIDATION_RESERVE<=deadline,
            'Insufficient remaining global bound for unchanged per-ELF budget; no dispatch/retry')

def terminal_gate(results,metadata,abort,ledger,cases):
    common.check_stage(results,metadata,cases,abort)
    require(metadata['tests']==[c['id'] for c in cases] and metadata['completed_at'] and
        metadata['jobs']==JOBS and metadata['timeout_s'] is None and metadata['simv']==ledger['simv'] and
        metadata['seed']==1 and metadata['commit_trace'] is True and metadata['code_coverage'] is False,
        'Exact COMPLETE runner contract')
    for result,case in zip(results,cases):
        require(type(result.returncode) is int and result.returncode==0 and result.name==case['id'] and
            0<=result.elapsed_s<=case['timeout_s'] and not result.reason,'Per-ELF terminal result/budget')

def build_options(options,repo,out,ledger,dry=False):
    return options(repo_root=repo,output_root=out/('dryrun' if dry else 'replay'),config='default',
        jobs=JOBS,seed=1,dry_run=dry,build_only=False,skip_build=True,simv=Path(ledger['simv']),
        # Base runner gives options.timeout_s precedence over TestCase.timeout_s.
        commit_trace=True,timeout_s=None)

def tests_for(testcase,cases):
    return [testcase(c['id'],'app','',Path(c['elf']),c['id'],c['timeout_s']) for c in cases]

def dryrun(image,out,digest):
    terminal_plan_gate(out,digest,image)
    require(not (out/'dryrun').exists(),'Fresh dryrun only')
    ledger,repo,(parent,options,testcase,_)=common.image_context(image)
    cases=read(out/'plan.json')['cases']
    results=parent(build_options(options,repo,out,ledger,True),tests_for(testcase,cases),sys.argv).run()
    require([r.name for r in results]==[c['id'] for c in cases] and all(r.status=='DRY_RUN' for r in results),
            'Exact10 dryrun did not complete')
    common.save(out/'dryrun_gate.json',dict(status='DRYRUN_ONLY_NO_DUT',jobs=JOBS,cases=[r.name for r in results],
                                          plan_sha256=digest))

def run(image,out,digest,authorized,review,review_sha):
    require(authorized and digest,'Explicit new run authorization required')
    terminal_plan_gate(out,digest,image);plan=read(out/'plan.json')
    approvals=authorization_gate(plan,digest,review,review_sha)
    approvals.update(gates.pilot_gate(PILOT_AUDIT,PILOT_SHA))
    ledger,repo,(parent,options,testcase,_)=common.image_context(image)
    require(ledger['snapshot_sha256']==plan['snapshot_sha256'],'Snapshot drift')
    owner=service_identity();resource=common.resources(out,JOBS,plan['reserved_slots'])
    with (out/'launch.json').open('x') as stream:
        json.dump(dict(owner=owner,admission=resource,approval_pins=approvals,
                       started=time.time(),plan_sha256=digest),stream,indent=2)
    abort=threading.Event();deadline=time.monotonic()+WORKER_BOUND
    timer=threading.Timer(WORKER_BOUND,abort.set);timer.daemon=True
    terminal=dict(status='NOT_PASS',plan_sha256=digest,results=[],retries=0,pins_unchanged=False)
    import ara_verify.runner as engine
    old_fail=engine.FAIL_RE;engine.FAIL_RE=re.compile(old_fail.pattern+'|'+checker.VETO.pattern,re.I)
    with common.abort_signals(abort):
        timer.start()
        try:
            require(not (out/'replay').exists(),'No retries or overwrite')
            entries={c['id']:c for c in plan['cases']}
            def admission(name):
                require(name in entries and not abort.is_set(),'Dispatch aborted/unknown')
                deadline_gate(entries[name],time.monotonic(),deadline)
            def check(result):
                strict=checker.artifacts(result,entries[result.name],ledger)
                common.save(result.artifact_dir/'strict_original.json',strict)
            results=checked_runner(parent,abort,check,admission)(
                build_options(options,repo,out,ledger),tests_for(testcase,plan['cases']),sys.argv).run()
            terminal['results']=[dict(asdict(r),artifact_dir=str(r.artifact_dir)) for r in results]
            terminal_gate(results,read(out/'replay/run.json'),abort,ledger,plan['cases'])
            require(read(out/'replay/summary.json')==terminal['results'],'Summary mismatch')
            terminal_plan_gate(out,digest,image);common.image_context(image);common.base.verify_pins(approvals)
            evidence={str(p):sha(p) for p in (out/'launch.json',out/'replay/run.json',out/'replay/summary.json')}
            for case in plan['cases']:
                root=out/'replay/tests'/case['id']
                names=['input.elf','inputs.json','command.json','console.log','work/run.vcs.log','commit_trace.csv',
                    'trace_summary.json','child_outcome.unvalidated.json','observer.command.json','observer.stdout',
                    'observer.stderr','strict_original.json']
                if case['kind']=='remaining34':names.append('observer.json')
                evidence.update({str(root/n):sha(root/n) for n in names})
            require(sha(out/'plan.json')==digest,'Final disk plan drift')
            terminal.update(status=PASS,evidence_pins=evidence,pins_unchanged=True,new34_accepted=True,
                J4_current_M6_accepted=True,positive_controls_not_failure_count=2,
                source_failure_count_with_accepted_pilot=40,Linux_signalframe_proved=False)
        except BaseException as e:
            abort.set();terminal.update(status='NOT_PASS',error=f'{type(e).__name__}: {e}')
            if (out/'replay/summary.json').exists():terminal['results']=read(out/'replay/summary.json')
        finally:
            frozen.quiesce_deadline(timer,abort,deadline)
            engine.FAIL_RE=old_fail;terminal['finished']=time.time()
            common.publish(out,terminal,abort)
    print(terminal['status'],flush=True);return int(terminal['status']!=PASS)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['prepare','dryrun','run'])
    for name in ('image','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--reserved-slots',type=int,default=0)
    for name in ('authorize-prepare','authorize-run'):p.add_argument('--'+name,action='store_true')
    for name in ('plan-sha256','parent-review-sha256'):p.add_argument('--'+name)
    p.add_argument('--parent-review',type=Path)
    a=p.parse_args();image,out=a.image.resolve(),a.out.resolve()
    require(out.parent==HERE,'Owned fresh direct child only')
    env=common.base.shared.environment();os.environ.clear();os.environ.update(env)
    if a.mode=='prepare':
        require(a.authorize_prepare,'Explicit prepare gate');prepare(image,out,a.reserved_slots);return 0
    if a.mode=='dryrun':dryrun(image,out,a.plan_sha256);return 0
    return run(image,out,a.plan_sha256,a.authorize_run,a.parent_review,a.parent_review_sha256)

if __name__=='__main__':raise SystemExit(main())
