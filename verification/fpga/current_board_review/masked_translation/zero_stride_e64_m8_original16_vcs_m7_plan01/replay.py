#!/usr/bin/env python3
"""One authorized frozen-M7 full-original16 run and closed-CSV checker."""
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
import tempfile
import time
sys.dont_write_bytecode=True
import checker
from checker import HERE,REF,G,NAME,HISTORICAL,READY_SHA,IMAGE,IMAGE_SHA,common,read,sha,require,load
frozen=load('zero16_frozen_execution',HERE.parent/'negative_stride_store_vcs_m6_plan01/replay.py')
TIMEOUT,WORKER_BOUND,OUTER=10800,12000,12600
UNIT='ara-zero-stride-e64-m8-original16-m7-01.service'
PASS='PASS_M7_ORIGINAL16_NOT_LINUX'

def scope():
    spec=checker.specification()
    return dict(id=NAME,original_name=HISTORICAL,elf=spec['elf'],sha256=spec['elf_sha256'],timeout_s=TIMEOUT,
                pass_markers=['ZERO_STRIDE_ORIGINAL16_PASS cases=16 faults=12 errors=0']),spec

def review():
    # Source/Host/cost admission is authorized by the current user task.
    return {}

def cost():
    fw=read(REF/'READY02.json')['firmware_instructions']
    slow=fw/273*1.2
    require(slow<=10800,'Measured firmware projection exceeds 3h; no DUT dispatch')
    return dict(reference_firmware_records=fw,proxy766_s=fw/(851704/1111.624555705),
                slow273_plus20_s=slow,guarantee=False,automatic_extension=False)

def validate(plan,image):
    case,spec=scope()
    require(image==IMAGE and plan['image']==str(image) and plan['image_sha256']==sha(image/'image.json')==IMAGE_SHA,'Exact frozen M7')
    require(plan['case']==case and plan['spec']==spec and plan['jobs']==1 and plan['timeout_s']==TIMEOUT and
            plan['worker_timeout_s']==WORKER_BOUND and plan['service_timeout_s']==OUTER and plan['unit']==UNIT and
            all(plan[k] is True for k in ('no_build','no_retry','no_fsdb','stop_first_fail')),'Original scope/budget drift')
    require(plan['reference_ready_sha256']==READY_SHA and plan['review_pins']==review(),'Reference/review binding')
    original=read(REF/'evidence_pins02.json')
    require(all(plan['pins'].get(p)==h for p,h in original.items()),'All original61 pins retained')
    require(plan['pins'].get(str(HERE/'replay.py'))==sha(HERE/'replay.py'),'Current worker pin')
    common.base.verify_pins(plan['pins'])

def disk_gate(out,digest,image):
    require(sha(out/'plan.json')==digest,'Fresh disk plan SHA');validate(read(out/'plan.json'),image)
    require(sha(out/'plan.json')==digest,'Plan changed during validation')

def options_for(options,repo,out,ledger,dry=False):
    return options(repo_root=repo,output_root=out/('dryrun' if dry else 'replay'),config='default',jobs=1,seed=1,
                   dry_run=dry,build_only=False,skip_build=True,simv=Path(ledger['simv']),commit_trace=True,timeout_s=TIMEOUT)

