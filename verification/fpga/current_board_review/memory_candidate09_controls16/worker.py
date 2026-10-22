"""M9 exact M8 controls16 only; immutable software/checks, jobs1, no rebuild."""
import argparse
from dataclasses import asdict
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
G=HERE.parent
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);sys.modules[name]=value;spec.loader.exec_module(value)
    return value
M7=G/'memory_candidate07_controls16/regression.py'
m7=module('m9_original_controls_checks',M7)
TERMINAL=G/'arithmetic_restart_original/macc_disjoint482/full482_optimized_prepare01/vcs_m8_plan03/terminal_publish.py'
terminal=module('m9_reviewed_terminal',TERMINAL)
read,sha,require=m7.read,m7.sha,m7.require
OLD=G/'memory_candidate08_recovery19/prepared01'
IMAGE=Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/campaign/image')
IMAGE_SHA='48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a'
UNIT='ara-m9-controls16-01.service'
PASS='PASS_M9_CONTROLS16_ARCHITECTURAL'
BASE_PINS={
 str(OLD/'plan.json'):'62f4e876969ab8389c43171917ee85c4c3e2b0fc4c86a4c7423ee926578b58fa',
 str(OLD/'complete.json'):'d096580fe824af503900c77e972c8facb5aca984bce65f483fdc569d702fe2a5',
 str(M7):'86c98586450af79929ff9fe6d8dadf131dd912997c1079e053dde9e384ed2a6c',
 str(TERMINAL):'495a2f91dde233c040eea231531d414b734184100b7c33a88dda98b6070ec718',
}


def save(path,data):
    with path.open('x') as f:
        json.dump(data,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())


def scope():
    m7.base.verify_pins(BASE_PINS)
    p,t=read(OLD/'plan.json'),read(OLD/'complete.json')
    require(t['status']=='PASS_M8_RECOVERY3_CONTROLS16_RESIDENT1' and
            t['aborted'] is False and t['pins_unchanged'] is True and t['retries']==0,'M8 baseline acceptance')
    cases=[];pins=dict(BASE_PINS)
    for source in p['cases']:
        if source['kind']!='control':continue
        c=dict(source,stage='controls16')
        r=next(x for x in t['results'] if x['name']==c['id'])
        require(r['status']=='PASS' and type(r['returncode']) is int and r['returncode']==0 and
                c['timeout_s']==180,'Exact accepted M8 control and budget')
        root=Path(r['artifact_dir'])
        require(root==OLD/'regression19/tests'/c['id'],'Actual M8 baseline path')
        c['baseline_csv']=str(root/'commit_trace.csv')
        for name in ('commit_trace.csv','input.elf','command.json','inputs.json','console.log',
                     'work/run.vcs.log','trace_summary.json','child_exit.json','performance.json'):
            path=root/name
            require(str(path) in t['evidence_pins'],'Baseline evidence membership')
            pins[str(path)]=t['evidence_pins'][str(path)]
        pins[c['elf']]=c['sha256']
        require(sha(root/'input.elf')==c['sha256'],'Same actual private M8 ELF')
        cases.append(c)
    require(len(cases)==len({c['id'] for c in cases})==16 and
            sum(t['performance'][c['id']]['rows'] for c in cases)==310350,'Exact16/full310350')
    return cases,pins


def image_context():
    require(sha(IMAGE/'image.json')==IMAGE_SHA,'Exact M9 image')
    m7.base.IMAGE=IMAGE
    ledger,repo,framework=m7.base.image_context()
    require(ledger['configuration_sha256']==m7.CONFIGURATION_SHA,'Same config/AXI delay')
    build=read(IMAGE.parents[1]/'BUILD_ACCEPTED.json')
    require(build['status']=='BUILD_ONLY_NOT_DUT_PASS' and build['sources']==539 and build['compiled']==453 and
            build['image_sha256']==IMAGE_SHA and build['snapshot_sha256']==ledger['snapshot_sha256'] and
            build['approved_source_sha256']=={'hardware/src/vlsu/addrgen.sv':
                '3736b64136ebbf5629dadb0037457279f9bb91307356c468c9677d321c8c51c5'},'M9 build contract')
    return ledger,repo,framework


