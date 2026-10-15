#!/usr/bin/env python3
"""Prepare/dryrun one existing M6 ELF; run needs pinned parent authorization."""
import json
import os
from dataclasses import asdict
from pathlib import Path
import re
import shlex
import subprocess
import sys
import threading
import time
sys.dont_write_bytecode=True
import checker
from checker import HERE,REF,G,NAME,HISTORICAL,READY_SHA,require,read,sha,common,load

worker=load('negative_stride_frozen_worker',G/'merge_original_prefix98_vcs_m6_plan01/replay.py')
outcome=load('negative_stride_durable_outcome',G/'fp_compare_unboxed_prefix265_vcs_m6_plan01/provenance_recovery01/adapter.py')
TIMEOUT,WORKER_BOUND,OUTER=5400,7200,7800
UNIT='ara-negative-stride-store-m6-01.service'
IMAGE_SHA='a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0'
AUDIT=HERE.parent/'store_entry_review01'
AUDIT_PINS={str(AUDIT/'ENTRY.md'):'e77981f68f4e0df9d144b25dddb6e39805c1935f2f06e61bdbf1b851e5374cf6',
            str(AUDIT/'ENTRY.json'):'e8f1d31fcf521c988178e20ac07052329d7cb654d66795f2274b03db68e6e55e'}

def accepted_adapter():
    common.base.verify_pins(AUDIT_PINS);a=read(AUDIT/'ENTRY.json');r=read(REF/'READY.json')
    require(a['schema']=='NEGATIVE_STRIDE_STORE_ENTRY_REVIEW_V1' and
            a['decision']=='ACCEPTED_FOR_WORKER_PREPARATION_REFERENCE_ONLY_NOT_DUT' and a['blocking_findings']==[] and
            a['ready_sha256']==READY_SHA and a['ready_pins_verified']==66 and a['source_name']==HISTORICAL and
            a['soc_elf_sha256']==r['soc_elf_sha256'] and a['source_cases']==1 and
            a['reference_scalar_checks']==17275 and a['reference_firmware_records']==858371 and
            a['full_checkpoint_count']==4 and a['each_checkpoint_data_memory_bytes']==8192 and
            a['reference_actual_returncode']==a['reference_wrapper_actual_wait_returncode']==0 and
            a['dut_launch_authorized_by_review'] is False and a['independent_full_raw_parse'] is False,
            'Actual ENTRY schema/scope')
    for key,path in (('source_proof_sha256',REF/'software01/source_proof.json'),
                     ('reference_result_sha256',REF/'reference01/status.json'),
                     ('execution_sha256',REF/'reference01/execution.json'),
                     ('wrapper_wait_sha256',REF/'reference01/wrapper_wait.json')):
        require(a[key]==sha(path),'ENTRY evidence link '+key)
    return dict(AUDIT_PINS)

def scope():
    spec=checker.specification()
    return dict(id=NAME,original_name=HISTORICAL,elf=spec['elf'],sha256=spec['elf_sha256'],
                timeout_s=TIMEOUT,pass_markers=['NEGATIVE_STRIDE_STORE_SINGLE_PASS']),spec

def validate(data,image):
    case,spec=scope()
    require(data['status']=='PREPARED_NOT_RUN' and data['image']==str(image) and
            data['image_sha256']==sha(image/'image.json')==IMAGE_SHA,'Image/plan drift')
    require(data['case']==case and data['spec']==spec and data['jobs']==1 and data['timeout_s']==TIMEOUT and
            data['worker_timeout_s']==WORKER_BOUND and data['service_timeout_s']==OUTER and data['unit']==UNIT and data['no_retry'] and data['no_build'] and
            data['no_fsdb'] and data['reference_ready_sha256']==READY_SHA,'Scope/budget drift')
    require(data['adapter_review_pins']==accepted_adapter(),'Static review pins differ')
    require(data['pins'].get(str(Path(__file__).resolve()))==sha(Path(__file__)),'Worker drift')
    original=read(REF/'READY.json')['pins']
    require(len(original)==66 and all(data['pins'].get(p)==h for p,h in original.items()),'All original66 pins must survive')
    common.base.verify_pins(data['pins'])

