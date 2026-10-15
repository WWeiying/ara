#!/usr/bin/env python3
"""Two future frozen-M6 source singles; prepare/dryrun never launch or build."""
import argparse
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
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
from checker import common, require, read, sha
from newscope import *

REVIEW = HERE.parent/'nan_minmax_soc_entry_review01/TERMINAL_ENTRY_REVIEW01.md'
REVIEW_SHA = 'e5f42231f0ad2c124231a046ab9b0214913452baa741e2f54cc8abe9ace750de'
HOST_REPORT = 'host04.json'


def durable(path, data):
    path = Path(path)
    with path.open('x') as stream:
        json.dump(data,stream,indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def first_cause(root, cause):
    root=Path(root)
    try:
        durable(root/'first_cause.json',cause)
    except FileExistsError:
        pass
    if root.name in NAMES and root.parent.name=='tests' and root.parent.parent.name=='replay':
        try:
            durable(root.parents[2]/'first_cause.json',dict(cause,runtime_id=root.name))
        except FileExistsError:
            pass


def merge_pins(*tables):
    result={}
    for table in tables:
        for path,digest in table.items():
            require(path not in result or result[path]==digest,'Conflicting input pin: '+path)
            result[path]=digest
    return result


def accepted_reference():
    require(sha(READY)==READY_SHA and sha(REVIEW)==REVIEW_SHA,'Actual READY/independent review pin required')
    require('ACCEPTED FOR THE TWO SEALED SOURCE-SINGLE VCS INPUTS, NOT DUT PASS.' in REVIEW.read_text(),
            'Actual independent review decision')
    ready=read(READY)
    require(ready['status']=='TWO_SOURCE_SINGLE_ARCHITECTURAL_REFERENCES_READY_PENDING_INDEPENDENT_TERMINAL_REVIEW'
            and ready['pins_pre_post_unchanged'] is True and ready['DUT_run'] is False,
            'Actual source-single reference scope')
    pre=read(READY.parent/'pins_pre.json')
    require(pre==read(READY.parent/'pins_post.json'),'Source pre/post pins differ')
    common.base.verify_pins(pre)
    common.base.verify_pins(ready['result_pins'])
    pins=merge_pins(pre,ready['result_pins'],{str(READY):READY_SHA,str(REVIEW):REVIEW_SHA})
    require([r['shape'] for r in ready['results']]==[shape(n) for n in NAMES],'Exact two reference cases')
    for result,name in zip(ready['results'],NAMES):
        dest=REF/shape(name)
        proof=read(dest/'sourceproof.json')
        require(result['status']=='ARCHITECTURAL_REFERENCE_ACCEPTED_BY_EXECUTOR_NOT_DUT' and
                result['original_scope']==proof['config'] and result['firmware_retired']==REFERENCE_RETIRED and
                result['helper_instructions']==21 and result['full_output_oracle_bytes']==144 and
                result['flags']==result['vstart']==0 and result['DUT_run'] is False,
                'Reference exact helper/oracle/count scope')
        pins=merge_pins(pins,proof['external_pins'],proof['prepared_pins'],
                        {str(dest/'sourceproof.json'):sha(dest/'sourceproof.json')},
                        read(dest/'reference01/admission.json')['pins'])
        execution=read(dest/'reference01/execution.json')
        receipt=read(dest/'reference01/actual_exit_unvalidated.json')
        require(type(receipt['returncode']) is int and receipt['returncode']==0 and receipt['validated'] is False
                and execution['returncode']==0 and execution.get('timed_out',False) is False
                and execution.get('error') is None and 0<execution['elapsed_s']<120,
                'Actual reference numeric exit/bound')
        raw=dest/'reference01/commits.log'
        require(execution['raw']['commits.log']['sha256']==result['raw_sha256']
                and raw.stat().st_size==execution['raw']['commits.log']['bytes']<=256*1024**2,
                'Reference raw identity/resource bound')
        pins[str(raw)]=result['raw_sha256']
        for filename in ('actual_exit_unvalidated.json','execution.json','ATTEMPT_STARTED.json','admission.json',
                         'admission.pin.json','spike.cmd'):
            path=dest/'reference01'/filename
            pins[str(path)]=sha(path)
        require(sha(dest/'soc/program.elf')==ELF_SHA[name],'Reviewed exact SoC ELF')
    require(pins[str(REF/'call1234/reference01/actual_exit_unvalidated.json')]==
            '800a2fec448b774eff4a268b6dfa9b8676acb48411fc9f485837e9b7988f809d' and
            pins[str(REF/'call1234/reference01/execution.json')]==
            '1ea6789ac7b537a225a6cd2f1326ec07a453a78ed8795908d777d160d9c1ae16' and
            pins[str(REF/'call1234/reference01/ATTEMPT_STARTED.json')]==
            '887dacdec419261bfa263ea3cde1a4b6ed6a51def86eb2544b5e62d590d99f8d',
            'Independent additionally reviewed second-case receipts')
    common.base.verify_pins(pins)
    return pins


def cases():
    return [dict(id=name,original_name=name,source_label='rvv_fp_redspecial_e32_m1',
                 original_call=int(shape(name)[4:]),elf=str(REF/shape(name)/'soc/program.elf'),
                 sha256=ELF_SHA[name],timeout_s=TIMEOUT,
                 pass_markers=[MARKER,'BOARD_CASE_PASS '+name,'BOARD_REPLAY_PASS']) for name in NAMES]


def validate(plan,image):
    require(image==IMAGE and plan['status']=='PREPARED_NOT_RUN' and plan['image']==str(image)
            and plan['image_sha256']==sha(image/'image.json'),'Exact frozen M6 plan/image')
    require(plan['cases']==cases() and plan['jobs']==JOBS and plan['timeout_s']==TIMEOUT
            and plan['service_timeout_s']==OUTER and plan['unit']==UNIT and
            all(plan[k] is True for k in ('no_build','no_retry','no_fsdb','no_code_coverage','no_ucli',
                                         'stop_first_fail','numeric_monitor_before_postcheck')),
            'Exact two-case resource/budget/run contract')
    require(plan['reference_ready_sha256']==READY_SHA and plan['independent_review_sha256']==REVIEW_SHA,
            'Source acceptance provenance')
    require(plan['specs']=={name:checker.specification(name) for name in NAMES},'Actual SoC specifications')
    require(type(plan['reserved_slots']) is int and 0<=plan['reserved_slots']<=24,'Unused reservation bounds')
    require(plan['pins'].get(str(HERE/'replay.py'))==sha(HERE/'replay.py'),'Worker pin')
    expected=accepted_reference()
    require(all(plan['pins'].get(path)==digest for path,digest in expected.items()),
            'Incomplete source/READY/independent-review pins')
    host=read(HERE/HOST_REPORT)
    require(host['status']=='PASS_HOST_ONLY_NOT_DUT' and host['failures']==host['errors']==0 and
            all(plan['pins'].get(path)==digest for path,digest in host['pins'].items()) and
            plan['pins'].get(str(HERE/HOST_REPORT))==sha(HERE/HOST_REPORT),'Host/code pin membership')
    common.base.verify_pins(plan['pins'])


def terminal_plan_gate(out,digest,image):
    require(sha(out/'plan.json')==digest,'Late disk plan drift')
    validate(read(out/'plan.json'),image)
    require(sha(out/'plan.json')==digest,'Plan changed during late gate')


def prepare(image,out,reserved):
    require(image==IMAGE and out.parent==HERE and not out.exists(),'Fresh direct plan / actual M6 only')
    pins=accepted_reference()
    host=read(HERE/HOST_REPORT)
    require(host['status']=='PASS_HOST_ONLY_NOT_DUT' and host['failures']==host['errors']==0,'Current Host required')
    common.base.verify_pins(host['pins'])
    pins.update(host['pins'])
    ledger,repo,_=common.image_context(image)
    require(Path(ledger['snapshot']).parent.name=='current_board_memory_candidate06','Frozen M6 snapshot')
    pins.update(common.image_pins(image,ledger,repo))
    for module in list(sys.modules.values()):
        path=getattr(module,'__file__',None)
        if path and Path(path).is_file() and Path(path).resolve().is_relative_to(HERE.parents[3]):
            pins[str(Path(path).resolve())]=sha(Path(path))
    for filename in ('newscope.py','checker.py','replay.py','test_host.py','README.md',HOST_REPORT):
        pins[str(HERE/filename)]=sha(HERE/filename)
    pins[str(checker.OBJDUMP)]=sha(checker.OBJDUMP)
    plan=dict(status='PREPARED_NOT_RUN',image=str(image),image_sha256=sha(image/'image.json'),
              snapshot_sha256=ledger['snapshot_sha256'],cases=cases(),
              specs={n:checker.specification(n) for n in NAMES},pins=pins,jobs=JOBS,
              timeout_s=TIMEOUT,service_timeout_s=OUTER,unit=UNIT,reserved_slots=reserved,
              no_build=True,no_retry=True,no_fsdb=True,no_code_coverage=True,no_ucli=True,
              stop_first_fail=True,numeric_monitor_before_postcheck=True,
              reference_ready_sha256=READY_SHA,independent_review_sha256=REVIEW_SHA,
              parent_run_approval='UNRESOLVED',resources_checked_at_authorized_run_only=True,
              budget=dict(reference_firmware_each=REFERENCE_RETIRED,proxy_retired_per_second=600,
                          estimated_each_s=REFERENCE_RETIRED/600,completion_guaranteed=False,
                          fixed_case_s=TIMEOUT,fixed_worker_s=OUTER,no_automatic_budget_increase=True),
              scope='two original selected max singles; no min/full Linux/parent acceptance')
    validate(plan,image)
    out.mkdir()
    durable(out/'plan.json',plan)
    digest=sha(out/'plan.json')
    worker=[sys.executable,'-B',str(HERE/'replay.py'),'run','--out',str(out),
            '--plan-sha256',digest,'--authorize-run','--parent-review','UNRESOLVED_PARENT_REVIEW_JSON',
            '--parent-review-sha256','UNRESOLVED_PARENT_REVIEW_SHA256']
    service=['systemd-run','--user','--unit='+UNIT,'--property=RuntimeMaxSec=7200',
             '--property=KillMode=control-group','--property=Restart=no',
             '--property=WorkingDirectory='+str(HERE),
             '--property=StandardOutput=append:'+str(out/'service.log'),
             '--property=StandardError=append:'+str(out/'service.log'),*worker]
    durable(out/'ready.json',dict(status='PREPARED_NOT_LAUNCHED',plan_sha256=digest,
             service_command=shlex.join(service),command=worker,parent_approval='UNRESOLVED',DUT_started=False))
    print('PREPARED_NOT_LAUNCHED',digest,flush=True)


def build_options(options,repo,out,ledger,dry=False):
    return options(repo_root=repo,output_root=out/('dryrun' if dry else 'replay'),config='default',
                   jobs=JOBS,seed=1,dry_run=dry,build_only=False,skip_build=True,
                   simv=Path(ledger['simv']),commit_trace=True,timeout_s=TIMEOUT)


def dryrun(image,out,digest):
    terminal_plan_gate(out,digest,image)
    require(not (out/'dryrun').exists(),'Once-only fresh dryrun')
    ledger,repo,(parent,options,testcase,_)=common.image_context(image)
    class NoBuild(parent):
        def build(self):
            return Path(ledger['simv'])
    opts=build_options(options,repo,out,ledger,True)
    tests=[testcase(c['id'],'app','',Path(c['elf']),c['original_name'],TIMEOUT) for c in cases()]
    results=NoBuild(opts,tests,sys.argv).run()
    require(len(results)==2 and [r.name for r in results]==NAMES and
            all(r.status=='DRY_RUN' and r.returncode is None for r in results),'Exact dryrun membership')
    pins={}
    for c in cases():
        root=out/'dryrun/tests'/c['id']
        actual=read(root/'command.json')
        expected=monitor_command(root,ledger['simv'],c['id'],Path(c['elf']))
        require(actual==dict(command=expected,cwd=str(root/'work')),'Exact dryrun command/private cwd')
        require(not any((root/p).exists() for p in ('console.log','commit_trace.csv','work/run.vcs.log')),
                'Dryrun unexpectedly produced DUT data')
        pins[str(root/'command.json')]=sha(root/'command.json')
    terminal_plan_gate(out,digest,image)
    durable(out/'dryrun_gate.json',dict(status='DRYRUN_ONLY_NO_DUT',jobs=JOBS,cases=NAMES,
             plan_sha256=digest,evidence_pins=pins,build_invoked=False,DUT_started=False))
    print('DRYRUN_ONLY_NO_DUT',digest,flush=True)


def monitor_command(root,simv,name,preload=None):
    return [str(simv),'-l','run.vcs.log','+ntb_random_seed=1',
            '+PRELOAD='+str(preload or root/'input.elf'),'+TESTCASE='+name,'+NO_FSDB',
            '+COMMIT_TRACE='+str(root/'commit_trace.csv')]


def monitored(original,abort,roots,simv):
    routing={str(root.resolve()/'work'):(name,root.resolve()) for name,root in roots.items()}
    def call(command,cwd,console,timeout,cancel_event=None):
        root=None
        try:
            require(str(Path(cwd).resolve()) in routing,'Unowned/private monitor CWD')
            name,root=routing[str(Path(cwd).resolve())]
            require(Path(console).resolve()==root/'console.log' and timeout==TIMEOUT and
                    list(map(str,command))==monitor_command(root,simv,name),'Monitor command/runtime/bound')
            outcome=original(command,cwd,console,timeout,cancel_event)
            code,elapsed,timed_out,failure_seen=outcome
            durable(root/'child_outcome.unvalidated.json',dict(schema='ACTUAL_MONITOR_WAIT_V1',
                    architectural_acceptance=False,name=name,source_label='rvv_fp_redspecial_e32_m1',
                    returncode=code,elapsed_s=elapsed,timed_out=timed_out,failure_seen=failure_seen,
                    command=list(map(str,command)),cwd=str(cwd),timeout_s=timeout))
            require(type(code) is int and type(timed_out) is bool and type(failure_seen) is bool,
                    'Actual numeric monitor tuple')
            if code!=0 or timed_out or failure_seen:
                abort.set()
                first_cause(root,dict(kind='MONITOR_OUTCOME',name=name,returncode=code,
                                     timed_out=timed_out,failure_seen=failure_seen))
            raw=(root/'command.json').read_bytes()
            metadata=json.loads(raw)
            durable(root/'child_command.provenance.json',dict(command=metadata,
                    command_sha256=hashlib.sha256(raw).hexdigest(),actual_monitor_command=list(map(str,command))))
            require(metadata==dict(command=list(map(str,command)),cwd=str(cwd)),'Actual command provenance')
            return outcome
        except BaseException as error:
            abort.set()
            if root is not None:
                receipt=root/'child_outcome.unvalidated.json'
                first_cause(root,dict(kind='MONITOR_OR_POST_EXCEPTION',
                    returncode=read(receipt)['returncode'] if receipt.exists() else None,error=repr(error)))
            raise
    return call


@contextmanager
def engine_hooks(engine,abort,roots,simv):
    old_monitor,old_fail=engine._run_monitored,engine.FAIL_RE
    # One immutable routing wrapper is installed before both worker threads.
    engine._run_monitored=monitored(old_monitor,abort,roots,simv)
    engine.FAIL_RE=re.compile(old_fail.pattern+'|'+checker.VETO.pattern,re.I)
    try:
        yield
    finally:
        engine._run_monitored,engine.FAIL_RE=old_monitor,old_fail


def checked_runner(parent,abort,check,admission):
    class Runner(parent):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            self.cancel_event=abort
        def _run_test(self,test,image):
            root=self.output_root/'tests'/test.name
            result=None
            try:
                require(test.name in NAMES and not abort.is_set(),'Unknown/aborted dispatch')
                admission(test.name)
                result=super()._run_test(test,image)
                durable(root/'runner_result.unvalidated.json',dict(name=result.name,status=result.status,
                        returncode=result.returncode,elapsed_s=result.elapsed_s,reason=result.reason,
                        architectural_acceptance=False))
                if result.status!='PASS' or result.returncode!=0:
                    abort.set()
                    first_cause(root,dict(kind='RUNNER_CLASSIFICATION',name=result.name,
                                         status=result.status,returncode=result.returncode,reason=result.reason))
                else:
                    require(not abort.is_set(),'Late abort before strict checking')
                    check(result)
                    if abort.is_set():
                        result.status,result.reason='CANCELLED','Late abort during strict validation'
                return result
            except BaseException as error:
                abort.set()
                if root.is_dir():
                    receipt=root/'child_outcome.unvalidated.json'
                    first_cause(root,dict(kind='POSTCHECK_EXCEPTION',
                        returncode=read(receipt)['returncode'] if receipt.exists() else None,error=repr(error)))
                raise
    return Runner


def terminal_gate(results,metadata,abort,ledger):
    common.check_stage(results,metadata,cases(),abort)
    require(metadata['tests']==NAMES and metadata['completed_at'] and metadata['jobs']==JOBS and
            metadata['timeout_s']==TIMEOUT and metadata['seed']==1 and metadata['simv']==ledger['simv'] and
            metadata['commit_trace'] is True and metadata['code_coverage'] is False,'Frozen COMPLETE contract')
    require(all(type(r.returncode) is int and r.returncode==0 and not r.reason and
                0<=r.elapsed_s<=TIMEOUT for r in results),'Complete exact two-case outcomes')


def owner_gate(props,cgroup,pid):
    fields={'Id','LoadState','ActiveState','SubState','MainPID','ControlGroup','RuntimeMaxUSec','KillMode','Restart'}
    require(set(props)==fields and props['Id']==UNIT and props['LoadState']=='loaded' and
            props['ActiveState']=='active' and props['SubState']=='running' and props['MainPID']==str(pid) and
            props['ControlGroup'].endswith('/'+UNIT) and props['ControlGroup'] in
            [line.split(':',2)[-1] for line in cgroup.splitlines()] and props['RuntimeMaxUSec']=='2h' and
            props['KillMode']=='control-group' and props['Restart']=='no','Direct service owner/fixed7200s')


def service_identity():
    runtime=Path('/run/user')/str(os.getuid())
    require(runtime.is_dir() and runtime.stat().st_uid==os.getuid() and (runtime/'bus').is_socket(),
            'Trusted user bus required')
    env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(runtime/'bus'))
    query=subprocess.run(['systemctl','--user','show',UNIT,'--property=Id,LoadState,ActiveState,SubState,'
                          'MainPID,ControlGroup,RuntimeMaxUSec,KillMode,Restart'],
                         env=env,text=True,capture_output=True,timeout=10)
    require(query.returncode==0 and not query.stderr.strip(),'Service query failed')
    props=dict(line.split('=',1) for line in query.stdout.splitlines())
    group=Path('/proc/self/cgroup').read_text()
    owner_gate(props,group,os.getpid())
    return dict(properties=props,cgroup=group,pid=os.getpid())


