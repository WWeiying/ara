#!/usr/bin/env python3
"""Ten unchanged reference ELFs, frozen M6 only, two workers, no retry/build."""
import argparse
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
sys.dont_write_bytecode = True
import csv_check

HERE = Path(__file__).resolve().parent
REF = HERE.parent
G = HERE.parents[3]
sys.path.insert(0,str(G/'gather_repair05'))
import regression as common
read,sha,require = common.read,common.sha,csv_check.require
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image')
IMAGE_SHA = 'a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0'
UNIT = 'ara-negative-stride-remaining38-m6-01.service'
JOBS, TIMEOUT, CHECK_TIMEOUT, WORKER_BOUND, OUTER = 2,10800,900,58500,59400
PASS = 'PASS_M6_NEGATIVE_STRIDE_REMAINING38_NOT_LINUX'
VETO = re.compile(common.BAD.pattern+r'|NEGATIVE_STRIDE_BATCH_FAIL|BOARD_REPLAY_MISMATCH|RVV_[A-Z0-9_]*FAIL|\b(?:FATAL|FAILED|FAIL|ABORT|MISMATCH)\b',re.I)


def save(path,data):
    with Path(path).open('x') as f:
        json.dump(data,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())


def console_gate(text):
    require(not VETO.search(text),'Raw failure marker veto')
    require(text.splitlines().count('NEGATIVE_STRIDE_BATCH_PASS')==1 and
            'Core Test *** SUCCESS *** (tohost = 0)' in text and '$finish' in text,'Exact oracle/success/finish')


def outcome_gate(record):
    require(type(record['returncode']) is int and record['returncode']==0 and
            record['status']=='PASS' and not record['reason'],'Actual child numeric outcome')


def aftercheck_gate(abort):
    require(not abort.is_set(),'Late abort during check')


def scope():
    ready = read(REF/'READY.json')
    require(ready['status']=='READY_38_SOURCE_SV39_REFERENCE_NOT_DUT' and ready['cases']==38 and
            ready['budget']['all_estimates_under_10800'] is True,'Full38 reference gate')
    cases = []
    for i,g in enumerate(ready['groups']):
        label = f'group{i:02d}'
        require(g['group']==label and g['cases']==(4 if i<9 else 2),'Original group order/count')
        name = 'negative38_'+label
        cases.append(dict(id=name,original_name=name,source_names=g['original_names'],group=label,
                          elf=g['soc_elf'],sha256=g['soc_elf_sha256'],timeout_s=TIMEOUT,
                          pass_markers=['NEGATIVE_STRIDE_BATCH_PASS'],checks=g['scalar_checks'],
                          reference_firmware_records=g['firmware_records'],estimate_s=g['conservative_m6_estimate_s']))
    require(len(cases)==10 and len({n for c in cases for n in c['source_names']})==38,'Exact membership')
    return cases


def validate(plan,digest,out):
    require(sha(out/'plan.json')==digest,'Fresh plan SHA')
    require(plan['status']=='PREPARED_NOT_RUN' and plan['cases']==scope() and plan['jobs']==JOBS and
            plan['image']==str(IMAGE) and plan['image_sha256']==sha(IMAGE/'image.json')==IMAGE_SHA and
            plan['timeout_s']==TIMEOUT and plan['check_timeout_s']==CHECK_TIMEOUT and
            plan['worker_bound_s']==WORKER_BOUND and plan['service_bound_s']==OUTER and plan['unit']==UNIT and
            plan['no_retry'] is True and plan['no_build'] is True and plan['no_fsdb'] is True,
            'Scope/image/budget drift')
    require(type(plan['reserved_slots']) is int and 0<=plan['reserved_slots']<=24,'Resource reservation')
    common.base.verify_pins(plan['pins'])
    require(sha(out/'plan.json')==digest,'Plan changed during validation')


