#!/usr/bin/env python3
"""Prepare-only by default; explicit nine-single, no-build M6 replay worker."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import threading
import time

sys.dont_write_bytecode = True
import checker
from checker import HERE, REF, SHAPES, READY_SHA, require, read, sha, common

IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image')
TIMEOUT, OUTER, WORKER_BOUND, JOBS = 5400, 19800, 18900, 3
UNIT = 'ara-redspecial-remaining9-original-m6-01.service'
PASS = 'PASS_M6_ORIGINAL_REMAINING9_SINGLES1296_NOT_FULL_PARENTS'
REVIEW = HERE.parent / 'original_remaining9_reference_audit01/REVIEW.md'
REVIEW_SHA = '4d9bc0f53153a8828aab651477262e2498b38b6d6178eadee34ece1bc3eb5ecc'
AUDIT_SHA = '73d0ab599a46abe7aa4a871dab35d512de1ac98c055349a8eb732eab069fa781'
MF4_PLAN_SHA = '51711836aab45fa44a34f16e80801fb9ac0dbf2412cf6660577e0737c17f013c'
MF4_ELF_SHA = 'eed20f08a98ac66766a66810b6f5f8fc829d0603477d37b3d59d48c32669f162'
MF4_STATUS = 'INDEPENDENT_M6_ORIGINAL_E16_MF4_SINGLE144_ACCEPTED_NOT_FULL_PARENT'
MF4_CONTRACT = dict(status=MF4_STATUS, plan_sha256=MF4_PLAN_SHA, soc_elf_sha256=MF4_ELF_SHA,
    required=['image_sha256', 'complete_path', 'complete_sha256', 'evidence_pins'],
    checked_only_at_authorized_run=True, reference_acceptance_not_sufficient=True)


def accepted_reference():
    require(sha(REF/'READY.json')==READY_SHA and sha(REVIEW)==REVIEW_SHA and
            sha(REVIEW.with_name('result.json'))==AUDIT_SHA,'Independent source/reference drift')
    audit=read(REVIEW.with_name('result.json'))
    require(audit['status']=='INDEPENDENT_REFERENCE_ALL9_ACCEPTED_NOT_DUT' and audit['shapes']==SHAPES,
            'Exact independent nine-reference acceptance')
    ready=read(REF/'READY.json');common.base.verify_pins(ready['case_ready_pins'])
    pins=dict(ready['case_ready_pins'])
    for shape in SHAPES:
        r=read(REF/shape/'READY.json');common.base.verify_pins(r['pins']);pins.update(r['pins'])
    return pins


def scope():
    require(sha(REF/'READY.json')==READY_SHA,'Accepted READY drift')
    cases=[]
    ready=read(REF/'READY.json')
    for shape in SHAPES:
        root=REF/shape
        require(sha(root/'READY.json')==ready['case_ready_pins'][str(root/'READY.json')],'Case READY drift')
        r=read(root/'READY.json');proof=read(root/'sourceproof.json');c=proof['config']
        require(sha(root/'soc/program.elf')==r['soc_sha256'],'ELF drift')
        cases.append(dict(id=c['identity'], original_name=c['identity'], shape=shape,
            elf=str(root/'soc/program.elf'),sha256=r['soc_sha256'],timeout_s=TIMEOUT,
            pass_markers=[f"RVV_FP_REDSPECIAL_PASS sew={c['sew']} cases=1 flags_seen=16 errors=0",
                          'BOARD_CASE_PASS '+c['identity'],'BOARD_REPLAY_PASS']))
    return cases


def validate(plan,image):
    require(image==IMAGE and plan['status']=='PREPARED_NOT_RUN' and plan['image']==str(image) and
            plan['image_sha256']==sha(image/'image.json'),'Image/plan drift')
    require(plan['cases']==scope() and plan['jobs']==JOBS and plan['timeout_s']==TIMEOUT and
            plan['service_timeout_s']==OUTER and plan['worker_timeout_s']==WORKER_BOUND and plan['unit']==UNIT and
            all(plan[k] is True for k in ('no_build','no_retry','no_fsdb','stop_first_fail')),'Scope/budget/ownership drift')
    require(plan['reference_ready_sha256']==READY_SHA and plan['reference_review_sha256']==REVIEW_SHA and
            plan['mf4_acceptance_contract']==MF4_CONTRACT,'Acceptance prerequisite drift')
    require(plan['pins'].get(str(Path(__file__).resolve()))==sha(Path(__file__)),'Worker drift')
    require(type(plan['reserved_slots']) is int and 0<=plan['reserved_slots']<=24,'Bad unused reservation')
    common.base.verify_pins(plan['pins'])
    require(plan['specs']=={s:checker.specification(s) for s in SHAPES},'Actual ELF specification drift')


def terminal_plan_gate(out,digest,image):
    require(sha(out/'plan.json')==digest,'Late disk plan drift')
    validate(read(out/'plan.json'),image)


def prepare(image,out,reserved):
    require(image==IMAGE and not out.exists(),'Fresh owned output, exact M6')
    pins=accepted_reference();ledger,repo,_=common.image_context(image)
    require(Path(ledger['snapshot']).parent.name=='current_board_memory_candidate06','Wrong M6 snapshot')
    host=read(HERE/'host01.json')
    require(host['status']=='PASS_HOST_ONLY' and host['failures']==0 and host['shapes']==SHAPES and
            host['script_sha256']==sha(HERE/'test_host.py') and host['checker_sha256']==sha(HERE/'checker.py') and
            host['runner_sha256']==sha(HERE/'replay.py'),'Current Host tests required')
    pins.update(common.image_pins(image,ledger,repo))
    for module in list(sys.modules.values()):
        path=getattr(module,'__file__',None)
        if path and Path(path).is_file() and Path(path).resolve().is_relative_to(HERE.parents[4]):
            pins[str(Path(path).resolve())]=sha(Path(path))
    for p in [REF/'READY.json',REVIEW,REVIEW.with_name('result.json'),checker.OBJDUMP,
              *[HERE/n for n in ('checker.py','replay.py','test_host.py','README.md','host01.json','host01.log')]]:
        pins[str(p)]=sha(p)
    plan=dict(status='PREPARED_NOT_RUN',image=str(image),image_sha256=sha(image/'image.json'),
        snapshot_sha256=ledger['snapshot_sha256'],cases=scope(),specs={s:checker.specification(s) for s in SHAPES},
        pins=pins,jobs=JOBS,timeout_s=TIMEOUT,service_timeout_s=OUTER,worker_timeout_s=WORKER_BOUND,unit=UNIT,
        reserved_slots=reserved,no_build=True,no_retry=True,no_fsdb=True,stop_first_fail=True,
        reference_ready_sha256=READY_SHA,reference_review_sha256=REVIEW_SHA,mf4_acceptance_contract=MF4_CONTRACT,
        resources_checked_only_at_authorized_run=True,
        budget=dict(waves=3,simulation_envelope_s=3*TIMEOUT,validation_and_worker_headroom_s=WORKER_BOUND-3*TIMEOUT,
            service_teardown_headroom_s=OUTER-WORKER_BOUND,per_case_validation_reserve_s=600,
            reference_firmware=[r['firmware_retired'] for r in read(REF/'READY.json')['results']],
            completion_not_guaranteed=True,no_automatic_timeout_change=True),
        scope='nine authentic reduced singles; not full6720/Linux/DUT acceptance',
        launch_requires='pinned independent mf4 DUT acceptance plus NEW pinned parent authorization')
    validate(plan,image);out.mkdir(exist_ok=False);common.save(out/'plan.json',plan);digest=sha(out/'plan.json')
    worker=[sys.executable,'-B',str(HERE/'replay.py'),'run','--image',str(image),'--out',str(out),
        '--plan-sha256',digest,'--authorize-run','--parent-review','PARENT_REVIEW_JSON',
        '--parent-review-sha256','PARENT_REVIEW_SHA','--mf4-acceptance','MF4_DUT_ACCEPTANCE_JSON',
        '--mf4-acceptance-sha256','MF4_DUT_ACCEPTANCE_SHA']
    cmd=['systemd-run','--user','--unit='+UNIT,'--property=RuntimeMaxSec='+str(OUTER),
        '--property=KillMode=control-group','--property=Restart=no','--property=WorkingDirectory='+str(HERE),
        '--property=StandardOutput=append:'+str(out/'service.log'),'--property=StandardError=append:'+str(out/'service.log'),*worker]
    common.save(out/'ready.json',dict(status='PREPARED_NOT_LAUNCHED_MF4_DUT_AND_PARENT_GATES_PENDING',
        plan_sha256=digest,command=worker,service_command=shlex.join(cmd),pins=len(pins),VCS_started=False))
    print('PREPARED_NOT_LAUNCHED',digest,flush=True)


def owner_gate(p,cgroup,pid):
    fields={'Id','LoadState','ActiveState','SubState','MainPID','ControlGroup','RuntimeMaxUSec','KillMode','Restart'}
    require(set(p)==fields and p['Id']==UNIT and p['LoadState']=='loaded' and p['ActiveState']=='active' and
        p['SubState']=='running' and p['MainPID']==str(pid) and p['ControlGroup'].endswith('/'+UNIT) and
        p['ControlGroup'] in [l.split(':',2)[-1] for l in cgroup.splitlines()] and
        p['RuntimeMaxUSec']=='5h 30min' and p['KillMode']=='control-group' and p['Restart']=='no','Direct service/bound mismatch')


def service_identity():
    runtime=Path('/run/user')/str(os.getuid())
    require(runtime.is_dir() and runtime.stat().st_uid==os.getuid() and (runtime/'bus').is_socket(),'Trusted user bus unavailable')
    env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(runtime/'bus'))
    fields='Id,LoadState,ActiveState,SubState,MainPID,ControlGroup,RuntimeMaxUSec,KillMode,Restart'
    q=subprocess.run(['systemctl','--user','show',UNIT,'--property='+fields],env=env,text=True,capture_output=True,timeout=10)
    require(q.returncode==0 and not q.stderr.strip(),'Service query failed')
    props=dict(l.split('=',1) for l in q.stdout.splitlines());group=Path('/proc/self/cgroup').read_text()
    owner_gate(props,group,os.getpid());return dict(properties=props,cgroup=group,pid=os.getpid())


def mf4_gate(path,digest,image_sha):
    require(path and digest and sha(path)==digest,'Pinned mf4 DUT acceptance required; reference is insufficient')
    proof=read(path)
    require(proof['status']==MF4_STATUS and proof['plan_sha256']==MF4_PLAN_SHA and
            proof['soc_elf_sha256']==MF4_ELF_SHA and proof['image_sha256']==image_sha,'Exact mf4 DUT identity/acceptance')
    cp=Path(proof['complete_path']);require(sha(cp)==proof['complete_sha256'],'mf4 terminal drift')
    complete=read(cp)
    require(complete['status']=='PASS_M6_ORIGINAL_E16_MF4_SINGLE144_NOT_FULL_PARENT' and
            complete['plan_sha256']==MF4_PLAN_SHA and complete['aborted'] is False and
            complete['pins_unchanged'] is True and len(complete['results'])==1,'mf4 real terminal/noabort')
    r=complete['results'][0]
    require(r['name']=='original_e16_mf4' and r['status']=='PASS' and r['returncode']==0 and
            not r['reason'] and 0<=r['elapsed_s']<=5400,'mf4 actual result')
    require(proof['evidence_pins'] and complete['evidence_pins'],'mf4 evidence missing')
    common.base.verify_pins(proof['evidence_pins']);common.base.verify_pins(complete['evidence_pins'])
    return {str(path):digest,str(cp):proof['complete_sha256'],**proof['evidence_pins'],**complete['evidence_pins']}


def authorization_gate(digest,path,review_sha,mf4_sha):
    require(path and review_sha and sha(path)==review_sha,'Pinned new parent review required')
    r=read(path)
    require(r['decision']=='AUTHORIZE_ORIGINAL_REMAINING9_M6_ONCE' and r['plan_sha256']==digest and
            r['unit']==UNIT and r['reference_review_sha256']==REVIEW_SHA and
            r['mf4_acceptance_sha256']==mf4_sha and r['budget_risk_accepted'] is True,'Parent scope/budget/gate mismatch')
    return {str(path):review_sha}


def checked_runner(parent,abort,check,admission):
    class Runner(parent):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.cancel_event=abort
        def _run_test(self,test,image):
            result=None
            try:
                if not abort.is_set():admission(test.name)
                result=super()._run_test(test,image)
                if result.status=='PASS':
                    check(result)
                    if abort.is_set():result.status,result.reason='CANCELLED','Abort during strict validation'
                if result.status!='PASS':abort.set()
                return result
            except Exception as e:
                abort.set()
                if result is not None:
                    result.status,result.reason='FAIL',f'Strict validation: {type(e).__name__}: {e}'
                    return result
                raise
            except BaseException:abort.set();raise
    return Runner


def terminal_gate(results,metadata,abort,ledger):
    cases=scope();common.check_stage(results,metadata,cases,abort)
    require(metadata['tests']==[c['id'] for c in cases] and metadata['completed_at'] and metadata['jobs']==JOBS and
            metadata['timeout_s']==TIMEOUT and metadata['simv']==ledger['simv'] and
            metadata['commit_trace'] is True and metadata['code_coverage'] is False,'Wrong COMPLETE contract')


def deadline_gate(now,deadline):
    require(now+TIMEOUT+600<=deadline,'Insufficient worker budget for unchanged case plus validation; no dispatch/retry')


def run(image,out,digest,authorized,review_path,review_sha,mf4_path,mf4_sha):
    require(authorized and digest and sha(out/'plan.json')==digest,'Explicit parent authorization/plan SHA required')
    plan=read(out/'plan.json');validate(plan,image)
    approval_pins=authorization_gate(digest,review_path,review_sha,mf4_sha)
    approval_pins.update(mf4_gate(mf4_path,mf4_sha,plan['image_sha256']))
    ledger,repo,(parent,options,testcase,_)=common.image_context(image)
    require(ledger['snapshot_sha256']==plan['snapshot_sha256'],'Snapshot drift')
    owner=service_identity();admitted=common.resources(out,JOBS,plan['reserved_slots'])
    with (out/'launch.json').open('x') as stream:
        json.dump(dict(owner=owner,admission=admitted,started=time.time(),plan_sha256=digest),stream,indent=2)
    abort=threading.Event();deadline=time.monotonic()+WORKER_BOUND
    timer=threading.Timer(WORKER_BOUND,abort.set);timer.daemon=True
    terminal=dict(status='NOT_PASS',plan_sha256=digest,results=[],retries=0,pins_unchanged=False)
    import ara_verify.runner as engine
    from ara_verify.trace import validate_trace
    old_fail=engine.FAIL_RE;engine.FAIL_RE=re.compile(old_fail.pattern+'|'+checker.VETO.pattern,re.I)
    with common.abort_signals(abort):
        timer.start()
        try:
            require(not (out/'replay').exists(),'No retry/overwrite')
            entries={c['id']:c for c in plan['cases']}
            def admission(name):
                require(name in entries,'Unknown dispatch')
                deadline_gate(time.monotonic(),deadline)
            def check(result):
                case=entries[result.name]
                common.save(result.artifact_dir/'strict_original.json',checker.artifacts(result,case,ledger,plan['specs'][case['shape']],validate_trace))
            opts=options(repo,out/'replay','default',1,JOBS,False,False,True,Path(ledger['simv']),True,TIMEOUT)
            tests=[testcase(c['id'],'app','',Path(c['elf']),c['id'],TIMEOUT) for c in plan['cases']]
            results=checked_runner(parent,abort,check,admission)(opts,tests,sys.argv).run()
            terminal['results']=[dict(asdict(r),artifact_dir=str(r.artifact_dir)) for r in results]
            terminal_gate(results,read(out/'replay/run.json'),abort,ledger)
            require(read(out/'replay/summary.json')==terminal['results'],'Summary mismatch')
            terminal_plan_gate(out,digest,image);common.image_context(image);common.base.verify_pins(approval_pins)
            evidence={str(p):sha(p) for p in (out/'launch.json',out/'replay/run.json',out/'replay/summary.json')}
            for case in plan['cases']:
                root=out/'replay/tests'/case['id']
                for n in ('input.elf','inputs.json','command.json','console.log','work/run.vcs.log',
                          'commit_trace.csv','trace_summary.json','strict_original.json'):
                    evidence[str(root/n)]=sha(root/n)
            terminal.update(status=PASS,evidence_pins=evidence,pins_unchanged=True,full_parents_accepted=False)
        except BaseException as e:
            abort.set();terminal.update(status='NOT_PASS',error=f'{type(e).__name__}: {e}')
            if (out/'replay/summary.json').exists():terminal['results']=read(out/'replay/summary.json')
        finally:
            engine.FAIL_RE=old_fail;terminal['finished']=time.time()
            common.publish(out,terminal,abort);timer.cancel()
    print(terminal['status'],flush=True);return int(terminal['status']!=PASS)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['prepare','run'])
    for n in ('image','out'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--reserved-slots',type=int,default=0)
    for n in ('authorize-prepare','authorize-run'):p.add_argument('--'+n,action='store_true')
    for n in ('plan-sha256','parent-review-sha256','mf4-acceptance-sha256'):p.add_argument('--'+n)
    for n in ('parent-review','mf4-acceptance'):p.add_argument('--'+n,type=Path)
    a=p.parse_args();image,out=a.image.resolve(),a.out.resolve()
    require(out.parent==HERE,'Owned fresh direct child only')
    env=common.base.shared.environment();os.environ.clear();os.environ.update(env)
    if a.mode=='prepare':
        require(a.authorize_prepare,'Explicit prepare gate');prepare(image,out,a.reserved_slots);return 0
    return run(image,out,a.plan_sha256,a.authorize_run,a.parent_review,a.parent_review_sha256,a.mf4_acceptance,a.mf4_acceptance_sha256)


if __name__=='__main__':raise SystemExit(main())