def prepare(image,out,host,reserved):
    require(image==IMAGE and not out.exists(),'Fresh owned output/M7 only')
    require(host.is_relative_to(HERE),'Owned Host output')
    h=read(host/'status.json')
    require(h['status']=='PASS_HOST_ONLY_NOT_DUT' and h['positive']['cases']==16 and h['positive']['checks']==checker.CHECKS and len(h['negative'])>=17,'Full16 Host gate')
    common.base.verify_pins(h['pins']);pins=checker.reference_pins();pins.update(h['pins']);pins[str(host/'status.json')]=sha(host/'status.json')
    runtime=read(HERE/'runtime_host02.json')
    require(runtime['status']=='PASS_HOST_ONLY_NOT_DUT' and runtime['tests']>=9 and not runtime['errors'] and not runtime['failures'],'Runtime Host gate')
    common.base.verify_pins(runtime['pins']);pins.update(runtime['pins']);pins[str(HERE/'runtime_host02.json')]=sha(HERE/'runtime_host02.json')
    pins.update(review());ledger,repo,_=common.image_context(image);pins.update(common.image_pins(image,ledger,repo))
    for m in list(sys.modules.values()):
        p=getattr(m,'__file__',None)
        if p and Path(p).is_file() and Path(p).resolve().is_relative_to(G.parents[2]):pins[str(Path(p).resolve())]=sha(Path(p))
    for name in ('replay.py','checker.py','csv_check.py','test_host.py','test_runtime.py'):
        pins[str(HERE/name)]=sha(HERE/name)
    case,spec=scope()
    require(type(reserved) is int and 0<=reserved<=24,'Unused reservation count')
    plan=dict(status='PREPARED_NOT_RUN',image=str(image),image_sha256=IMAGE_SHA,snapshot_sha256=ledger['snapshot_sha256'],
      case=case,spec=spec,pins=pins,jobs=1,timeout_s=TIMEOUT,worker_timeout_s=WORKER_BOUND,service_timeout_s=OUTER,
      unit=UNIT,reserved_slots=reserved,no_build=True,no_retry=True,no_fsdb=True,stop_first_fail=True,
      review_pins=review(),reference_ready_sha256=READY_SHA,host_status=str(host/'status.json'),
      parent_authorization='Current user: original16 M2/M8 software Host+Spike and firmware projection <=3h, then M7 two parallel runs; no additional approval report',
      scope='Continuous original16/12fault/16ecall; frozen M7 after DRAIN_EXCEPTION_MASK and descriptor guard',
      automatic_terminal_checker=True,original_linux_stall_closed=False,
      budget=cost())
    validate(plan,image);out.mkdir();common.save(out/'plan.json',plan);digest=sha(out/'plan.json')
    cmd=[sys.executable,'-B',str(HERE/'replay.py'),'run','--image',str(image),'--out',str(out),'--plan-sha256',digest,'--authorize-run']
    service=['systemd-run','--user','--unit='+UNIT,'--property=RuntimeMaxSec='+str(OUTER),'--property=KillMode=control-group',
      '--property=Restart=no','--property=WorkingDirectory='+str(HERE),'--property=StandardOutput=append:'+str(out/'service.log'),
      '--property=StandardError=append:'+str(out/'service.log'),*cmd]
    common.save(out/'ready.json',dict(status='PREPARED_NOT_LAUNCHED',plan_sha256=digest,command=cmd,service_command=service,
                                    command_text=shlex.join(service),pins=len(pins),DUT_started=False))
    print('PREPARED_NOT_LAUNCHED',digest,flush=True)

def service_identity():
    runtime=Path('/run/user')/str(os.getuid())
    require(runtime.is_dir() and runtime.stat().st_uid==os.getuid() and (runtime/'bus').is_socket(),'Trusted user bus')
    env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(runtime/'bus'))
    names={'Id','LoadState','ActiveState','SubState','MainPID','ControlGroup','RuntimeMaxUSec','KillMode','Restart'}
    q=subprocess.run(['systemctl','--user','show',UNIT,'--property='+','.join(sorted(names))],env=env,text=True,capture_output=True,timeout=10)
    require(q.returncode==0 and not q.stderr.strip(),'Actual user-service query')
    props=dict(line.split('=',1) for line in q.stdout.splitlines());group=Path('/proc/self/cgroup').read_text()
    require(set(props)==names and props['Id']==UNIT and props['LoadState']=='loaded' and props['ActiveState']=='active' and
      props['SubState']=='running' and props['MainPID']==str(os.getpid()) and props['ControlGroup'].endswith('/'+UNIT) and
      props['ControlGroup'] in [s.split(':',2)[-1] for s in group.splitlines()] and props['RuntimeMaxUSec']=='3h 30min' and
      props['KillMode']=='control-group' and props['Restart']=='no','Direct service owner/hard deadline')
    return dict(pid=os.getpid(),properties=props,cgroup=group,stdout=q.stdout)

def dryrun(image,out,digest):
    disk_gate(out,digest,image);require(not (out/'dryrun').exists(),'Fresh dryrun')
    ledger,repo,(parent,opts,testcase,_)=common.image_context(image);case=read(out/'plan.json')['case']
    results=parent(options_for(opts,repo,out,ledger,True),[testcase(NAME,'app','',Path(case['elf']),NAME,TIMEOUT)],sys.argv).run()
    require(len(results)==1 and results[0].name==NAME and results[0].status=='DRY_RUN','Exact no-DUT dryrun')
    disk_gate(out,digest,image);common.save(out/'dryrun_gate.json',dict(status='DRYRUN_ONLY_NO_DUT',plan_sha256=digest))

