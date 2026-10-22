#!/usr/bin/env python3
"""Original682 packed successor with frozen M8 and numeric-first monitor."""
import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import threading
import time

sys.dont_write_bytecode=True
import checker
from checker import common,require,read,sha
from newscope import *
TEMPLATE=BASE/'nan_min_soc_vcs_m6_plan01/replay.py'
require(sha(TEMPLATE)=='44539d4add863ab707e769d57440156adde8d196a27b20a00e60ba2e62384546','Sealed numeric-monitor template')
_spec=importlib.util.spec_from_file_location('sealed_M6_numeric_before_generic',TEMPLATE)
worker=importlib.util.module_from_spec(_spec);sys.modules[_spec.name]=worker;_spec.loader.exec_module(worker)
durable,first_cause,merge_pins=worker.durable,worker.first_cause,worker.merge_pins
monitor_command=worker.monitor_command
HOST_REPORT='host_worker01.json'
BINDING=HERE/'entry_binding.json'


def reference_inputs():
    require(sha(READY)==READY_SHA,'Exact source READY')
    r=read(READY)
    require(r['status']=='PREPARED_SCALAR_OPTIMIZATION_HOST_REFERENCE_COST_NOT_DUT_ENTRY' and
            sha(PREP/'pins.json')==r['pins_sha256'],'Source preparation schema/pins')
    result=read(HERE/'reference01/result.json')
    require(result['status']=='FULL_ORIGINAL682_STRICT_ACCEPTED_NOT_FULL_PARENT' and
            [result[k] for k in ('target_calls','full_result_bit_checks','guard_checks','returned_flags_checked',
                                'returned_vstart_zero','helper_instructions')]==[682,349184,1364,682,682,12592] and
            result['full_reference_vectors'] is True and result['pins_unchanged'] is True and
            result['actual_process']['returncode']==0 and not result['actual_process']['timed_out'],
            'Actual full dynamic reference acceptance')
    require(result['firmware_retired_to_exit']<2300000 and
            result['firmware_retired_to_exit']/(4529502/7544.534202890936)*1.2<TIMEOUT,'Measured budget gate')
    pins=merge_pins(read(PREP/'pins.json'),read(HERE/'reference01/input_pins.json'))
    for p in [READY,PREP/'pins.json',MAIN_REVIEW,HERE/'reference01/result.json',
              HERE/'reference01/execution.json',HERE/'reference01/command.json',
              HERE/'reference01/input_pins.json',HERE/'reference01/commits.log',
              HERE/'host_strict01.json',HERE/'USER_AUTHORIZATION.md']:
        pins=merge_pins(pins,{str(p):sha(p)})
    require(pins[str(HERE/'reference01/commits.log')]==result['raw_sha256'],'Raw reference linkage')
    common.base.verify_pins(pins)
    return pins

def independent_reference():
    binding=read(BINDING)
    require(binding['ready_sha256']==READY_SHA and binding['decision']=='NO_BLOCKER_DYNAMIC_CHECKER',
            'Actual dynamic checker independent review')
    common.base.verify_pins(binding['pins'])
    require(binding['checker_sha256']==sha(HERE/'strict.py') and
            binding['runner_sha256']==sha(HERE/'replay.py'),'Reviewed dynamic code')
    return merge_pins(binding['pins'],{str(BINDING):sha(BINDING)})

def cases():
    elf=PREP/'run01/soc.elf'
    require(sha(elf)==read(READY)['soc_elf_sha256'],'Packed SoC ELF identity')
    return [dict(id=NAME,original_name=NAME,source_label=HISTORICAL,elf=str(elf),sha256=sha(elf),
                 timeout_s=TIMEOUT,pass_markers=[MARKER,'BOARD_CASE_PASS '+NAME,'BOARD_REPLAY_PASS'])]

def predecessor_pins():
    return {}