def prepare(out,reserved):
    require(not out.exists(),'Fresh output only')
    host = read(HERE/'host02.log.wait.json')
    require(type(host['actual_wait_returncode']) is int and host['actual_wait_returncode']==0 and not host['timeout'], 'CSV Host receipt')
    host_runner = read(HERE/'runner_host02.log.wait.json')
    require(type(host_runner['actual_wait_returncode']) is int and host_runner['actual_wait_returncode']==0 and not host_runner['timeout'],'Runner Host receipt')
    ledger,repo,_ = common.image_context(IMAGE)
    require(sha(IMAGE/'image.json')==IMAGE_SHA,'Frozen M6 identity')
    pins = {**read(REF/'READY.json')['pins'],**common.image_pins(IMAGE,ledger,repo)}
    for module in list(sys.modules.values()):
        f = getattr(module,'__file__',None)
        if f and Path(f).is_file() and Path(f).resolve().is_relative_to(G.parents[2]):
            pins[str(Path(f).resolve())] = sha(Path(f))
    for f in [REF/'READY.json',REF/'REPORT.md',HERE/'csv_check.py',HERE/'replay.py',HERE/'test_host.py',
              HERE/'test_runner.py',HERE/'host02.log',HERE/'host02.log.wait.json',
              HERE/'runner_host02.log',HERE/'runner_host02.log.wait.json']:
        pins[str(f)] = sha(f)
    plan = dict(status='PREPARED_NOT_RUN',cases=scope(),jobs=JOBS,image=str(IMAGE),image_sha256=IMAGE_SHA,
                snapshot_sha256=ledger['snapshot_sha256'],pins=pins,timeout_s=TIMEOUT,check_timeout_s=CHECK_TIMEOUT,
                worker_bound_s=WORKER_BOUND,service_bound_s=OUTER,unit=UNIT,reserved_slots=reserved,
                no_build=True,no_fsdb=True,no_retry=True,stop_first_failure=True,
                authorization='User explicitly authorized current unchanged10 M6 groups/jobs2/10800s after reference38 PASS',
                budget_note='10800s hard simulation budget per group; separate900s bounded terminal checker. Five waves, no extension.',
                source_scope='Remaining38 source-derived singles, not Linux/full parent96 or M7 acceptance')
    out.mkdir();save(out/'plan.json',plan)
    digest = sha(out/'plan.json')
    validate(plan,digest,out)
    cmd = [sys.executable,'-B',str(HERE/'replay.py'),'run','--out',str(out),'--plan-sha256',digest,'--authorize-run']
    service = ['systemd-run','--user','--unit='+UNIT,'--property=RuntimeMaxSec='+str(OUTER),
               '--property=KillMode=control-group','--property=Restart=no','--property=WorkingDirectory='+str(HERE),
               '--property=StandardOutput=append:'+str(out/'service.log'),
               '--property=StandardError=append:'+str(out/'service.log'),*cmd]
    save(out/'ready.json',dict(status='PREPARED_NO_DUT',plan_sha256=digest,command=cmd,service_command=service,
                              service_shell=shlex.join(service),pins=len(pins)))
    print(json.dumps(dict(status='PREPARED_NO_DUT',plan_sha256=digest,pins=len(pins))))


def options(kind,repo,out,ledger,dry=False):
    return kind(repo_root=repo,output_root=out/('dryrun' if dry else 'replay'),config='default',jobs=JOBS,
                seed=1,dry_run=dry,build_only=False,skip_build=True,simv=Path(ledger['simv']),
                commit_trace=True,timeout_s=None)


def cases_for(kind,cases):
    return [kind(c['id'],'app','',Path(c['elf']),c['id'],c['timeout_s']) for c in cases]


def service_identity():
    names = ('Id','LoadState','ActiveState','SubState','MainPID','ControlGroup','RuntimeMaxUSec','KillMode','Restart')
    q = subprocess.run(['systemctl','--user','show',UNIT,'--property='+','.join(names)],text=True,capture_output=True,timeout=10)
    require(q.returncode==0 and not q.stderr.strip(),'Actual service query')
    props = dict(line.split('=',1) for line in q.stdout.splitlines())
    own = Path('/proc/self/cgroup').read_text()
    require(set(props)==set(names) and props['Id']==UNIT and props['LoadState']=='loaded' and
            props['ActiveState']=='active' and props['SubState']=='running' and props['MainPID']==str(os.getpid()) and
            props['ControlGroup'].endswith('/'+UNIT) and props['ControlGroup'] in [s.split(':',2)[-1] for s in own.splitlines()] and
            props['RuntimeMaxUSec']=='16h 30min' and props['KillMode']=='control-group' and props['Restart']=='no',
            'Direct service/cgroup/bound')
    return dict(pid=os.getpid(),properties=props,cgroup=own)