def durable_monitor(original):
    def monitored(command,cwd,console_path,timeout_s,cancel_event=None):
        rc,elapsed,timed_out,failure_seen=original(command,cwd,console_path,timeout_s,cancel_event)
        record=dict(schema='UNVALIDATED_MONITOR_OUTCOME_V1',architectural_acceptance=False,
          returncode=rc,elapsed_s=elapsed,timed_out=timed_out,failure_seen=failure_seen,
          abort_set=bool(cancel_event and cancel_event.is_set()),command=list(map(str,command)),cwd=str(cwd))
        root=Path(console_path).parent
        with (root/'monitor_numeric.unvalidated.json').open('x') as f:
            json.dump(record,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        require(type(rc) is int,'Actual numeric monitor code required')
        record['command_sha256']=sha(root/'command.json')
        common.save(root/'monitor_outcome.unvalidated.json',record)
        return rc,elapsed,timed_out,failure_seen
    return monitored

def checked_runner(parent,abort,check):
    inherited=frozen.outcome.successor_checked_runner(parent,abort,check)
    class Runner(inherited):
        def _run_test(self,*args):
            import ara_verify.runner as engine
            saved=engine._run_monitored
            engine._run_monitored=durable_monitor(saved)
            try:return super()._run_test(*args)
            finally:engine._run_monitored=saved
    return Runner

def run(image,out,digest,authorized):
    require(authorized and digest,'Explicit once-run authorization');disk_gate(out,digest,image)
    plan=read(out/'plan.json');ledger,repo,(parent,opts,testcase,_)=common.image_context(image)
    owner=service_identity();resources=common.resources(out,1,plan['reserved_slots'])
    common.save(out/'launch.json',dict(owner=owner,resources=resources,started=time.time(),plan_sha256=digest,review_pins=review()))
    abort=threading.Event();deadline=time.monotonic()+WORKER_BOUND;timer=threading.Timer(WORKER_BOUND,abort.set);timer.daemon=True
    terminal=dict(status='NOT_PASS',plan_sha256=digest,results=[],retries=0,pins_unchanged=False)
    import ara_verify.runner as engine
    from ara_verify.trace import validate_trace
    old_fail=engine.FAIL_RE;engine.FAIL_RE=re.compile(old_fail.pattern+'|'+checker.VETO.pattern,re.I)
    with common.abort_signals(abort):
        timer.start()
        try:
            require(not (out/'replay').exists(),'No retry/overwrite')
            def check(result):
                require(not abort.is_set(),'Aborted before automatic terminal checker')
                report=checker.artifacts(result,plan['case'],ledger,plan['spec'],validate_trace)
                common.save(result.artifact_dir/'strict_original16.json',report)
            tests=[testcase(NAME,'app','',Path(plan['case']['elf']),NAME,TIMEOUT)]
            results=checked_runner(parent,abort,check)(options_for(opts,repo,out,ledger),tests,sys.argv).run()
            terminal['results']=[dict(asdict(r),artifact_dir=str(r.artifact_dir)) for r in results]
            meta=read(out/'replay/run.json');common.check_stage(results,meta,[plan['case']],abort)
            require(meta['tests']==[NAME] and meta['jobs']==1 and meta['seed']==1 and meta['timeout_s']==TIMEOUT and
                    meta['simv']==ledger['simv'] and meta['commit_trace'] is True and meta['code_coverage'] is False,'Exact COMPLETE run contract')
            require(read(out/'replay/summary.json')==terminal['results'],'Summary mismatch')
            disk_gate(out,digest,image);common.image_context(image)
            evidence={str(p):sha(p) for p in (out/'launch.json',out/'replay/run.json',out/'replay/summary.json')}
            root=out/'replay/tests'/NAME
            for name in ('input.elf','inputs.json','command.json','console.log','work/run.vcs.log','commit_trace.csv','trace_summary.json',
                         'monitor_numeric.unvalidated.json','monitor_outcome.unvalidated.json','child_outcome.unvalidated.json','terminal_original16.json','strict_original16.json'):
                evidence[str(root/name)]=sha(root/name)
            require(sha(out/'plan.json')==digest,'Late disk plan drift')
            terminal.update(status=PASS,evidence_pins=evidence,pins_unchanged=True,baseline_image='M7_MASK_DRAIN_DESCRIPTOR_GUARD',linux_stall_closed=False)
        except BaseException as e:
            abort.set();terminal.update(status='NOT_PASS',error=f'{type(e).__name__}: {e}')
            if (out/'replay/summary.json').exists():terminal['results']=read(out/'replay/summary.json')
        finally:
            frozen.quiesce_deadline(timer,abort,deadline);engine.FAIL_RE=old_fail;terminal['finished']=time.time();common.publish(out,terminal,abort)
    print(terminal['status'],flush=True);return int(terminal['status']!=PASS)

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','dryrun','run'))
    for n in ('image','out','host'):p.add_argument('--'+n,type=Path,required=n!='host')
    p.add_argument('--plan-sha256');p.add_argument('--reserved-slots',type=int,default=0);p.add_argument('--authorize-run',action='store_true')
    a=p.parse_args();image=a.image.resolve();out=a.out.resolve();require(out.parent==HERE,'Owned direct child only')
    env=common.base.shared.environment();os.environ.clear();os.environ.update(env)
    if a.mode=='prepare':require(a.host is not None,'Host required');prepare(image,out,a.host.resolve(),a.reserved_slots);return 0
    if a.mode=='dryrun':dryrun(image,out,a.plan_sha256);return 0
    return run(image,out,a.plan_sha256,a.authorize_run)
if __name__=='__main__':raise SystemExit(main())