def validate(out,digest):
    require(sha(out/'plan.json')==digest,'Disk plan drift')
    p=read(out/'plan.json');cases,_=scope()
    require(p['cases']==cases and p['jobs']==1 and p['unit']==UNIT and p['service_s']==3600 and
            p['worker_s']==3300 and p['image_sha256']==IMAGE_SHA and p['reserved_slots']==0 and
            p['no_build'] is True and p['retries']==0,'Exact run contract')
    m7.base.verify_pins(p['pins'])
    return p


def prepare(out):
    require(not out.exists(),'Fresh independent directory')
    host=read(HERE/'host01.json')
    require(host['status']=='PASS_HOST_ONLY' and host['returncode']==0 and
            host['worker_sha256']==sha(Path(__file__)),'Focused Host binding')
    cases,pins=scope()
    ledger,repo,_=image_context();pins.update(m7.image_pins(IMAGE,ledger,repo))
    for path in (Path(__file__),HERE/'test_host.py',HERE/'host01.json',Path(m7.base.__file__),
                 Path(m7.base.shared.__file__),G/'integration/prepare.py',IMAGE.parents[1]/'BUILD_ACCEPTED.json',
                 G/'memory_candidate09_build/BUILD_HANDOFF01.md'):
        pins[str(path.resolve())]=sha(path)
    m7.base.verify_pins(pins);out.mkdir()
    save(out/'plan.json',dict(status='PREPARED_NOT_RUN',cases=cases,pins=pins,jobs=1,unit=UNIT,
        service_s=3600,worker_s=3300,reserved_slots=0,image=str(IMAGE),image_sha256=IMAGE_SHA,
        baseline_rows=310350,no_build=True,retries=0,no_software_change=True))
    print('PREPARED',sha(out/'plan.json'),flush=True)


def numeric(receipt):
    require(type(receipt['returncode']) is int and receipt['returncode']==0 and
            receipt['timed_out'] is False and receipt['failure_seen'] is False and
            0<=receipt['elapsed_s']<=180,'Actual numeric child0/budget/no failure')