def artifacts(result,case,ledger):
    root = result.artifact_dir
    raw = read(root/'child_outcome.unvalidated.json')
    outcome_gate(raw)
    require(raw['name']==case['id'] and raw['elapsed_s']==result.elapsed_s and
            raw['command_sha256']==sha(root/'command.json'),'Durable child identity')
    common.check_artifacts(result,case,ledger)
    for f in (root/'console.log',root/'work/run.vcs.log'):
        console_gate(f.read_text())
    monitor = read(root/'monitor_outcome.unvalidated.json')
    require(type(monitor['returncode']) is int and monitor['returncode']==0 and
            not monitor['timed_out'] and not monitor['failure_seen'] and not monitor['abort_set'] and
            monitor['command_sha256']==sha(root/'command.json'),'Actual monitor outcome')
    command = [sys.executable,'-B',str(HERE/'csv_check.py'),str(REF/'software01'/case['group']),
               str(root/'commit_trace.csv'),str(root/'strict_original.json')]
    save(root/'observer.command.json',dict(command=command))
    start = time.monotonic()
    with (root/'observer.stdout').open('x') as f:
        child = subprocess.Popen(command,stdout=f,stderr=subprocess.STDOUT)
        timed_out = False
        try:
            rc = child.wait(timeout=CHECK_TIMEOUT)
        except subprocess.TimeoutExpired:
            timed_out = True;child.kill();rc = child.wait()
    save(root/'observer.wait.json',dict(actual_wait_returncode=rc,timed_out=timed_out,elapsed_s=time.monotonic()-start))
    require(type(rc) is int and rc==0 and not timed_out,'Full CSV oracle did not accept')
    strict = read(root/'strict_original.json')
    trace = read(root/'trace_summary.json')
    require(strict['status']=='PASS_M6_NEGATIVE_STRIDE_GROUP_NOT_LINUX' and
            strict['cases']==len(case['source_names']) and strict['checks']==case['checks'],'Exact full group oracle')
    # The base runner already applies its architectural trace validator.
    require(trace['status']=='VALID','Generic protocol trace')