def prepare(image,out,reserved):
    require(not out.exists(),'Fresh prepared directory only')
    require(sha(REF/'READY.json')==READY_SHA,'Reference READY drift')
    r=read(REF/'READY.json');pins=dict(r['pins'])
    require(len(pins)==66 and r['no_DUT_launch'] and r['source_cases']==1 and
            r['source_name']==HISTORICAL and r['scalar_checks']==17275 and
            r['firmware_commit_format_records']==858371,'Exact store reference scope')
    pins[str(REF/'READY.json')]=READY_SHA;pins.update(accepted_adapter())
    ledger,repo,_=common.image_context(image)
    require(sha(image/'image.json')==IMAGE_SHA and Path(ledger['snapshot']).parent.name=='current_board_memory_candidate06','Frozen M6 only')
    pins.update(common.image_pins(image,ledger,repo));case,spec=scope()
    for path in (HERE/'host01.json',HERE/'csv_host01/status.json'):
        host=read(path);require(host['status']=='PASS_HOST_ONLY_NOT_DUT','Host gate missing/failing')
        common.base.verify_pins(host['pins']);pins.update(host['pins']);pins[str(path)]=sha(path)
    for module in list(sys.modules.values()):
        f=getattr(module,'__file__',None)
        if f and Path(f).is_file() and Path(f).resolve().is_relative_to(G.parents[2]):
            pins[str(Path(f).resolve())]=sha(Path(f))
    for name in ('replay.py','checker.py','csv_check.py','test_host.py','test_csv.py','README.md'):
        pins[str(HERE/name)]=sha(HERE/name)
    require(type(reserved) is int and 0<=reserved<=24,'Unused reservation only, live counted once')
    common.base.verify_pins(pins);out.mkdir()
    common.save(out/'plan.json',dict(status='PREPARED_NOT_RUN',image=str(image),image_sha256=IMAGE_SHA,
        snapshot_sha256=ledger['snapshot_sha256'],case=case,spec=spec,pins=pins,jobs=1,timeout_s=TIMEOUT,
        worker_timeout_s=WORKER_BOUND,service_timeout_s=OUTER,unit=UNIT,reserved_slots=reserved,no_build=True,no_retry=True,no_fsdb=True,
        reference_ready_sha256=READY_SHA,reference_original_pin_count=66,adapter_review_pins=AUDIT_PINS,
        adapter_review_scope='Static adapter only, not independent raw-reference acceptance or DUT launch',
        runtime_testcase=NAME,monitor_numeric_outcome_before_validation=True,
        budget=dict(reference_firmware_records=858371,proxy743_plus20_s=858371/743*1.2,
                    slow273_plus20_s=858371/273*1.2,
                    guarantee=False,automatic_extension=False),
        source_single=True,linux_or_parent96_acceptance=False,resource_snapshot=None,
        resource_check_deferred_to_authorized_run=True))
    digest=sha(out/'plan.json')
    cmd=[sys.executable,'-B',str(Path(__file__).resolve()),'run','--image',str(image),'--out',str(out),
         '--plan-sha256',digest,'--authorize-run','--parent-review','PARENT_REVIEW_JSON',
         '--parent-review-sha256','PARENT_REVIEW_SHA256']
    service=['systemd-run','--user','--unit='+UNIT,'--property=RuntimeMaxSec='+str(OUTER),
             '--property=KillMode=control-group','--property=Restart=no','--property=WorkingDirectory='+str(HERE),
             '--property=StandardOutput=append:'+str(out/'service.log'),'--property=StandardError=append:'+str(out/'service.log'),*cmd]
    common.save(out/'ready.json',dict(status='PREPARED_NOT_ADMITTED_NO_DUT',plan_sha256=digest,
        command=cmd,service_command=shlex.join(service),pins=len(pins),DUT_started=False))
    print('PREPARED_NOT_ADMITTED_NO_DUT',digest,flush=True)

def authorization_gate(plan,digest,path,digest_review):
    require(path is not None and digest_review and sha(path)==digest_review,'Pinned new parent authorization required')
    review=read(path)
    require(review['decision']=='AUTHORIZE_NEGATIVE_STRIDE_STORE_SINGLE_M6_ONCE' and review['plan_sha256']==digest and
            review['unit']==UNIT and review['reference_ready_sha256']==READY_SHA and
            review['adapter_review_pins']==accepted_adapter() and review['budget_risk_accepted'] is True,
            'Parent scope/review/budget authorization')
    return {str(path):digest_review,**accepted_adapter(),str(REF/'READY.json'):READY_SHA}

def service_identity(unit):
    runtime=Path('/run/user')/str(os.getuid())
    require(runtime.is_dir() and runtime.stat().st_uid==os.getuid() and (runtime/'bus').is_socket(),'Trusted user bus unavailable')
    env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(runtime/'bus'))
    names=('Id','LoadState','ActiveState','SubState','MainPID','ControlGroup','RuntimeMaxUSec','KillMode','Restart')
    q=subprocess.run(['systemctl','--user','show',unit,'--property='+','.join(names)],env=env,text=True,capture_output=True,timeout=10)
    require(q.returncode==0 and not q.stderr.strip(),'Service query error')
    props=dict(line.split('=',1) for line in q.stdout.splitlines());cgroup=Path('/proc/self/cgroup').read_text()
    require(set(props)==set(names) and props['Id']==unit and props['LoadState']=='loaded' and
            props['ActiveState']=='active' and props['SubState']=='running' and props['MainPID']==str(os.getpid()) and
            props['ControlGroup'].endswith('/'+unit) and any(x.split(':',2)[-1]==props['ControlGroup'] for x in cgroup.splitlines()) and
            props['RuntimeMaxUSec']=='2h 10min' and props['KillMode']=='control-group' and props['Restart']=='no','Wrong direct service owner/budget')
    return dict(pid=os.getpid(),properties=props,cgroup=cgroup,query_stdout=q.stdout)

