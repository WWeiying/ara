#!/usr/bin/env python3
"""Serial baseline RVV activity collector, Q8-priority, immutable case admission."""
import argparse
from contextlib import contextmanager
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
GATE = OUT/'power_gate_build_20261117_baseline_02'
DEFAULT = OUT/'power_gls_20261117_baseline_rvv_activity_01'
COMMON_SHA = 'e05b5a5b23a5ca3ade67aebd10843029b5e1012745210fb1d87678ae43f37f5d'


def load(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


g=load(HERE/'gate_run.py','rvv_shared_gate_primitives')
g.require(g.sha(HERE/'gate_run.py')==COMMON_SHA,'Sealed common scheduler drift')
eof=load(HERE/'audit_gate_capture_eof.py','rvv_native_eof')
require,sha,read,save,verify=g.require,g.sha,g.read,g.save,g.verify


def validate_window(first,last):
    require(type(first) is int and type(last) is int and 0<first<last and 2<=last-first<=32768,
            'Complete loop/tile must fit bounded 32768-cycle capture')


def capacity(rows,own=None):
    actual=[pid for pid,(_,args) in rows.items() if pid!=own and Path(args[0]).name=='simv']
    reserved=g.reserved_slots(rows,own_child=own)
    return dict(actual_other_simv=sorted(actual),reserved_other_slots=reserved,
                launch_allowed=reserved<4 and len(actual)<4)


@contextmanager
def shared_launch_locks():
    # Same order as the existing GLS successors; never a private third lock.
    with g.slot_lock():
        with (OUT/'.power-vcs-slots-20261117.lock').open('a') as stream:
            fcntl.flock(stream,fcntl.LOCK_EX)
            try:yield
            finally:fcntl.flock(stream,fcntl.LOCK_UN)


def q8_units():
    proc=subprocess.run(['systemctl','--user','list-units','--type=service',
        '--state=active,activating,deactivating','--plain','--no-legend','--no-pager','power-*q8*.service'],
        capture_output=True,text=True,check=True,timeout=30)
    return [line.split()[0] for line in proc.stdout.splitlines() if line.strip()]


def prepare(out):
    require(out.parent==OUT and out.name.startswith('power_gls_20261117_baseline_rvv_activity_') and
            not out.exists(),'Fresh owned collector output required')
    build=read(GATE/'build.json')
    require(build['state']=='RECONSTRUCTED_BASELINE_GATE_BUILT_NOT_SIMULATED','Existing baseline gate image required')
    verify(build['image_pins'])
    verify(read(GATE/'source-pins.json'))
    context=build['baseline_context']
    require(context['historical_byte_identity']=='UNPROVEN' and context['source_reconstructed'] is True,
            'Do not invent historical baseline byte identity')
    receipt=read(GATE/'gate-receipt.json')
    require(receipt['memory']['bytes']==1048576 and len(receipt['memory']['instances'])==8 and
            receipt['baseline_context']==context,'Gate memory/context mismatch')
    simv=GATE/'sim/simv'
    smoke=OUT/'power_gls_20261117_baseline_q8_smoke_03/result.json'
    warm=read(smoke)
    require(warm['state']=='GATE_SMOKE_PASS' and warm['full_gate_task_pass'] is True and
            warm['simv_sha256']==build['image_pins'][str(simv)],'Common-image Q8 smoke prerequisite')
    verify(warm['checked_artifacts'])
    out.mkdir()
    (out/'inputs').mkdir()
    pins={str(smoke):sha(smoke),str(GATE/'build.json'):sha(GATE/'build.json'),
          str(GATE/'source-pins.json'):sha(GATE/'source-pins.json')}
    for name in ('gate_rvv_activity.py','test_gate_rvv_activity.py','gate_run.py','audit_gate_capture_eof.py'):
        src,dst=HERE/name,out/'inputs'/name
        shutil.copyfile(src,dst)
        pins[str(src)]=sha(src)
        pins[str(dst)]=sha(dst)
    with (out/'host-tests.log').open('x') as log:
        subprocess.run([sys.executable,'-B',str(out/'inputs/test_gate_rvv_activity.py'),'-v'],
            stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    pins[str(out/'host-tests.log')]=sha(out/'host-tests.log')
    pins.update(build['image_pins'])
    cases=[]
    # Attention has already passed offline finite/tolerance/protocol checks before queue creation.
    for kind in ('m1','m4','attention'):
        admission=OUT/('power_rvv_activity_audit_20261117_'+kind+'_01')
        audit=read(admission/'result.json')
        require(audit['state']=='POWER_ELIGIBLE' and audit['kind']==kind and
                audit['strict_numerical_state']=='FAIL' and audit['traffic_protocol_checked'] is True and
                audit['original_worker_reclassified'] is False,'Scoped RTL power eligibility required')
        verify(read(admission/'source-pins.json'))
        verify(audit['artifacts'])
        window=audit['work']['window']
        first,last=window['first_cycle'],window['last_cycle']
        validate_window(first,last)
        case=out/'cases'/kind
        (case/'inputs').mkdir(parents=True)
        (case/'run').mkdir()
        private=case/'inputs/program.elf'
        shutil.copyfile(audit['elf'],private)
        require(sha(private)==audit['elf_sha256'],'Exact prechecked ELF copy required')
        rtl_plan=case/'inputs/rtl-plan.json'
        shutil.copyfile(GATE/'inputs/rtl-plan.json',rtl_plan)
        argv=[str(simv),'-no_save','-l',str(case/'run/run.vcs.log'),'+PRELOAD='+str(private),
            '+TESTCASE=rvv_activity_'+kind,'+NO_FSDB','+NO_INSTR_TRACE',
            '+GATE_MAX_CYCLES='+str(last+8192),'+GATE_VCD='+str(case/'run/window.vcd'),
            '+GATE_ROI_FIRST='+str(first),'+GATE_ROI_LAST='+str(last),'+GATE_STOP_AFTER_CAPTURE']
        plan=dict(kind=kind,mode='capture',command=argv,cwd=str(case/'run'),image=str(GATE),
            elf=str(private),elf_sha256=audit['elf_sha256'],first_cycle=first,last_cycle=last,
            max_cycles=last+8192,wall_seconds=14400,slot_seconds=14400,
            max_vcd_bytes=32*1024**3,max_log_bytes=256*1024**2,window_basis=window,
            rtl_admission=str(admission/'result.json'),rtl_admission_sha256=sha(admission/'result.json'),
            strict_original_state='FAIL',same_elf_gate_smoke_checked=False,
            gate_phase_checked=False,task_pass=False,power_acceptance=False)
        save(case/'plan.json',plan,True)
        for p in (admission/'result.json',admission/'source-pins.json',private,Path(audit['elf']),rtl_plan,
                  GATE/'inputs/rtl-plan.json',case/'plan.json'):
            pins[str(p)]=sha(p)
        cases.append(dict(kind=kind,path=str(case),plan_sha256=sha(case/'plan.json')))
    save(out/'image-binding.json',dict(state='IMAGE_BOUND_ACTIVITY_ONLY',baseline_context=context,
        simv_sha256=build['image_pins'][str(simv)],image_pins=build['image_pins'],
        gate_build_sha256=sha(GATE/'build.json'),gate_source_pins_sha256=sha(GATE/'source-pins.json'),
        rtl_power_eligibility_only=True,original_strict_failures_preserved=True,
        old_q8_original_PASS_release_not_reclassified=True),True)
    save(out/'plan.json',dict(schema='rvv-three-case-serial-gate-activity-v1',cases=cases,
        baseline_context=context,priority='All active Q8 services finish before each dispatch',
        scheduler='Existing canonical GLS lock then v3 interop lock; physical running watchdog',
        max_concurrent_simulators=4,own_parallelism=1,priority_wait_seconds=21600,
        automatic_retry=False,stop_after_first_failure=True,
        scope='Activity only; retained strict FAILs, no new compilation/RTL/synthesis/SAIF/DC; gate phase pending'),True)
    for p in (out/'plan.json',out/'image-binding.json'):
        pins[str(p)]=sha(p)
    verify(pins)
    save(out/'source-pins.json',pins,True)
    save(out/'status.json',dict(state='IMAGE_BOUND_NOT_LAUNCHED',simulations_started=0))
    unit=out.name.replace('_','-')+'.service'
    worker=['/usr/bin/python3','-B',str(out/'inputs/gate_rvv_activity.py'),'execute','--output',str(out),
            '--plan-sha256',sha(out/'plan.json'),'--authorize-capture']
    service=['systemd-run','--user','--unit='+unit,'--property=Type=exec','--property=KillMode=control-group',
        '--property=RuntimeMaxSec=86400','--property=TimeoutStopSec=45',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),*worker]
    save(out/'ready-command.json',dict(service=service,unit=unit,launched=False),True)


def run_capture(root,case,plan,pins):
    work=case/'run'
    started_wait=time.monotonic()
    proc=None
    while proc is None:
        with shared_launch_locks():
            snapshot=capacity(g.process_snapshot())
            priority=q8_units()
            if snapshot['launch_allowed'] and not priority:
                verify(pins)
                started_ns=time.time_ns()
                def limits():
                    resource.setrlimit(resource.RLIMIT_FSIZE,(plan['max_vcd_bytes'],plan['max_vcd_bytes']))
                with (work/'console.log').open('x') as log:
                    proc=subprocess.Popen(plan['command'],cwd=work,
                        env=dict(read(case/'inputs/rtl-plan.json')['environment'],PYTHONDONTWRITEBYTECODE='1'),
                        stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=limits)
                save(case/'dispatch.json',dict(pid=proc.pid,owner_pid=os.getpid(),started_ns=started_ns,
                    command=plan['command'],shared_capacity=snapshot,q8_priority_services=priority),True)
        if proc is None:
            require(time.monotonic()-started_wait<plan['slot_seconds'],'Finite shared-slot wait exhausted')
            save(root/'status.json',dict(state='WAITING_SHARED_SLOT_OR_Q8_PRIORITY',case=plan['kind'],
                capacity=snapshot,q8_services=priority,simulations_started=False))
            time.sleep(30)
    start,last_status=time.monotonic(),0
    try:
        while proc.poll() is None:
            elapsed=time.monotonic()-start
            require(elapsed<plan['wall_seconds'],'Finite gate wall watchdog expired')
            for file,limit in ((work/'window.vcd',plan['max_vcd_bytes']),
                               (work/'console.log',plan['max_log_bytes']),
                               (work/'run.vcs.log',plan['max_log_bytes'])):
                require(not file.exists() or file.stat().st_size<=limit,'Bounded activity artifact limit')
            snapshot=capacity(g.process_snapshot(),own=proc.pid)
            # Unknown future dispatchers block admission, never masquerade as four running children.
            require(len(snapshot['actual_other_simv'])<4,'Actual simultaneous simulator capacity exceeded')
            if elapsed-last_status>=30 or last_status==0:
                state=dict(state='GLS_RUNNING',case=plan['kind'],owner_pid=os.getpid(),child_pid=proc.pid,
                    elapsed_seconds=elapsed,child_cpu_seconds=g.cpu_seconds(proc.pid),
                    vcd_bytes=(work/'window.vcd').stat().st_size if (work/'window.vcd').exists() else 0,
                    **g.last_progress(work/'run.vcs.log'))
                save(root/'status.json',state)
                save(case/'status.json',state)
                with (case/'progress.jsonl').open('a') as stream:stream.write(json.dumps(state)+'\n')
                last_status=elapsed
            try:proc.wait(timeout=2)
            except subprocess.TimeoutExpired:pass
        return dict(returncode=proc.returncode,started_ns=started_ns,finished_ns=time.time_ns(),
                    elapsed_seconds=time.monotonic()-start)
    finally:g.stop_process(proc)


def finish_capture(case,plan,binding,run):
    require(run['returncode']==0,'Gate process failure')
    work=case/'run'
    text=(work/'run.vcs.log').read_text()
    g.clean_log(text)
    g.clean_log((work/'console.log').read_text())
    first,last=g.capture_markers(text,plan['first_cycle'],plan['last_cycle'])
    require(re.search(r'\$finish at simulation time\s+'+str(last)+r'\s*$',text,re.M) and
            'Core Test' not in text,'Capture must stop at selected window, not claim task completion')
    vcd=work/'window.vcd'
    stat=vcd.stat()
    require(0<stat.st_size<=plan['max_vcd_bytes'] and run['started_ns']<=stat.st_mtime_ns<=run['finished_ns']+2*10**9,
            'Owned VCD timestamp/size provenance')
    evidence=eof.inspect_vcd(vcd,first,last,plan['last_cycle']-plan['first_cycle'])
    return dict(state='CAPTURE_COMPLETE_NOT_TASK_PASS',kind=plan['kind'],vcd=str(vcd),vcd_sha256=sha(vcd),
        log_sha256=sha(work/'run.vcs.log'),elf_sha256=plan['elf_sha256'],simv_sha256=binding['simv_sha256'],
        baseline_context=binding['baseline_context'],rtl_admission=plan['rtl_admission'],
        strict_original_state='FAIL',full_gate_task_pass=False,gate_numeric_checked=False,
        gate_phase_checked=False,power_acceptance=False,power_publishable=False,
        window_basis=plan['window_basis'],vcd_evidence=evidence,**run)


def execute(out,plan_sha,authorize):
    require(authorize and Path(__file__).resolve()==out/'inputs/gate_rvv_activity.py' and
            not (out/'attempt.json').exists(),'Authorized frozen one-shot collector required')
    unit=out.name.replace('_','-')+'.service'
    pid=subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','--value'],text=True).strip()
    require(pid==str(os.getpid()) and '/'+unit in Path('/proc/self/cgroup').read_text(),'Direct service ownership required')
    require(sha(out/'plan.json')==plan_sha,'Plan identity')
    pins=read(out/'source-pins.json')
    verify(pins)
    binding=read(out/'image-binding.json')
    require(binding['baseline_context']==read(GATE/'build.json')['baseline_context'],'Gate context binding')
    verify(binding['image_pins'])
    plan=read(out/'plan.json')
    save(out/'attempt.json',dict(pid=os.getpid(),started=time.time(),plan_sha256=plan_sha),True)
    def interrupted(signum,frame):raise InterruptedError('Owned collector interrupted '+str(signum))
    signal.signal(signal.SIGTERM,interrupted)
    signal.signal(signal.SIGINT,interrupted)
    results=[]
    try:
        deadline=time.monotonic()+plan['priority_wait_seconds']
        while busy:=q8_units():
            require(time.monotonic()<deadline,'Finite Q8-priority wait expired')
            save(out/'status.json',dict(state='WAITING_FOR_Q8_PRIORITY',services=busy,
                pid=os.getpid(),simulations_started=0))
            time.sleep(60)
        for entry in plan['cases']:
            case=Path(entry['path'])
            require(sha(case/'plan.json')==entry['plan_sha256'],'Case plan drift')
            verify(pins)
            verify(binding['image_pins'])
            capture=read(case/'plan.json')
            run=run_capture(out,case,capture,pins)
            result=finish_capture(case,capture,binding,run)
            verify(pins)
            verify(binding['image_pins'])
            save(case/'result.json',result,True)
            results.append(result)
        result=dict(state='THREE_ACTIVITY_WINDOWS_COMPLETE_NOT_POWER_ACCEPTANCE',cases=results,
                    original_strict_failures_preserved=True,power_acceptance=False,gate_phase_checked=False)
    except BaseException as exc:
        result=dict(state='FAIL',error=repr(exc),completed_cases=results,artifacts_preserved=True,
                    automatic_retry=False,power_acceptance=False)
    save(out/'result.json',result,True)
    save(out/'status.json',dict(state=result['state'],completed=len(results)))
    return int(result['state']=='FAIL')


def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('action',choices=('prepare','execute'))
    p.add_argument('--output',type=Path,default=DEFAULT)
    p.add_argument('--plan-sha256')
    p.add_argument('--authorize-capture',action='store_true')
    a=p.parse_args()
    out=a.output.resolve()
    if a.action=='prepare':
        require(not a.authorize_capture,'Preparation does not launch GLS')
        prepare(out)
        print(json.dumps(dict(state='IMAGE_BOUND_NOT_LAUNCHED',output=str(out))))
        return 0
    return execute(out,a.plan_sha256,a.authorize_capture)


if __name__=='__main__':raise SystemExit(main())