def run(out,digest):
    plan = read(out/'plan.json');validate(plan,digest,out)
    require(read(out/'dryrun_gate.json')['plan_sha256']==digest,'Exact dryrun required')
    require(not (out/'launch.json').exists() and not (out/'replay').exists(),'No retry/overwrite')
    ledger,repo,(parent,kind,testcase,_) = common.image_context(IMAGE)
    owner = service_identity()
    resources = common.resources(out,JOBS,plan['reserved_slots'])
    save(out/'launch.json',dict(owner=owner,resources=resources,plan_sha256=digest,started=time.time()))
    abort = threading.Event()
    deadline = time.monotonic()+WORKER_BOUND
    timer = threading.Timer(WORKER_BOUND,abort.set);timer.daemon=True
    entries = {c['id']:c for c in plan['cases']}
    import ara_verify.runner as engine
    original_monitor,old_fail = engine._run_monitored,engine.FAIL_RE
    engine.FAIL_RE = re.compile(old_fail.pattern+'|'+VETO.pattern,re.I)
    def monitored(command,cwd,console_path,timeout_s,cancel_event=None):
        rc,elapsed,timed_out,failure_seen = original_monitor(command,cwd,console_path,timeout_s,cancel_event)
        save(Path(console_path).parent/'monitor_outcome.unvalidated.json',dict(
            returncode=rc,elapsed_s=elapsed,timed_out=timed_out,failure_seen=failure_seen,
            abort_set=bool(cancel_event and cancel_event.is_set()),architectural_acceptance=False,
            command_sha256=sha(Path(console_path).parent/'command.json')))
        return rc,elapsed,timed_out,failure_seen
    engine._run_monitored = monitored
    class Runner(parent):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw);self.cancel_event=abort
        def _run_test(self,test,image):
            try:
                require(not abort.is_set() and time.monotonic()+TIMEOUT+CHECK_TIMEOUT<=deadline,'Abort/global remaining budget')
                result = super()._run_test(test,image)
                record = dict(asdict(result),artifact_dir=str(result.artifact_dir),architectural_acceptance=False,
                              command_sha256=sha(result.artifact_dir/'command.json'))
                save(result.artifact_dir/'child_outcome.unvalidated.json',record)
                outcome_gate(record)
                artifacts(result,entries[test.name],ledger)
                aftercheck_gate(abort)
                return result
            except BaseException:
                abort.set();raise
    terminal = dict(status='NOT_PASS',results=[],plan_sha256=digest,retries=0,pins_unchanged=False)
    with common.abort_signals(abort):
        timer.start()
        try:
            results = Runner(options(kind,repo,out,ledger),cases_for(testcase,plan['cases']),sys.argv).run()
            terminal['results'] = [dict(asdict(x),artifact_dir=str(x.artifact_dir)) for x in results]
            metadata = read(out/'replay/run.json')
            common.check_stage(results,metadata,plan['cases'],abort)
            require(metadata['tests']==[c['id'] for c in plan['cases']] and metadata['jobs']==JOBS and
                    metadata['simv']==ledger['simv'] and metadata['commit_trace'] is True and
                    metadata['timeout_s'] is None and metadata['code_coverage'] is False,'Runner identity/coverage')
            require(read(out/'replay/summary.json')==terminal['results'],'Actual terminal summary')
            validate(plan,digest,out)
            evidence = {str(p):sha(p) for p in (out/'launch.json',out/'replay/run.json',out/'replay/summary.json')}
            for case in plan['cases']:
                root = out/'replay/tests'/case['id']
                for n in ('input.elf','inputs.json','command.json','console.log','work/run.vcs.log','commit_trace.csv',
                          'trace_summary.json','monitor_outcome.unvalidated.json','child_outcome.unvalidated.json',
                          'observer.command.json','observer.stdout','observer.wait.json','strict_original.json'):
                    evidence[str(root/n)] = sha(root/n)
            terminal.update(status=PASS,evidence_pins=evidence,pins_unchanged=True,source_cases=38,
                            linux_accepted=False,M7_accepted=False)
        except BaseException as e:
            abort.set();terminal['error']=f'{type(e).__name__}: {e}'
            if (out/'replay/summary.json').exists():
                terminal['results']=read(out/'replay/summary.json')
        finally:
            timer.cancel();timer.join()
            if time.monotonic()>=deadline:abort.set()
            engine._run_monitored,engine.FAIL_RE = original_monitor,old_fail
            terminal['finished']=time.time();common.publish(out,terminal,abort)
    print(terminal['status'],flush=True)
    return int(terminal['status']!=PASS)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['prepare','dryrun','run'])
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--plan-sha256')
    p.add_argument('--reserved-slots',type=int,default=0)
    p.add_argument('--authorize-run',action='store_true')
    a=p.parse_args();out=a.out.resolve()
    require(out.parent==HERE,'Owned fresh output only')
    env=common.base.shared.environment();os.environ.clear();os.environ.update(env)
    if a.mode=='prepare':prepare(out,a.reserved_slots);return 0
    if a.mode=='dryrun':
        plan=read(out/'plan.json');validate(plan,a.plan_sha256,out)
        require(not (out/'dryrun').exists(),'No repeated dryrun')
        ledger,repo,(parent,kind,testcase,_)=common.image_context(IMAGE)
        results=parent(options(kind,repo,out,ledger,True),cases_for(testcase,plan['cases']),sys.argv).run()
        require([r.name for r in results]==[c['id'] for c in plan['cases']] and all(r.status=='DRY_RUN' for r in results),'Exact10 dryrun')
        save(out/'dryrun_gate.json',dict(status='DRYRUN_ONLY_NO_DUT',plan_sha256=a.plan_sha256,jobs=JOBS,cases=10))
        print('DRYRUN10_PASS_NO_DUT');return 0
    require(a.authorize_run,'Explicit run switch required')
    return run(out,a.plan_sha256)


if __name__=='__main__':
    raise SystemExit(main())