def authorization_gate(digest,path,path_sha):
    require(path and path_sha and sha(path)==path_sha,'Actual parent run approval required')
    review=read(path)
    require(review['decision']=='AUTHORIZE_TWO_NAN_MAX_M6_SINGLES_ONCE' and review['plan_sha256']==digest and
            review['unit']==UNIT and review['cases']==NAMES and review['reference_ready_sha256']==READY_SHA and
            review['independent_review_sha256']==REVIEW_SHA and review['budget_risk_accepted'] is True,
            'Parent approval exact scope')
    return {str(path):path_sha}


def run(image,out,digest,authorized,review,review_sha):
    require(authorized and digest,'Explicit run authorization required')
    terminal_plan_gate(out,digest,image)
    approval=authorization_gate(digest,review,review_sha)
    plan=read(out/'plan.json')
    ledger,repo,(parent,options,testcase,_)=common.image_context(image)
    require(ledger['snapshot_sha256']==plan['snapshot_sha256'],'Snapshot drift')
    owner=service_identity()
    resource=common.resources(out,JOBS,plan['reserved_slots'])
    durable(out/'launch.json',dict(owner=owner,admission=resource,started=time.time(),plan_sha256=digest))
    abort=threading.Event()
    terminal=dict(status='NOT_PASS',plan_sha256=digest,results=[],retries=0,pins_unchanged=False)
    import ara_verify.runner as engine
    from ara_verify.trace import validate_trace
    roots={n:out/'replay/tests'/n for n in NAMES}
    by_name={c['id']:c for c in plan['cases']}
    with common.abort_signals(abort),engine_hooks(engine,abort,roots,ledger['simv']):
        try:
            require(not (out/'replay').exists(),'No retry/overwrite')
            def admit(name):
                require(name in NAMES and not abort.is_set(),'Aborted/unknown dispatch')
                terminal_plan_gate(out,digest,image)
                common.base.verify_pins(approval)
                common.resources(out,JOBS,plan['reserved_slots'])
            def check(result):
                report=checker.artifacts(result,by_name[result.name],ledger,
                                         plan['specs'][result.name],validate_trace)
                durable(result.artifact_dir/'strict_original.json',report)
            tests=[testcase(n,'app','',Path(by_name[n]['elf']),n,TIMEOUT) for n in NAMES]
            opts=build_options(options,repo,out,ledger)
            results=checked_runner(parent,abort,check,admit)(opts,tests,sys.argv).run()
            terminal['results']=[dict(asdict(r),artifact_dir=str(r.artifact_dir)) for r in results]
            terminal_gate(results,read(out/'replay/run.json'),abort,ledger)
            require(read(out/'replay/summary.json')==terminal['results'],'Summary disagreement')
            terminal_plan_gate(out,digest,image)
            common.image_context(image)
            common.base.verify_pins(approval)
            files=[out/'launch.json',out/'replay/run.json',out/'replay/summary.json']
            for name,root in roots.items():
                child=read(root/'child_outcome.unvalidated.json')
                require(child['name']==name and type(child['returncode']) is int and child['returncode']==0 and
                        child['timed_out'] is False and child['failure_seen'] is False,'Actual numeric child success')
                files += [root/f for f in ('input.elf','inputs.json','command.json','console.log','work/run.vcs.log',
                         'commit_trace.csv','trace_summary.json','strict_original.json','child_outcome.unvalidated.json',
                         'runner_result.unvalidated.json','child_command.provenance.json')]
            terminal.update(status=PASS,pins_unchanged=True,evidence_pins={str(p):sha(p) for p in files},
                            full_parent_accepted=False,min_accepted=False)
        except BaseException as error:
            abort.set()
            terminal.update(status='NOT_PASS',error=repr(error))
            first_cause(out,dict(kind='WORKER_EXCEPTION',error=repr(error)))
            terminal['unvalidated_children']={n:read(root/'child_outcome.unvalidated.json') for n,root in roots.items()
                                             if (root/'child_outcome.unvalidated.json').exists()}
        finally:
            terminal['finished']=time.time()
            common.publish(out,terminal,abort)
    print(terminal['status'],flush=True)
    return int(terminal['status']!=PASS)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['prepare','dryrun','run'])
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--image',type=Path,default=IMAGE)
    p.add_argument('--reserved-slots',type=int,default=0)
    p.add_argument('--authorize-prepare',action='store_true')
    p.add_argument('--authorize-run',action='store_true')
    p.add_argument('--plan-sha256')
    p.add_argument('--parent-review',type=Path)
    p.add_argument('--parent-review-sha256')
    a=p.parse_args()
    out,image=a.out.resolve(),a.image.resolve()
    require(out.parent==HERE,'Owned direct fresh output only')
    if a.mode=='prepare':
        require(a.authorize_prepare,'Explicit prepare permission')
        durable(HERE/'prepare_attempt02.json',dict(command=sys.argv,out=str(out),DUT_started=False))
        try:
            prepare(image,out,a.reserved_slots)
        except BaseException as error:
            durable(HERE/'prepare_rejected02.json',dict(error=repr(error),no_retry=True,DUT_started=False))
            raise
        return 0
    if a.mode=='dryrun':
        dryrun(image,out,a.plan_sha256)
        return 0
    env=common.base.shared.environment()
    os.environ.clear()
    os.environ.update(env)
    return run(image,out,a.plan_sha256,a.authorize_run,a.parent_review,a.parent_review_sha256)


if __name__=='__main__':
    raise SystemExit(main())