def validate(plan,image):
    require(image==IMAGE and plan['status']=='PREPARED_NOT_RUN' and
            plan['image_sha256']==sha(image/'image.json')==IMAGE_SHA,'Frozen M8 image')
    require(plan['cases']==cases() and plan['specs']=={NAME:checker.specification(Path(cases()[0]['elf']))} and
            plan['jobs']==JOBS and plan['timeout_s']==TIMEOUT and plan['service_timeout_s']==OUTER and
            plan['unit']==UNIT and plan['reference_ready_sha256']==READY_SHA and
            all(plan[k] is True for k in ('no_build','no_retry','no_fsdb','no_code_coverage','no_ucli',
                                         'stop_first_fail','numeric_monitor_before_postcheck')),
            'Exact682 fixed-scope fixed-budget plan')
    expected=merge_pins(reference_inputs(),independent_reference())
    require(all(plan['pins'].get(p)==h for p,h in expected.items()),'Complete evidence pin membership')
    require(plan['pins'].get(str(HERE/'replay.py'))==sha(HERE/'replay.py'),'Worker pin')
    host=read(HERE/HOST_REPORT)
    require(host['status']=='PASS_HOST_ONLY_NOT_DUT' and host['failures']==host['errors']==0 and
            all(plan['pins'].get(p)==h for p,h in host['pins'].items()),'Worker Host/code identity')
    common.base.verify_pins(plan['pins'])

def terminal_plan_gate(out,digest,image):
    require(sha(out/'plan.json')==digest,'Late disk plan drift')
    validate(read(out/'plan.json'),image)
    require(sha(out/'plan.json')==digest,'Plan drift during late gate')


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
                    architectural_acceptance=False,name=name,source_label=HISTORICAL,
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



def service_identity():
    runtime=Path('/run/user')/str(os.getuid())
    require(runtime.stat().st_uid==os.getuid() and (runtime/'bus').is_socket(),'Trusted user bus')
    env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(runtime/'bus'))
    keys='Id,LoadState,ActiveState,SubState,MainPID,ControlGroup,RuntimeMaxUSec,KillMode,Restart'
    q=subprocess.run(['systemctl','--user','show',UNIT,'--property='+keys],env=env,text=True,capture_output=True,timeout=10)
    require(q.returncode==0 and not q.stderr.strip(),'Service query')
    p=dict(line.split('=',1) for line in q.stdout.splitlines());cg=Path('/proc/self/cgroup').read_text()
    require(p['Id']==UNIT and p['LoadState']=='loaded' and p['ActiveState']=='active' and
            p['SubState']=='running' and p['MainPID']==str(os.getpid()) and
            p['ControlGroup'].endswith('/'+UNIT) and p['ControlGroup'] in
            [line.split(':',2)[-1] for line in cg.splitlines()] and p['RuntimeMaxUSec']=='3h 40min' and
            p['KillMode']=='control-group' and p['Restart']=='no','Direct worker/fixed13200s')
    return dict(properties=p,cgroup=cg,pid=os.getpid())


def authorization_gate(digest,path,digest_parent):
    require(path==HERE/'USER_AUTHORIZATION.md' and digest_parent==sha(path),'Exact existing user authorization')
    return merge_pins(independent_reference(),{str(path):digest_parent})