def durable_monitor(original):
    def monitored(command,cwd,console_path,timeout_s,cancel_event=None):
        rc,elapsed,timed_out,failure_seen=original(command,cwd,console_path,timeout_s,cancel_event)
        require(type(rc) is int,'Actual monitored wait code missing')
        record=dict(schema='UNVALIDATED_MONITOR_OUTCOME_V1',architectural_acceptance=False,
            returncode=rc,elapsed_s=elapsed,timed_out=timed_out,failure_seen=failure_seen,
            abort_set=bool(cancel_event and cancel_event.is_set()),command=list(map(str,command)),cwd=str(cwd),
            command_sha256=sha(Path(console_path).parent/'command.json'))
        with (Path(console_path).parent/'monitor_outcome.unvalidated.json').open('x') as f:
            json.dump(record,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        return rc,elapsed,timed_out,failure_seen
    return monitored

def checked_runner(parent,abort,check):
    inherited=outcome.successor_checked_runner(parent,abort,check)
    class Runner(inherited):
        def _run_test(self,*args):
            import ara_verify.runner as engine
            saved=engine._run_monitored;engine._run_monitored=durable_monitor(saved)
            try:return super()._run_test(*args)
            finally:engine._run_monitored=saved
    return Runner

def quiesce_deadline(timer,abort,deadline):
    timer.cancel();timer.join()
    if time.monotonic()>=deadline:abort.set()

def run(image,out,digest,authorized,review_path,review_digest):
    require(authorized and digest and sha(out/'plan.json')==digest,'Explicit pinned parent authorization required')
    plan=read(out/'plan.json');validate(plan,image)
    approval=authorization_gate(plan,digest,review_path,review_digest)
    ledger,repo,(parent,options,testcase,_)=common.image_context(image)
    owner=service_identity(UNIT);admission=common.resources(out,1,plan['reserved_slots'])
    common.save(out/'launch.json',dict(owner=owner,admission=admission,approval_pins=approval,
                                      started=time.time(),plan_sha256=digest))
    abort=threading.Event();deadline=time.monotonic()+WORKER_BOUND
    timer=threading.Timer(WORKER_BOUND,abort.set);timer.daemon=True
    terminal=dict(status='NOT_PASS',plan_sha256=digest,retries=0,results=[],pins_unchanged=False)
    import ara_verify.runner as engine
    from ara_verify.trace import validate_trace
    old_fail=engine.FAIL_RE
    engine.FAIL_RE=re.compile(old_fail.pattern+'|'+checker.VETO.pattern,re.I)
    with common.abort_signals(abort):
        timer.start()
        try:
            require(not (out/'replay').exists(),'No retry/overwrite')
            def check(result):
                require(not abort.is_set(),'Aborted before validation')
                report=checker.artifacts(result,plan['case'],ledger,plan['spec'],validate_trace)
                common.save(result.artifact_dir/'strict_prefix.json',report)
            opts=worker.build_options(options,repo,out/'replay',ledger)
            tests=[testcase(NAME,'app','',Path(plan['case']['elf']),NAME,TIMEOUT)]
            results=checked_runner(parent,abort,check)(opts,tests,sys.argv).run()
            terminal['results']=[dict(asdict(r),artifact_dir=str(r.artifact_dir)) for r in results]
            worker.terminal_gate(results,read(out/'replay/run.json'),abort,ledger)
            require(read(out/'replay/summary.json')==terminal['results'],'Summary differs')
            worker.final_inputs(out,digest,image,approval)
            evidence={str(p):sha(p) for p in (out/'launch.json',out/'replay/run.json',out/'replay/summary.json')}
            root=out/'replay/tests'/NAME
            for n in ('input.elf','inputs.json','command.json','console.log','work/run.vcs.log',
                      'commit_trace.csv','trace_summary.json','strict_prefix.json',
                      'monitor_outcome.unvalidated.json','child_outcome.unvalidated.json'):
                evidence[str(root/n)]=sha(root/n)
            require(sha(out/'plan.json')==digest,'Late disk plan drift')
            terminal.update(status=worker.PASS,evidence_pins=evidence,pins_unchanged=True,
                            source_single=True,linux_or_parent96_accepted=False,axi_b_handshakes_measured=False)
        except BaseException as error:
            abort.set();terminal.update(status='NOT_PASS',error=f'{type(error).__name__}: {error}')
            if (out/'replay/summary.json').exists():terminal['results']=read(out/'replay/summary.json')
        finally:
            quiesce_deadline(timer,abort,deadline)
            engine.FAIL_RE=old_fail;terminal['finished']=time.time()
            common.publish(out,terminal,abort)
    print(terminal['status'],flush=True)
    return int(terminal['status']!=worker.PASS)

worker.HERE=HERE;worker.REF=REF;worker.NAME=NAME;worker.TIMEOUT=TIMEOUT;worker.OUTER=OUTER;worker.UNIT=UNIT
worker.PASS='PASS_M6_NEGATIVE_STRIDE_STORE_SOURCE_SINGLE_NOT_LINUX'
worker.prepare=prepare;worker.scope=scope;worker.validate=validate
worker.authorization_gate=authorization_gate;worker.service_identity=service_identity;worker.checked_runner=checked_runner
worker.run=run
if __name__=='__main__':raise SystemExit(worker.main())
