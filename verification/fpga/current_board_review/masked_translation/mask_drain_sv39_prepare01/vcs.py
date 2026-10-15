#!/usr/bin/env python3
"""M7 single-case adapter; reuse frozen runner and accepted M7 admission."""
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
spec=importlib.util.spec_from_file_location('m7_controls',HERE.parents[1]/'memory_candidate07_controls16/regression.py')
m7=importlib.util.module_from_spec(spec);spec.loader.exec_module(m7)
import dut_check
require,read,sha=m7.require,m7.read,m7.sha


def save(p,v):
    with p.open('x') as f:
        json.dump(v,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())


def prepare(member):
    ref=HERE/('reference_'+member+'01');ready=read(ref/'READY.json')
    require(ready['status']=='HOST_SPIKE_PASS_NOT_DUT' and ready['member']==member,'Reference scope')
    require(read(ref/'reference_exit.json')['returncode']==0 and read(ref/'status.json')['checks']==914,'Reference not complete')
    pins=dict(ready['input_pins']);pins.update({str(ref/p):h for p,h in ready['outputs'].items()})
    ledger,repo,_=m7.image_context(m7.M7);pins.update(m7.image_pins(m7.M7,ledger,repo))
    for p in (ref/'READY.json',Path(__file__),Path(dut_check.__file__),Path(m7.__file__),
              Path(m7.base.__file__),Path(m7.base.shared.__file__),HERE/'host_dut_check01.json'):
        pins[str(p)]=sha(p)
    host=read(HERE/'host_dut_check01.json')
    require(host['passed'] is True and host['checker_sha256']==sha(Path(dut_check.__file__)) and
            host['worker_sha256']==sha(Path(__file__)),'Host gate')
    m7.base.verify_pins(pins)
    out=HERE/('vcs_m7_'+member+'01');out.mkdir(exist_ok=False)
    case=dict(id=ready['runtime_name'],original_name=ready['runtime_name'],elf=str(ref/'soc.elf'),
              sha256=ready['outputs']['soc.elf'],timeout_s=3600,pass_markers=['MASK_DRAIN_SV39_PASS'])
    plan=dict(member=member,case=case,pins=pins,reference=str(ref),image=str(m7.M7),
              unit='ara-mask-drain-'+member+'-m7-01.service',outer_s=4200,reserved_slots=1,
              no_build=True,no_retry=True,scope='New e64 VL9 real Sv39 drain boundary, not original16 root')
    save(out/'plan.json',plan);print(str(out)+' '+sha(out/'plan.json'),flush=True)


def monitor_wrapper(original):
    def monitored(command,cwd,console_path,timeout_s,cancel_event=None):
        result=original(command,cwd,console_path,timeout_s,cancel_event)
        rc,elapsed,timed_out,failure_seen=result
        save(Path(console_path).parent/'child_exit.json',dict(returncode=rc,elapsed_s=elapsed,
             timed_out=timed_out,failure_seen=failure_seen,abort_set=bool(cancel_event and cancel_event.is_set()),
             command=list(map(str,command)),cwd=str(cwd),architectural_acceptance=False))
        return result
    return monitored


def run(out,approved):
    require(sha(out/'plan.json')==approved,'Plan SHA drift');p=read(out/'plan.json')
    m7.base.verify_pins(p['pins'])
    ledger,repo,(parent,opts_type,testcase,_)=m7.image_context(m7.M7)
    owner=dict(x.split('=',1) for x in subprocess.check_output(['systemctl','--user','show',p['unit'],
        '-p','MainPID','-p','ControlGroup','-p','KillMode','-p','Restart','-p','RuntimeMaxUSec'],text=True,timeout=15).splitlines())
    require(owner['MainPID']==str(os.getpid()) and owner['KillMode']=='control-group' and owner['Restart']=='no'
            and owner['RuntimeMaxUSec']=='1h 10min' and Path('/proc/self/cgroup').read_text().strip()=='0::'+owner['ControlGroup'],
            'Direct bounded service ownership')
    admission=m7.resources(out,1,p['reserved_slots'])
    save(out/'launch.json',dict(pid=os.getpid(),owner=owner,admission=admission,plan_sha256=approved,started=time.time()))
    abort=threading.Event();started=time.monotonic();terminal=dict(status='NOT_PASS',results=[],aborted=False,pins_unchanged=False,retries=0)
    import ara_verify.runner as engine
    original=engine._run_monitored;original_re=engine.FAIL_RE
    engine._run_monitored=monitor_wrapper(original)
    engine.FAIL_RE=re.compile(original_re.pattern+'|MASK_DRAIN_SV39_FAIL',original_re.flags)
    class Runner(parent):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.cancel_event=abort
    with m7.abort_signals(abort):
        try:
            c=p['case'];opts=opts_type(repo,out/'run','default',1,1,False,False,True,Path(ledger['simv']),True,None)
            results=Runner(opts,[testcase(c['id'],'app','',Path(c['elf']),c['id'],c['timeout_s'])],sys.argv).run()
            terminal['results']=[dict(asdict(r),artifact_dir=str(r.artifact_dir)) for r in results]
            require(len(results)==1,'Incomplete membership');r=results[0];root=r.artifact_dir
            receipt=read(root/'child_exit.json')
            require(type(receipt['returncode']) is int and receipt['returncode']==0 and not any(
                receipt[k] for k in ('timed_out','failure_seen','abort_set')),'Actual child outcome not accepted')
            require(r.status=='PASS' and type(r.returncode) is int and r.returncode==0 and not abort.is_set(),'Runner failed/aborted')
            m7.check_artifacts(r,c,ledger)
            require('MASK_DRAIN_SV39_FAIL' not in (root/'console.log').read_text(),'Software fail')
            result=dut_check.analyze(root/'commit_trace.csv',read(Path(p['reference'])/'soc.symbols.json'),int(p['member']=='store'))
            save(out/'csv.json',result)
            m7.base.verify_pins(p['pins']);m7.image_context(m7.M7)
            require(not abort.is_set() and time.monotonic()-started<4100,'Abort/deadline before acceptance')
            evidence={str(f):sha(f) for f in root.rglob('*') if f.is_file() and f.suffix not in ('.vpd','.fsdb')}
            terminal.update(status='M7_MASK_DRAIN_'+p['member'].upper()+'_PASS',pins_unchanged=True,
                            csv=result,evidence_pins=evidence,plan_sha256=approved)
        except BaseException as e:
            abort.set();terminal['error']=f'{type(e).__name__}: {e}'
        finally:
            engine._run_monitored=original;engine.FAIL_RE=original_re
            # The exclusive terminal publication is the acceptance boundary.
            prior=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
            try:
                terminal['aborted']=abort.is_set() or bool(signal.sigpending()&{signal.SIGINT,signal.SIGTERM})
                if terminal['aborted']:terminal['status']='NOT_PASS'
                terminal['finished']=time.time();save(out/'complete.json',terminal)
            finally:signal.pthread_sigmask(signal.SIG_SETMASK,prior)
    print(terminal['status'],flush=True)
    return int(terminal['status']=='NOT_PASS')


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('mode',choices=['prepare','run']);a.add_argument('member',choices=['load','store'])
    a.add_argument('--plan-sha256');args=a.parse_args()
    env=m7.base.shared.environment();env.update(XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}',DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
    os.environ.clear();os.environ.update(env)
    if args.mode=='prepare':prepare(args.member)
    else:sys.exit(run(HERE/('vcs_m7_'+args.member+'01'),args.plan_sha256))