def prepare(image,out,reserved):
    require(image==IMAGE and out.parent==HERE and not out.exists() and reserved==0,'Fresh owned plan')
    pins=merge_pins(reference_inputs(),independent_reference())
    host=read(HERE/HOST_REPORT)
    require(host['status']=='PASS_HOST_ONLY_NOT_DUT' and host['failures']==host['errors']==0,'Worker Host PASS')
    common.base.verify_pins(host['pins']);pins=merge_pins(pins,host['pins'])
    ledger,repo,_=common.image_context(image)
    require(Path(ledger['snapshot']).parent.name=='current_board_memory_candidate08','Exact M8 snapshot')
    pins=merge_pins(pins,common.image_pins(image,ledger,repo))
    for mod in list(sys.modules.values()):
        p=getattr(mod,'__file__',None)
        if p and Path(p).is_file() and Path(p).resolve().is_relative_to(HERE.parents[4]):
            pins=merge_pins(pins,{str(Path(p).resolve()):sha(Path(p))})
    for f in ('newscope.py','model.py','elf.py','strict.py','checker.py','replay.py','test_strict.py',
              'test_worker.py','host_strict01.json',HOST_REPORT,'USER_AUTHORIZATION.md'):
        pins=merge_pins(pins,{str(HERE/f):sha(HERE/f)})
    from elf import OBJDUMP,NM
    pins=merge_pins(pins,{str(OBJDUMP):sha(OBJDUMP),str(NM):sha(NM)})
    plan=dict(status='PREPARED_NOT_RUN',image=str(image),image_sha256=IMAGE_SHA,snapshot_sha256=ledger['snapshot_sha256'],
        cases=cases(),specs={NAME:checker.specification(Path(cases()[0]['elf']))},pins=pins,jobs=JOBS,
        timeout_s=TIMEOUT,service_timeout_s=OUTER,unit=UNIT,reserved_slots=0,
        no_build=True,no_retry=True,no_fsdb=True,no_code_coverage=True,no_ucli=True,stop_first_fail=True,
        numeric_monitor_before_postcheck=True,reference_ready_sha256=READY_SHA,
        scope='All682/681predecessors,not17920/Linux; original complete512bit oracle and flags',
        budget=dict(case_s=TIMEOUT,service_s=OUTER,no_autoextension=True),
        user_authorization_sha256=sha(HERE/'USER_AUTHORIZATION.md'))
    validate(plan,image);out.mkdir();durable(out/'plan.json',plan);digest=sha(out/'plan.json')
    command=[sys.executable,'-B',str(HERE/'replay.py'),'run','--out',str(out),'--plan-sha256',digest,
             '--authorize-run','--parent-review',str(HERE/'USER_AUTHORIZATION.md'),
             '--parent-review-sha256',sha(HERE/'USER_AUTHORIZATION.md')]
    service=['systemd-run','--user','--unit='+UNIT,'--property=Type=exec',
             '--property=RuntimeMaxSec='+str(OUTER),'--property=KillMode=control-group',
             '--property=Restart=no','--property=WorkingDirectory='+str(HERE),
             '--property=StandardOutput=append:'+str(out/'service.log'),
             '--property=StandardError=append:'+str(out/'service.log'),*command]
    durable(out/'ready.json',dict(status='PREPARED_NOT_LAUNCHED',plan_sha256=digest,
            service_command=shlex.join(service),service_argv=service,command=command,DUT_started=False))
    print('PREPARED_NOT_LAUNCHED',digest,flush=True)

def dryrun(image,out,digest):
    terminal_plan_gate(out,digest,image)
    ledger,repo,(parent,options,testcase,_)=common.image_context(image)
    require(not(out/'dryrun').exists(),'Exactly one fresh dryrun')
    class NoBuild(parent):
        def build(self):return Path(ledger['simv'])
    opts=worker.build_options(options,repo,out,ledger,True)
    tests=[testcase(NAME,'app','',Path(cases()[0]['elf']),NAME,TIMEOUT)]
    results=NoBuild(opts,tests,sys.argv).run()
    require(len(results)==1 and results[0].status=='DRY_RUN' and results[0].returncode is None,'Exact dryrun result')
    root=out/'dryrun/tests'/NAME
    command=read(root/'command.json')
    require(command==dict(command=worker.monitor_command(root,ledger['simv'],NAME,Path(cases()[0]['elf'])),
                          cwd=str(root/'work')),'Actual private ELF dryrun command')
    require(not any((root/f).exists() for f in ('console.log','commit_trace.csv','work/run.vcs.log')),'No DUT outputs in dryrun')
    terminal_plan_gate(out,digest,image)
    durable(out/'dryrun_gate.json',dict(status='DRYRUN_ONLY_NO_DUT',plan_sha256=digest,
        command_pin={str(root/'command.json'):sha(root/'command.json')},build_invoked=False,DUT_started=False))
    print('DRYRUN_ONLY_NO_DUT',digest,flush=True)


