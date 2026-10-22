#!/usr/bin/env python3
"""No-build M8 single worker. Prepare/dryrun now; pinned entry review before run."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import threading
import time
sys.dont_write_bytecode = True
import checker as c
sys.path.insert(0,str(c.G/'gather_repair05'))
# Both sealed source preparation and integration use the module name prepare.
# Their functions retain their own module objects; do not alias their APIs.
source_prepare = sys.modules.pop('prepare', None)
import regression as common
if source_prepare is not None: sys.modules['prepare'] = source_prepare
HERE, REF = c.HERE, c.REF
require, read, sha = c.require, c.read, c.m.sha
NAME = c.NAME
TIMEOUT, WORKER, OUTER = 10800, 12000, 13200
UNIT = 'ara-segment-full144-m8-01.service'
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate08/campaign/image')
SOURCE_REVIEW = HERE.parent/'segment_full144_review_zeno01'
SOURCE_REVIEW_PINS = {
    str(SOURCE_REVIEW/'REVIEW.json'): 'e4231d1b5084b0751d451d1866c9694dcead70b8136487f068e3d48259f0b5bf',
    str(SOURCE_REVIEW/'REVIEW.md'): '5f34c55009e730f3beac7dc058e9ff62c047abae726bd486db34d872c39204c2'}

def save(path,value):
    path=Path(path)
    with path.open('x') as f:
        json.dump(value,f,indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())

def verify(pins):
    common.base.verify_pins(pins)

def source_review():
    verify(SOURCE_REVIEW_PINS)
    r=read(SOURCE_REVIEW/'REVIEW.json')
    require(r['decision']=='NO_BLOCKER_SOURCE_REFERENCE_SCOPE_ONLY' and r['no_blocker_source_reference'] and
            r['reference_raw_review_accepted'] and r['source_READY_sha256']==c.READY_SHA and
            r['evidence_pins_count']==87 and r['full144_actual_contexts_checked']==144 and
            r['worker_entry_reviewed'] is False and r['DUT_authorized_by_this_review'] is False,
            'Actual independent source/reference review scope')
    verify(r['hashes'])
    return {**SOURCE_REVIEW_PINS,**r['hashes']}

def options(cls,repo,out,ledger):
    return cls(repo_root=repo,output_root=out,config='default',jobs=1,seed=1,
        dry_run=True,build_only=False,skip_build=True,simv=Path(ledger['simv']),commit_trace=True,
        timeout_s=TIMEOUT,contract_monitor=False,probe_kinds=(),code_coverage=False)

def shape():
    return dict(cases=144,jobs=1,timeout_s=TIMEOUT,worker_timeout_s=WORKER,service_timeout_s=OUTER,
                unit=UNIT,no_retry=True,no_fsdb=True,no_build=True,source_outcomes=[0,77],
                capability_is_eligible_not_required=True,linux_clone_COW_equivalent=False)

def prepare(image,out):
    require(not out.exists(),'Fresh output only')
    spec=c.specification(); ready=read(REF/'READY.json')
    require(sha(REF/'evidence_pins.json') == ready['evidence_pins_sha256'],'Reference evidence map')
    pins=read(REF/'evidence_pins.json'); verify(pins)
    require(len(pins)==87,'Original87 evidence pins')
    pins[str(REF/'evidence_pins.json')]=sha(REF/'evidence_pins.json')
    pins[str(REF/'READY.json')]=c.READY_SHA
    pins.update(source_review())
    host=read(HERE/'host02.json'); require(host['status']=='PASS_HOST_ONLY_NOT_DUT','Host incomplete')
    verify(host['pins']); pins.update(host['pins'])
    ledger,repo,framework=common.image_context(image)
    require(Path(ledger['snapshot']).parent.name=='current_board_memory_candidate08','Explicit M8 snapshot')
    pins.update(common.image_pins(image,ledger,repo))
    for path in HERE.iterdir():
        if path.is_file(): pins[str(path)]=sha(path)
    for module in list(sys.modules.values()):
        path=getattr(module,'__file__',None)
        if path and Path(path).is_file() and Path(path).resolve().is_relative_to(c.G.parents[2]):
            pins[str(Path(path).resolve())]=sha(path)
    verify(pins); out.mkdir()
    plan=dict(status='PREPARED_NOT_ADMITTED',image=str(image),image_sha256=sha(image/'image.json'),
              snapshot_sha256=ledger['snapshot_sha256'],spec=spec,pins=pins,shape=shape(),
              runtime_id=NAME,historical_name=c.m.NAME,reference_ready_sha256=c.READY_SHA,
              source_review_pins=SOURCE_REVIEW_PINS,
              independent_worker_review_required=True,reference_raw_review_required=True,
              budget_estimate=ready['budget_estimates'],launch_authorized=False)
    save(out/'plan.json',plan); digest=sha(out/'plan.json')
    parent,opt,test,_=framework
    runner=parent(options(opt,repo,out/'dryrun',ledger),[test(NAME,'app','',Path(spec['elf']),NAME,TIMEOUT)],sys.argv)
    results=runner.run()
    require(len(results)==1 and results[0].status=='DRY_RUN','Actual dryrun')
    command=['python3','-B',str(HERE/'replay.py'),'run','--image',str(image),'--out',str(out),
             '--plan-sha256',digest,'--review','INDEPENDENT_REVIEW_JSON','--review-sha256','REVIEW_SHA',
             '--authorization','PARENT_AUTHORIZATION_JSON','--authorization-sha256','AUTHORIZATION_SHA']
    service=['systemd-run','--user','--unit='+UNIT,'--property=RuntimeMaxSec='+str(OUTER),
             '--property=KillMode=control-group','--property=Restart=no',
             '--property=WorkingDirectory='+str(HERE),
             '--property=StandardOutput=append:'+str(out/'service.log'),
             '--property=StandardError=append:'+str(out/'service.log'),*command]
    verify(pins)
    save(out/'ready.json',dict(status='PREPARED_DRYRUN_ONLY_PENDING_INDEPENDENT_ENTRY_REVIEW',
        plan_sha256=digest,command=command,service_command=shlex.join(service),pins=len(pins),DUT_started=False,
        dryrun_sha256=sha(out/'dryrun/run.json')))
    print(json.dumps(dict(status='PREPARED_NOT_ADMITTED',plan_sha256=digest,pins=len(pins))))

def validate(plan,image):
    require(plan['status']=='PREPARED_NOT_ADMITTED' and plan['shape']==shape(),'Plan scope/budget drift')
    require(plan['image']==str(image) and sha(image/'image.json')==plan['image_sha256'],'Image drift')
    require(plan['spec']==c.specification() and plan['runtime_id']==NAME and plan['historical_name']==c.m.NAME,'Actual ELF/runtime identity drift')
    require(plan['reference_ready_sha256']==c.READY_SHA and plan['independent_worker_review_required'] and
            plan['reference_raw_review_required'] and not plan['launch_authorized'],'Entry requirements')
    require(plan['source_review_pins']==SOURCE_REVIEW_PINS,'Source review binding')
    source_review()
    require(plan['pins'].get(str(HERE/'replay.py'))==sha(HERE/'replay.py'),'Worker drift')
    verify(plan['pins'])

def entry(plan_sha,review,rsha,authorization,asha):
    require(review and authorization and sha(review)==rsha and sha(authorization)==asha,'Pinned independent review and explicit authorization')
    r=read(review); a=read(authorization)
    require(r['decision']=='ACCEPT_SEGMENT144_M8_WORKER_ENTRY' and r['plan_sha256']==plan_sha and
            r['blocking_findings']==[] and r['reference_ready_sha256']==c.READY_SHA and
            r['reference_raw_review_accepted'] is True and r['worker_review_accepted'] is True,
            'Independent raw+worker review not accepted')
    verify(r['evidence_pins'])
    require(a['decision']=='AUTHORIZE_SEGMENT144_M8_ONCE' and a['plan_sha256']==plan_sha and
            a['entry_review_sha256']==rsha and a['unit']==UNIT and a['budget_risk_accepted'] is True,
            'Explicit single-run authorization')
    return {str(review):rsha,str(authorization):asha,**r['evidence_pins']}

def owner():
    runtime=Path('/run/user')/str(os.getuid())
    require(runtime.stat().st_uid==os.getuid() and (runtime/'bus').is_socket(),'Trusted user bus')
    env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(runtime/'bus'))
    names=('Id','LoadState','ActiveState','SubState','MainPID','ControlGroup','RuntimeMaxUSec','KillMode','Restart')
    p=subprocess.run(['systemctl','--user','show',UNIT,'--property='+','.join(names)],env=env,text=True,capture_output=True,timeout=10)
    require(p.returncode==0 and not p.stderr.strip(),'Actual service query error')
    fields=dict(line.split('=',1) for line in p.stdout.splitlines())
    cg=Path('/proc/self/cgroup').read_text()
    require(set(fields)==set(names) and fields['Id']==UNIT and fields['LoadState']=='loaded' and
            fields['ActiveState']=='active' and fields['SubState']=='running' and fields['MainPID']==str(os.getpid()) and
            fields['ControlGroup'].endswith('/'+UNIT) and any(line.split(':',2)[-1]==fields['ControlGroup'] for line in cg.splitlines()) and
            fields['RuntimeMaxUSec']=='3h 40min' and fields['KillMode']=='control-group' and fields['Restart']=='no',
            'Actual direct service owner/deadline')
    return dict(pid=os.getpid(),properties=fields,cgroup=cg)

def command_for(ledger,root):
    return [ledger['simv'],'-l','run.vcs.log','+ntb_random_seed=1','+PRELOAD='+str(root/'input.elf'),
            '+TESTCASE='+NAME,'+NO_FSDB','+COMMIT_TRACE='+str(root/'commit_trace.csv')]

def metadata(root,plan,ledger):
    spec=plan['spec']; require(sha(root/'input.elf')==spec['elf_sha256'],'Private ELF drift')
    require(read(root/'command.json')==dict(command=command_for(ledger,root),cwd=str(root/'work')),'Actual command/cwd/seed/preload')
    require(read(root/'inputs.json')==dict(binary=dict(source=spec['elf'],path=str(root/'input.elf'),sha256=spec['elf_sha256']),
                simv=dict(path=ledger['simv'],image_sha256=ledger['files'])),'Private provenance')

def outcome_gate(outcome,source_exit):
    require(type(outcome['returncode']) is int and not outcome['timed_out'] and not outcome['failure_seen'] and not outcome['aborted'], 'Actual monitor failed/interrupted')
    # $finish argument is not specified to be a Unix status. Record the actual
    # numeric value; only the bounded declared protocol pair can be accepted.
    require(outcome['returncode'] in ((0,77) if source_exit==77 else (0,)), 'Unexpected simulator process exit')
    require(0 <= outcome['elapsed_s'] <= TIMEOUT,'Simulation time budget')

def audit_job(root,spec,out):
    ledger,repo,_=common.image_context(Path(read(out/'plan.json')['image']))
    from ara_verify.trace import validate_trace
    strict=c.analyze(root/'commit_trace.csv',spec)
    generic=validate_trace(root/'commit_trace.csv')
    require((strict['rows'],strict['retired'],strict['last_cycle']) ==
            (generic['rows'],generic['retire_count'],generic['last_cycle']),'Strict/generic trace identity')
    require(generic['cvx_exception_count']==strict['capability'] and generic['backend_uop_alloc_count']==generic['backend_uop_done_count']>0,'Whole CVX/uop protocol')
    outcome=read(root/'child_outcome.unvalidated.json'); outcome_gate(outcome,strict['source_exit'])
    for path in (root/'console.log',root/'work/run.vcs.log'): c.protocol(path.read_text(),strict['source_exit'])
    save(root/'strict_result.json',dict(strict=strict,generic=generic,actual_simulator_rc=outcome['returncode'],
         source_exit=strict['source_exit'],csv_sha256=sha(root/'commit_trace.csv')))

def run(args):
    out=args.out; image=args.image; digest=args.plan_sha256
    require(digest and sha(out/'plan.json')==digest,'Pinned plan required')
    plan=read(out/'plan.json'); validate(plan,image)
    reviews=entry(digest,args.review,args.review_sha256,args.authorization,args.authorization_sha256)
    require(not (out/'launch.json').exists() and not (out/'replay').exists(),'One attempt/no overwrite')
    ledger,repo,_=common.image_context(image)
    owned=owner(); resources=common.resources(out,1,0)
    save(out/'launch.json',dict(plan_sha256=digest,owner=owned,resources=resources,review_pins=reviews,time=time.time()))
    root=out/'replay'/NAME; (root/'work').mkdir(parents=True)
    shutil.copyfile(plan['spec']['elf'],root/'input.elf')
    command=command_for(ledger,root)
    save(root/'command.json',dict(command=command,cwd=str(root/'work')))
    save(root/'inputs.json',dict(binary=dict(source=plan['spec']['elf'],path=str(root/'input.elf'),sha256=plan['spec']['elf_sha256']),
         simv=dict(path=ledger['simv'],image_sha256=ledger['files'])))
    metadata(root,plan,ledger)
    abort=threading.Event(); deadline=time.monotonic()+WORKER
    timer=threading.Timer(WORKER,abort.set); timer.daemon=True
    terminal=dict(status='NOT_PASS',plan_sha256=digest,source_exit=None,actual_simulator_rc=None,attempts=1)
    import ara_verify.runner as engine
    original_fail=engine.FAIL_RE; engine.FAIL_RE=c.FailureMatcher()
    with common.abort_signals(abort):
        timer.start()
        try:
            rc,elapsed,timed,failed=engine._run_monitored(command,root/'work',root/'console.log',TIMEOUT,abort)
            raw=dict(status='UNVALIDATED_CHILD_OUTCOME',architectural_acceptance=False,returncode=rc,
                     elapsed_s=elapsed,timed_out=timed,failure_seen=failed,aborted=abort.is_set(),
                     command_sha256=sha(root/'command.json'),runtime_id=NAME,historical_name=c.m.NAME)
            save(root/'child_outcome.unvalidated.json',raw)
            terminal['actual_simulator_rc']=rc
            require(type(rc) is int and not timed and not failed and not abort.is_set(),'Actual simulator incomplete/failure; no retry')
            # Separate bounded process: a validation failure cannot destroy child rc.
            remaining=deadline-time.monotonic()
            require(remaining>0,'No observer budget left')
            audit_command=[sys.executable,'-B',str(HERE/'replay.py'),'audit','--image',str(image),'--out',str(out)]
            start=time.monotonic(); timeout=False
            with (root/'audit.log').open('x') as log:
                process=subprocess.Popen(audit_command,stdout=log,stderr=subprocess.STDOUT)
                try: audit_rc=process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    timeout=True; process.kill(); audit_rc=process.wait()
            save(root/'audit_wait.json',dict(returncode=audit_rc,timeout=timeout,elapsed_s=time.monotonic()-start,command=audit_command))
            require(audit_rc==0 and not timeout and not abort.is_set(),'Strict offline audit failed/aborted')
            metadata(root,plan,ledger); verify(plan['pins']); verify(reviews)
            require(sha(out/'plan.json')==digest,'Late plan disk drift')
            result=read(root/'strict_result.json')
            terminal.update(status=result['strict']['status'],source_exit=result['source_exit'],pins_unchanged=True,
                numerical=result['strict']['numerical'],capability=result['strict']['capability'],
                evidence_pins={str(p):sha(p) for p in root.rglob('*') if p.is_file()})
        except BaseException as error:
            abort.set(); terminal.update(status='NOT_PASS',error=f'{type(error).__name__}: {error}')
        finally:
            engine.FAIL_RE=original_fail; timer.cancel(); timer.join()
            if time.monotonic()>=deadline: abort.set()
            terminal['aborted']=abort.is_set(); terminal['finished']=time.time()
            if abort.is_set(): terminal['status']='NOT_PASS'
            common.publish(out,terminal,abort)
    return int(terminal['status']=='NOT_PASS')

def main():
    p=argparse.ArgumentParser(); p.add_argument('mode',choices=('prepare','run','audit'))
    p.add_argument('--image',type=Path,default=IMAGE); p.add_argument('--out',type=Path,required=True)
    for name in ('plan-sha256','review-sha256','authorization-sha256'): p.add_argument('--'+name)
    p.add_argument('--review',type=Path); p.add_argument('--authorization',type=Path)
    args=p.parse_args(); args.out=args.out.resolve(); args.image=args.image.resolve()
    if args.mode=='prepare': prepare(args.image,args.out); return 0
    if args.mode=='audit':
        require((args.out/'replay'/NAME/'child_outcome.unvalidated.json').is_file(),'Audit requires completed child evidence')
        audit_job(args.out/'replay'/NAME,read(args.out/'plan.json')['spec'],args.out); return 0
    return run(args)

if __name__=='__main__': raise SystemExit(main())