def execute(out,digest,dry=False):
    p=validate(out,digest)
    ledger,repo,(parent,options,testcase,_)=image_context()
    cases=p['cases'];entries={c['id']:c for c in cases}
    abort=terminal.TerminalAbort()
    import ara_verify.runner as engine
    original,old_re=engine._run_monitored,engine.FAIL_RE
    def monitored(command,cwd,console,timeout,cancel_event=None):
        result=original(command,cwd,console,timeout,cancel_event)
        rc,elapsed,timed_out,failure=result
        receipt=dict(returncode=rc,elapsed_s=elapsed,timed_out=timed_out,failure_seen=failure,
                     command=list(map(str,command)),cwd=str(cwd))
        save(Path(console).parent/'child_exit.json',receipt)
        try:numeric(receipt)
        except BaseException:abort.set();raise
        return result
    controls={c['id']:dict(baseline_csv=c['baseline_csv']) for c in cases}
    def admit(name):
        require(not abort.is_set() and sha(Path(entries[name]['elf']))==entries[name]['sha256'],'Dispatch abort/ELF')
        save(out/'admission'/(name+'.json'),m7.resources(out,1,0))
    runner_cls=parent if dry else m7.checked_runner(parent,entries,ledger,abort,admit,controls)
    opts=options(repo,out/('dryrun' if dry else 'controls16'),'default',1,1,dry,False,True,
                 Path(ledger['simv']),True,None)
    tests=[testcase(c['id'],'app','',Path(c['elf']),c['original_name'],180) for c in cases]
    if dry:
        require(not(out/'dryrun').exists(),'One dryrun')
        results=runner_cls(opts,tests,sys.argv).run()
        require(len(results)==16 and all(r.status=='DRY_RUN' and r.returncode is None for r in results),'Dryrun16')
        validate(out,digest);save(out/'dryrun_gate.json',dict(status='DRYRUN_ONLY_NO_DUT',plan_sha256=digest,cases=16))
        return 0
    require(not(out/'controls16').exists() and read(out/'dryrun_gate.json')['plan_sha256']==digest,'Once-only after dryrun')
    env=dict(os.environ,XDG_RUNTIME_DIR='/run/user/'+str(os.getuid()),
             DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/'+str(os.getuid())+'/bus')
    q=subprocess.run(['systemctl','--user','show',UNIT,'--property=MainPID,ControlGroup,KillMode,Restart,RuntimeMaxUSec'],
                     env=env,text=True,capture_output=True,timeout=15);q.check_returncode()
    owner=dict(x.split('=',1) for x in q.stdout.splitlines())
    require(owner['MainPID']==str(os.getpid()) and owner['KillMode']=='control-group' and owner['Restart']=='no' and
            owner['RuntimeMaxUSec']=='1h' and Path('/proc/self/cgroup').read_text().strip()=='0::'+owner['ControlGroup'],
            'Direct bounded unit owner')
    save(out/'launch.json',dict(owner=owner,plan_sha256=digest,admission=m7.resources(out,1,0)))
    (out/'admission').mkdir()
    result=dict(status='NOT_PASS',plan_sha256=digest,results=[],retries=0,pins_unchanged=False)
    expires=time.monotonic()+3300
    timer=threading.Timer(3300,abort.set);timer.daemon=True
    engine._run_monitored=monitored;engine.FAIL_RE=re.compile(old_re.pattern+'|'+m7.BAD.pattern,old_re.flags)
    with m7.abort_signals(abort):
        timer.start()
        try:
            results=runner_cls(opts,tests,sys.argv).run()
            result['results']=[dict(asdict(r),artifact_dir=str(r.artifact_dir)) for r in results]
            m7.check_stage(results,read(out/'controls16/run.json'),cases,abort)
            require(read(out/'controls16/summary.json')==result['results'],'Actual summary membership')
            performance={}
            for c in cases:
                root=out/'controls16/tests'/c['id']
                numeric(read(root/'child_exit.json'));performance[c['id']]=read(root/'performance.json')
            require(sum(v['rows'] for v in performance.values())==310350,'Full310350 event comparison')
            validate(out,digest);image_context()
            result.update(status=PASS,pins_unchanged=True,performance=performance,
                compared_rows=310350,cycle_changed_rows=sum(v['cycle_changed_rows'] for v in performance.values()),
                performance_status='REVIEW_CYCLE_DIFFERENCES' if any(v['cycle_changed_rows'] for v in performance.values())
                    else 'EXACT_M8_CONTROLS16_ALL_CYCLES',
                evidence_pins={str(f):sha(f) for f in (out/'controls16').rglob('*') if f.is_file()})
        except BaseException as error:
            abort.set();result['firstfailure']=repr(error)
        finally:
            timer.cancel();timer.join();engine._run_monitored,engine.FAIL_RE=original,old_re
            result['finished']=time.time()
            terminal.publish(out,result,abort,expires)
    print(result['status'],result.get('performance_status',''),flush=True)
    return int(result['status']!=PASS)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','dryrun','run'])
    p.add_argument('--out',type=Path,default=HERE/'prepared01');p.add_argument('--plan-sha256')
    a=p.parse_args();require(a.out.resolve().parent==HERE,'Owned independent output')
    env=m7.base.shared.environment()
    env.update(XDG_RUNTIME_DIR='/run/user/'+str(os.getuid()),DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/'+str(os.getuid())+'/bus')
    os.environ.clear();os.environ.update(env)
    if a.mode=='prepare':prepare(a.out)
    else:raise SystemExit(execute(a.out,a.plan_sha256,a.mode=='dryrun'))