def run(image,out,digest,authorized,path,parent_sha):
    require(authorized,'Main run authorization required')
    terminal_plan_gate(out,digest,image);approval=authorization_gate(digest,path,parent_sha)
    plan=read(out/'plan.json');ledger,repo,(parent,options,testcase,_)=common.image_context(image)
    owner=service_identity();admission=common.resources(out,1,0)
    durable(out/'launch.json',dict(owner=owner,admission=admission,plan_sha256=digest,approval_pins=approval,started=time.time()))
    abort=threading.Event();terminal=dict(status='NOT_PASS',plan_sha256=digest,results=[],retries=0,pins_unchanged=False)
    import ara_verify.runner as engine
    from ara_verify.trace import validate_trace
    root=out/'replay/tests'/NAME
    with common.abort_signals(abort),worker.engine_hooks(engine,abort,{NAME:root},ledger['simv']):
        try:
            require(not(out/'replay').exists(),'Fresh no-retry execution')
            def admit(name):
                require(name==NAME and not abort.is_set(),'Aborted/unknown dispatch')
                terminal_plan_gate(out,digest,image);common.base.verify_pins(approval);common.resources(out,1,0)
            def check(result):
                report=checker.artifacts(result,cases()[0],ledger,plan['specs'][NAME],validate_trace)
                durable(root/'strict_original.json',report)
            opts=worker.build_options(options,repo,out,ledger)
            tests=[testcase(NAME,'app','',Path(cases()[0]['elf']),NAME,TIMEOUT)]
            results=worker.checked_runner(parent,abort,check,admit)(opts,tests,sys.argv).run()
            terminal['results']=[dict(asdict(r),artifact_dir=str(r.artifact_dir)) for r in results]
            worker.terminal_gate(results,read(out/'replay/run.json'),abort,ledger)
            require(read(out/'replay/summary.json')==terminal['results'],'Actual summary membership')
            terminal_plan_gate(out,digest,image);common.image_context(image);common.base.verify_pins(approval)
            outcome=read(root/'child_outcome.unvalidated.json')
            require(type(outcome['returncode']) is int and outcome['returncode']==0 and
                    outcome['timed_out'] is False and outcome['failure_seen'] is False and
                    not(out/'first_cause.json').exists(),'Actual monitor0/no failure/sticky cause')
            files=[out/'launch.json',out/'replay/run.json',out/'replay/summary.json']
            files += [root/f for f in ('input.elf','inputs.json','command.json','console.log','work/run.vcs.log',
                 'commit_trace.csv','trace_summary.json','strict_original.json','child_outcome.unvalidated.json',
                 'runner_result.unvalidated.json','child_command.provenance.json')]
            terminal.update(status=PASS,pins_unchanged=True,evidence_pins={str(f):sha(f) for f in files},full_parent_accepted=False)
        except BaseException as error:
            abort.set();first_cause(out,dict(kind='WORKER_EXCEPTION',error=repr(error)))
            terminal.update(status='NOT_PASS',error=repr(error))
            if(root/'child_outcome.unvalidated.json').exists():
                terminal['actual_unvalidated_child']=read(root/'child_outcome.unvalidated.json')
        finally:
            terminal['finished']=time.time();common.publish(out,terminal,abort)
    print(terminal['status'],flush=True);return int(terminal['status']!=PASS)


# Bind only this private immutable template module, never edit consumed files.
worker.cases=cases
worker.monitored=monitored
worker.NAMES=NAMES
worker.JOBS=JOBS
worker.TIMEOUT=TIMEOUT
worker.OUTER=OUTER
worker.HERE=HERE
worker.IMAGE=IMAGE
worker.checker=checker


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['prepare','dryrun','run'])
    p.add_argument('--out',type=Path,required=True);p.add_argument('--authorize-prepare',action='store_true')
    p.add_argument('--authorize-run',action='store_true');p.add_argument('--reserved-slots',type=int,default=0)
    p.add_argument('--plan-sha256');p.add_argument('--parent-review',type=Path);p.add_argument('--parent-review-sha256')
    a=p.parse_args();out=a.out.resolve();require(out.parent==HERE,'Owned direct output')
    if a.mode=='prepare':
        require(a.authorize_prepare,'Prepare-only authorization')
        durable(HERE/'prepare_attempt01.json',dict(command=sys.argv,DUT_started=False))
        try:prepare(IMAGE,out,a.reserved_slots)
        except BaseException as error:
            durable(HERE/'prepare_rejected01.json',dict(error=repr(error),no_retry=True,DUT_started=False));raise
        return 0
    if a.mode=='dryrun':dryrun(IMAGE,out,a.plan_sha256);return 0
    env=common.base.shared.environment();os.environ.clear();os.environ.update(env)
    return run(IMAGE,out,a.plan_sha256,a.authorize_run,a.parent_review,a.parent_review_sha256)


if __name__=='__main__':raise SystemExit(main())
