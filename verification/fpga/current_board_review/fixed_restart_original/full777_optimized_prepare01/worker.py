#!/usr/bin/env python3
"""Prepared single M8 run; independent pinned review required before execution."""
import argparse
from dataclasses import asdict
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
G=HERE.parents[1]
spec=importlib.util.spec_from_file_location('sealed_m8_recovery',G/'memory_candidate08_recovery19/worker.py')
m8=importlib.util.module_from_spec(spec);spec.loader.exec_module(m8)
import check
require,read,sha,save=m8.require,m8.read,m8.sha,m8.save
IMAGE_SHA='bd27bf6f7bb90b2b05c4546faaed8a8e32b8e545c182167fef72c170e40bdfd0'
UNIT='ara-fixed-full777-m8-01.service'
PLAN=HERE/'vcs_m8_prepared02'
OUTPUT=HERE/'vcs_m8_run01'


def case():
    ident='fixed_e8_m4_prefix777'
    e=read(HERE/'prepared01/soc/programs.json')['programs'][ident]
    return dict(id=ident,original_name=ident,elf=e['path'],sha256=e['sha256'],timeout_s=9000,pass_markers=e['pass_markers'])


def prepare():
    check.verify()
    bridge=read(HERE/'prepared01/reference01/bridge_setup02.json')
    require(bridge['calls']==777 and bridge['full_oracle_loads']==51282 and
            bridge['original_rng_stores']==1472 and bridge['mask_stores']==8758 and
            bridge['unknown_registers_assumed_zero'] is False,'Full reference setup bridge')
    ledger,repo,(parent,options,testcase,_)=m8.image_context(IMAGE_SHA)
    PLAN.mkdir(exist_ok=False)
    cmd=[sys.executable,str(HERE/'test_check.py')]
    save(PLAN/'host_invocation.json',dict(command=cmd))
    with (PLAN/'host.log').open('x') as log:
        child=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=60)
    save(PLAN/'host_exit.json',dict(returncode=child.returncode))
    require(child.returncode==0,'Focused checker negatives')
    c=case()
    opts=options(repo,PLAN/'dryrun','default',1,1,True,False,True,Path(ledger['simv']),True,None)
    rows=parent(opts,[testcase(c['id'],'app','',Path(c['elf']),c['original_name'],9000)],sys.argv).run()
    require(len(rows)==1 and rows[0].status=='DRY_RUN','Exactly one nonexecuted dryrun')
    pins=read(HERE/'prepared01/input_pins.json')
    pins.update(m8.m7.image_pins(m8.IMAGE,ledger,repo))
    for module in list(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if file and Path(file).is_file() and (Path(file).is_relative_to(G) or Path(file).is_relative_to(repo)):
            pins[str(Path(file).resolve())]=sha(Path(file))
    for root in (HERE/'prepared01/reference01',PLAN):
        pins.update({str(p):sha(p) for p in root.rglob('*') if p.is_file()})
    for name in ('check.py','test_check.py','worker.py','REVIEW.md'):
        pins[str(HERE/name)]=sha(HERE/name)
    monitor=repo/'hardware/tb/ara_commit_monitor.sv'
    rvfi=repo/'hardware/deps/cva6/core/cva6_rvfi.sv'
    plan=dict(status='PREPARED_REQUIRES_INDEPENDENT_REVIEW_NOT_RUN',case=c,pins=pins,jobs=1,retries=0,
              image=str(m8.IMAGE),image_sha256=IMAGE_SHA,configuration_sha256=ledger['configuration_sha256'],
              timeout_s=9000,checker_timeout_s=180,outer_s=10800,unit=UNIT,output=str(OUTPUT),
              monitor=str(monitor),rvfi=str(rvfi),no_build=True,original_Linux_replay=False,
              review_schema=dict(no_blocker=True,plan_sha256='EXACT_PLAN_SHA',reserved_slots=0))
    m8.m7.base.verify_pins(pins)
    save(PLAN/'plan.json',plan)
    save(PLAN/'READY.json',dict(status=plan['status'],plan_sha256=sha(PLAN/'plan.json'),pins=len(pins),
                              host_returncode=child.returncode,actual_DUT_runs=0))
    print(json.dumps(read(PLAN/'READY.json'),indent=2))


def run(approved,review_path,review_sha):
    require(sha(PLAN/'plan.json')==approved and review_path and sha(review_path)==review_sha,'Exact reviewed inputs')
    p=read(PLAN/'plan.json'); review=read(review_path)
    require(review.get('no_blocker') is True and review.get('plan_sha256')==approved,'Independent no-blocker required')
    reserved=review.get('reserved_slots')
    require(type(reserved) is int and 0<=reserved<=23,'Actual reserved capacity required')
    require(p['case']==case() and p['jobs']==1 and p['timeout_s']==9000 and p['outer_s']==10800,'Scope/budget drift')
    m8.m7.base.verify_pins(p['pins'])
    ledger,repo,(parent,options,testcase,_)=m8.image_context(IMAGE_SHA)
    owner=dict(line.split('=',1) for line in subprocess.check_output(['systemctl','--user','show',UNIT,
               '-p','MainPID','-p','ControlGroup','-p','KillMode','-p','Restart','-p','RuntimeMaxUSec'],text=True,timeout=15).splitlines())
    require(owner['MainPID']==str(os.getpid()) and owner['KillMode']=='control-group' and owner['Restart']=='no'
            and owner['RuntimeMaxUSec']=='3h' and Path('/proc/self/cgroup').read_text().strip()=='0::'+owner['ControlGroup'],
            'Direct bounded service owner')
    OUTPUT.mkdir(exist_ok=False)
    save(OUTPUT/'launch.json',dict(pid=os.getpid(),owner=owner,plan_sha256=approved,review_sha256=review_sha,
                                 admission=m8.m7.resources(OUTPUT,1,reserved),started=time.time()))
    import ara_verify.runner as engine
    original,old_re=engine._run_monitored,engine.FAIL_RE
    abort=threading.Event();start=time.monotonic()
    result=dict(status='NOT_PASS',aborted=False,retries=0,pins_unchanged=False,firstfailure=None,
                plan_sha256=approved,image_sha256=IMAGE_SHA,results=[])
    def monitored(command,cwd,console,timeout_s,cancel_event=None):
        rc,elapsed,timed_out,failed=original(command,cwd,console,timeout_s,cancel_event)
        save(Path(console).parent/'child_exit.json',dict(returncode=rc,elapsed_s=elapsed,timed_out=timed_out,
            failure_seen=failed,abort_set=bool(cancel_event and cancel_event.is_set()),command=list(map(str,command)),cwd=str(cwd)))
        return rc,elapsed,timed_out,failed
    engine._run_monitored=monitored
    engine.FAIL_RE=re.compile(old_re.pattern+'|RVV_MATRIX_FAIL|RVV_MATRIX_FAILED|FIXED_.*FAIL',old_re.flags)
    class Runner(parent):
        def __init__(self,*args):super().__init__(*args);self.cancel_event=abort
    with m8.m7.abort_signals(abort):
        try:
            c=p['case'];opts=options(repo,OUTPUT/'replay','default',1,1,False,False,True,Path(ledger['simv']),True,None)
            rows=Runner(opts,[testcase(c['id'],'app','',Path(c['elf']),c['original_name'],9000)],sys.argv).run()
            result['results']=[dict(asdict(r),artifact_dir=str(r.artifact_dir)) for r in rows]
            require(len(rows)==1,'One result required')
            r=rows[0];root=r.artifact_dir
            m8.check_receipt(read(root/'child_exit.json'),9000)
            require(r.status=='PASS' and type(r.returncode) is int and r.returncode==0 and not abort.is_set(),'Actual runner outcome')
            m8.m7.check_artifacts(r,c,ledger)
            cmd=[sys.executable,str(HERE/'check.py'),'csv','--csv',str(root/'commit_trace.csv'),'--out',str(root/'full777.json')]
            save(root/'checker_invocation.json',dict(command=cmd))
            with (root/'checker.log').open('x') as log:
                child=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=180)
            save(root/'checker_exit.json',dict(returncode=child.returncode))
            require(child.returncode==0 and not abort.is_set(),'Independent full CSV check/abort')
            m8.m7.base.verify_pins(p['pins']);m8.image_context(IMAGE_SHA)
            require(time.monotonic()-start<10500,'Whole run deadline')
            result.update(status='PASS_CONTINUOUS_FULL777_M8',pins_unchanged=True,
                          checker=read(root/'full777.json'),evidence_pins={str(f):sha(f) for f in OUTPUT.rglob('*') if f.is_file()})
        except BaseException as error:
            abort.set();result['firstfailure']=f'{type(error).__name__}: {error}'
        finally:
            engine._run_monitored,engine.FAIL_RE=original,old_re
            blocked=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
            try:
                result['aborted']=abort.is_set() or bool(signal.sigpending() & {signal.SIGINT,signal.SIGTERM})
                if result['aborted']:result['status']='NOT_PASS'
                result['elapsed_s']=time.monotonic()-start
                save(OUTPUT/'complete.json',result)
            finally:signal.pthread_sigmask(signal.SIG_SETMASK,blocked)
    print(result['status'],flush=True)
    return int(result['status']!='PASS_CONTINUOUS_FULL777_M8')


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['prepare','run']);a.add_argument('--plan-sha256')
    a.add_argument('--review',type=Path);a.add_argument('--review-sha256');args=a.parse_args()
    require(sys.flags.optimize==0,'Python assertions must remain enabled')
    if args.action=='prepare':prepare()
    else:raise SystemExit(run(args.plan_sha256,args.review,args.review_sha256))
