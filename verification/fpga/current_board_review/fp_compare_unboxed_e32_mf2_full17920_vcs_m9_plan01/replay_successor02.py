#!/usr/bin/env python3
"""Prepare/dryrun only until independent entry AND new parent run approval."""
import argparse
from dataclasses import asdict
import os
import shlex
import subprocess
import threading
import time
import checker
import detail_monitor
from scope import *
from specification import specification,owner_contract
common=checker.common

# Private binding to mature monitor/runner hooks, no editing sealed helper files.
import scope
scope.NAMES=[NAME]
sys.modules['newscope']=scope
TEMPLATE=G/'nan_min_soc_vcs_m6_plan01/replay.py'
require(sha(TEMPLATE)=='44539d4add863ab707e769d57440156adde8d196a27b20a00e60ba2e62384546','Mature numeric-first template')
worker=load('unboxed17920_mature_worker',TEMPLATE)
durable,merge_pins,first_cause=worker.durable,worker.merge_pins,worker.first_cause
monitor_command=worker.monitor_command
HOST=HERE/'host_final.json'
ENTRY=HERE/'ENTRY_REVIEW.json'

def cases():
    return [dict(id=NAME,original_name=NAME,historical_name=HISTORICAL,elf=str(ELF),sha256=ELF_SHA,
                 timeout_s=TIMEOUT,pass_markers=[MARKER,'BOARD_CASE_PASS '+NAME,'BOARD_REPLAY_PASS'])]

def reference_pins():
    require(sha(REVIEW)==REVIEW_SHA and sha(FPR_REVIEW)==FPR_REVIEW_SHA,'Accepted reference and frozen FPR chain')
    review=read(REVIEW);root=REF/'reference01'
    require(review['status']=='ACCEPTED_REFERENCE_FULL17920_SOURCE_ONLY_NOT_DUT' and review['accepted'] is True
            and review['firmware_to_HTIF']==2941812,'Reference terminal acceptance, not DUT')
    bindings={root/'COMPLETE.json':review['complete_sha256'],
              root/'audit01/result.json':review['audit_result_sha256'],
              root/'spike.wait.json':review['wait_receipt_sha256']['spike'],
              root/'audit.wait.json':review['wait_receipt_sha256']['audit'],
              REF/'execution_receipt01/outer.wait.json':review['wait_receipt_sha256']['outer']}
    for path,digest in bindings.items(): require(sha(path)==digest,'Reference evidence drift '+str(path))
    complete=read(root/'COMPLETE.json')
    require(complete['input_pins_unchanged'] is True and complete['reference_attempts']==1
            and complete['closed_semantic_parses']==1,'Exactly one complete reference')
    result=read(root/'audit01/result.json')
    require([result[k] for k in ('calls','result_bits','guards','flags','vstarts','helper_instructions',
             'stores','input_LD','output_LWU','record_LD')]==
             [17920,286720,35840,17920,17920,326144,878080,286720,17920,2240],'Exact complete FP32 source reference')
    require(result['EOF_pure_park'] is True,'Reference full EOF, not early HTIF return')
    for path in (root/'spike.wait.json',root/'audit.wait.json',REF/'execution_receipt01/outer.wait.json'):
        q=read(path)
        require(type(q['actual_wait_exit'])is int and q['actual_wait_exit']==0 and q['timed_out'] is False,
                'Actual numeric reference/audit/outer wait')
    pins=merge_pins(read(REF/'input_pins.json'),read(STAGE/'generated01/artifact_pins.json'),
                    {str(path):digest for path,digest in bindings.items()})
    fpr=read(FPR_REVIEW)
    pins=merge_pins(pins,{str(Path(fpr['frozen_root'])/p):h for p,h in fpr['source_pins'].items()})
    for p in [REVIEW,REVIEW.with_suffix('.md'),FPR_REVIEW,FPR_REVIEW.with_suffix('.md'),
              REF/'input_pins.json',REF/'ENTRY.json',REF/'parent_authorization01.json',
              STAGE/'linked_cfg01/soc.json',SOFTWARE/'program.elf',SOFTWARE/'disassemble.log',SOFTWARE/'symbols.log']:
        pins=merge_pins(pins,{str(p):sha(p)})
    # The accepted reference receipts bind the closed raw; do not reread it.
    require(complete['raw']['sha256']==review['recorded_raw_sha256'] and
            complete['raw']['bytes']==review['recorded_raw_bytes'],'Accepted reference raw identity')
    return pins

def service_contract():
    return dict(RemainAfterExit=False,Type='exec',stop_timeout_s=300,
                exit_hook=str(HERE/'exit_hook_successor.py'),exit_hook_sha256=sha(HERE/'exit_hook_successor.py'),
                collector=str(HERE/'collect_successor.py'),collector_sha256=sha(HERE/'collect_successor.py'),
                collector_bound_s=180,auto_after_main_exit=True)

def owned_pins():
    result={str(p):sha(p) for p in HERE.glob('*.py')}
    for mod in list(sys.modules.values()):
        f=getattr(mod,'__file__',None)
        if f and Path(f).is_file() and Path(f).resolve().is_relative_to(G.parents[3]):
            result[str(Path(f).resolve())]=sha(f)
    return result

def validate(plan):
    require(plan['status']=='PREPARED_NOT_RUN' and plan['cases']==cases() and plan['image']==str(IMAGE)
            and plan['image_sha256']==sha(IMAGE/'image.json')==IMAGE_SHA,'Exact runtime/image/ELF identity')
    require((plan['jobs'],plan['case_timeout_s'],plan['worker_timeout_s'],plan['service_timeout_s'],plan['unit'],plan['reserved_slots'])
            ==(1,10800,12000,13200,UNIT,0),'Fixed resource and time contract')
    require(plan['service_terminal_contract']==service_contract(),'Automatic numeric terminal collector')
    require(plan['detail_monitor']==detail_monitor.contract(),'Exact private early-failure contract')
    require(plan['spec']==specification() and plan['owner_contract']==owner_contract(),'Actual SoC spec and185 owner derivation')
    require(all(plan[k] is True for k in ('no_build','no_retry','no_fsdb','stop_first_fail','numeric_before_postcheck')),'Execution restrictions')
    host=read(HOST);receipt=read(HERE/'host_supplement.wait.json')
    require(host['status']=='PASS_HOST_ONLY_NOT_DUT' and host['failures']==host['errors']==0 and
            type(receipt['actual_wait_exit'])is int and receipt['actual_wait_exit']==0 and receipt['timed_out'] is False
            and receipt['log_sha256']==sha(HERE/'host_supplement.log'),'Actual short Host outcome')
    require(host['inherited_passed_methods']==34 and host['corrected_methods']==1 and host['corrected_subcases']==6
            and host['prior_host_sha256']==sha(HERE/'host02.json')
            and host['prior_wait_sha256']==sha(HERE/'host02.wait.json') and host['prior_actual_wait_exit']==1,
            'Exact composite Host evidence, old rc1 not relabeled')
    expected=merge_pins(reference_pins(),owned_pins(),host['pins'])
    require(all(plan['pins'].get(p)==h for p,h in expected.items()),'Complete current pins membership')
    common.base.verify_pins(plan['pins'])

def disk_gate(out,digest):
    require(sha(out/'plan.json')==digest,'Late disk plan drift')
    validate(read(out/'plan.json'))
    require(sha(out/'plan.json')==digest,'Late plan race')

def prepare(out):
    require(out.parent==HERE and not out.exists(),'Fresh owned output')
    ledger,repo,_=common.image_context(IMAGE)
    require(sha(IMAGE/'image.json')==IMAGE_SHA and Path(ledger['snapshot']).parent.name=='current_board_memory_candidate09','Frozen M9')
    pins=merge_pins(reference_pins(),owned_pins(),read(HOST)['pins'],common.image_pins(IMAGE,ledger,repo))
    short=read(HERE/'monitor_host01.json');wait=read(HERE/'monitor_host01.wait.json')
    require(short['status']=='PASS_MONITOR_SUCCESSOR_HOST_NOT_DUT' and short['failures']==short['errors']==0
            and type(wait['actual_wait_exit'])is int and wait['actual_wait_exit']==0 and wait['timed_out'] is False
            and wait['log_sha256']==sha(HERE/'monitor_host01.log'),'Actual narrow monitor Host success')
    for p in ('monitor_host01.json','monitor_host01.wait.json','monitor_host01.log','monitor_host01.command.json'):
        pins=merge_pins(pins,{str(HERE/p):sha(HERE/p)})
    for p in (HOST,HERE/'host02.json',HERE/'host02.wait.json',HERE/'host02.log',HERE/'host02.command.json',
              HERE/'host_supplement.wait.json',HERE/'host_supplement.log',HERE/'host_supplement.command.json'):
        pins=merge_pins(pins,{str(p):sha(p)})
    plan=dict(status='PREPARED_NOT_RUN',cases=cases(),spec=specification(),owner_contract=owner_contract(),
        image=str(IMAGE),image_sha256=IMAGE_SHA,snapshot_sha256=ledger['snapshot_sha256'],pins=pins,
        jobs=1,case_timeout_s=TIMEOUT,worker_timeout_s=WORKER,service_timeout_s=OUTER,unit=UNIT,reserved_slots=0,
        max_live_simv=24,min_available_GiB=32,no_build=True,no_retry=True,no_fsdb=True,stop_first_fail=True,
        numeric_before_postcheck=True,full_parent=True,linux=False,
        scope='Original17920 contiguous/32seeds/286720bits/35840guards/flags/vstarts; no partition reset',
        service_terminal_contract=service_contract(),detail_monitor=detail_monitor.contract(),
        reference_raw_identity=read(REF/'reference01/COMPLETE.json')['raw'],
        launch_gate='Hilbert exact independent ENTRY plus separately authorized parent run record; prepare is not launch permission')
    validate(plan);out.mkdir();durable(out/'plan.json',plan);digest=sha(out/'plan.json')
    command=[sys.executable,'-B',str(HERE/'replay_successor02.py'),'run','--out',str(out),'--plan-sha256',digest,
             '--entry-review',str(ENTRY),'--entry-sha256','__ACTUAL_INDEPENDENT_ENTRY_SHA__',
             '--parent-review','__NEW_PARENT_RUN_JSON__','--parent-sha256','__ACTUAL_PARENT_SHA__']
    service=['systemd-run','--user','--unit='+UNIT,'--property=Type=exec','--property=RemainAfterExit=no',
             '--property=TimeoutStopSec=300','--property=RuntimeMaxSec='+str(OUTER),'--property=KillMode=control-group','--property=Restart=no',
             '--property=WorkingDirectory='+str(HERE),'--property=StandardOutput=append:'+str(out/'service.log'),
             '--property=StandardError=append:'+str(out/'service.log'),
             '--property=ExecStopPost='+shlex.join([sys.executable,'-B',str(HERE/'exit_hook_successor.py'),'--out',str(out)]),*command]
    durable(out/'ready.json',dict(status='PREPARED_PENDING_INDEPENDENT_ENTRY_NO_LAUNCH',plan_sha256=digest,
                                 service_argv=service,service_command=shlex.join(service),DUT_started=False))
    print('PREPARED_NOT_LAUNCHED',digest,flush=True)

def dryrun(out,digest):
    disk_gate(out,digest)
    ledger,repo,(parent,options,testcase,_)=common.image_context(IMAGE)
    require(not(out/'dryrun').exists(),'Fresh dryrun')
    class NoBuild(parent):
        def build(self): return Path(ledger['simv'])
    opts=worker.build_options(options,repo,out,ledger,True)
    r=NoBuild(opts,[testcase(NAME,'app','',ELF,NAME,TIMEOUT)],sys.argv).run()
    require(len(r)==1 and r[0].status=='DRY_RUN' and r[0].returncode is None,'Actual dryrun only')
    root=out/'dryrun/tests'/NAME
    require(read(root/'command.json')==dict(command=monitor_command(root,ledger['simv'],NAME,ELF),cwd=str(root/'work')),'Exact dryrun command')
    require(not any((root/p).exists() for p in ('console.log','commit_trace.csv','work/run.vcs.log')),'No DUT outputs')
    disk_gate(out,digest)
    durable(out/'dryrun_gate.json',dict(status='DRYRUN_ONLY_NO_DUT',plan_sha256=digest,command_sha256=sha(root/'command.json'),build_invoked=False,DUT_started=False))

def monitored(original,abort,roots,simv):
    routes={str(root.resolve()/'work'):root for root in roots.values()}
    def call(command,cwd,console,timeout,cancel_event=None):
        root=routes.get(str(Path(cwd).resolve()))
        require(root is not None and Path(console)==root/'console.log' and timeout==TIMEOUT and
                list(map(str,command))==monitor_command(root,simv,NAME),'Exact monitor command/private scope')
        result=original(command,cwd,console,timeout,cancel_event)
        code,elapsed,timed,failure=result
        durable(root/'child_outcome.unvalidated.json',dict(name=NAME,historical_name=HISTORICAL,returncode=code,
            elapsed_s=elapsed,timed_out=timed,failure_seen=failure,command=list(map(str,command)),cwd=str(cwd),
            architectural_acceptance=False,kind='ACTUAL_MONITOR_WAIT'))
        require(type(code)is int and type(timed)is bool and type(failure)is bool,'Actual numeric outcome schema')
        if code!=0 or timed or failure: abort.set()
        require(read(root/'command.json')==dict(command=list(map(str,command)),cwd=str(cwd)),'Persisted command identity')
        if failure:
            text=(root/'console.log').read_text(errors='replace')
            found=detail_monitor.DETAIL.search(text)
            if found:
                durable(root/'detail_firstfailure.json',dict(kind='COMPLETE_ORIGINAL_DETAIL',
                    line=found.group(0),fields=found.groupdict(),console_sha256=sha(root/'console.log')))
        return result
    return call

@__import__('contextlib').contextmanager
def engine_hooks(engine,abort,roots,simv):
    old_monitor,old_fail=engine._run_monitored,engine.FAIL_RE
    engine._run_monitored=monitored(old_monitor,abort,roots,simv)
    engine.FAIL_RE=detail_monitor.combined(old_fail)
    try: yield
    finally: engine._run_monitored,engine.FAIL_RE=old_monitor,old_fail

def approval_gate(out,digest,entry,entrysha,parent,parentsha):
    require(entry==ENTRY and sha(entry)==entrysha,'Actual independent entry')
    e=read(entry)
    require(e['decision']=='NO_BLOCKER_FP32_FULL17920_M9_ENTRY' and e['plan_sha256']==digest and
            e['worker_sha256']==sha(HERE/'replay_successor02.py') and e['checker_sha256']==sha(HERE/'checker.py') and
            e['strict_sha256']==sha(HERE/'strict.py') and e['reference_review_sha256']==REVIEW_SHA,'Exact independent binding')
    require(parent and sha(parent)==parentsha,'Separate new parent run approval')
    p=read(parent)
    require(p['decision']=='AUTHORIZE_FP32_FULL17920_M9_ONCE' and p['plan_sha256']==digest and p['entry_sha256']==entrysha
            and p['unit']==UNIT and p['budget_s']==[10800,12000,13200] and p['jobs']==1,'Not prepare-only permission')
    return {str(entry):entrysha,str(parent):parentsha}

def service_identity():
    keys='Id,LoadState,ActiveState,SubState,MainPID,ControlGroup,RuntimeMaxUSec,KillMode,Restart,RemainAfterExit'
    q=subprocess.run(['systemctl','--user','show',UNIT,'--property='+keys],text=True,capture_output=True,timeout=10)
    require(q.returncode==0 and not q.stderr.strip(),'Actual user-manager query')
    p=dict(x.split('=',1) for x in q.stdout.splitlines());cg=Path('/proc/self/cgroup').read_text()
    require(p['Id']==UNIT and p['LoadState']=='loaded' and p['ActiveState']=='active' and p['SubState']=='running'
            and p['MainPID']==str(os.getpid()) and p['ControlGroup'].endswith('/'+UNIT) and p['ControlGroup'] in
            [x.split(':',2)[-1] for x in cg.splitlines()] and p['RuntimeMaxUSec']=='3h 40min'
            and p['KillMode']=='control-group' and p['Restart']=='no' and p['RemainAfterExit']=='no','Direct13200s service ownership')
    return dict(properties=p,cgroup=cg,pid=os.getpid())

def run(out,digest,entry,entrysha,parent,parentsha):
    disk_gate(out,digest);approval=approval_gate(out,digest,entry,entrysha,parent,parentsha)
    require(not(out/'replay').exists(),'Once-only no retry')
    ledger,repo,(base,options,testcase,_)=common.image_context(IMAGE)
    owner=service_identity();resources=common.resources(out,1,0)
    durable(out/'launch.json',dict(owner=owner,resources=resources,plan_sha256=digest,approval_pins=approval,started=time.time()))
    abort=threading.Event();timer=threading.Timer(WORKER,abort.set);timer.daemon=True;timer.start()
    terminal=dict(status='NOT_PASS',plan_sha256=digest,results=[],retries=0,pins_unchanged=False)
    root=out/'replay/tests'/NAME
    import ara_verify.runner as engine
    with common.abort_signals(abort),engine_hooks(engine,abort,{NAME:root},ledger['simv']):
        try:
            def admit(name):
                require(name==NAME and not abort.is_set(),'Aborted dispatch')
                disk_gate(out,digest);common.base.verify_pins(approval);common.resources(out,1,0)
            def check(result):
                durable(root/'strict_original.json',checker.artifacts(result,cases()[0],ledger,read(out/'plan.json')['spec'],abort))
            opts=worker.build_options(options,repo,out,ledger)
            results=worker.checked_runner(base,abort,check,admit)(opts,[testcase(NAME,'app','',ELF,NAME,TIMEOUT)],sys.argv).run()
            terminal['results']=[dict(asdict(r),artifact_dir=str(r.artifact_dir)) for r in results]
            worker.terminal_gate(results,read(out/'replay/run.json'),abort,ledger)
            require(read(out/'replay/summary.json')==terminal['results'],'Actual summary exact membership')
            numeric=read(root/'child_outcome.unvalidated.json')
            require(type(numeric['returncode'])is int and numeric['returncode']==0 and
                    numeric['timed_out'] is False and numeric['failure_seen'] is False,'Durable child0 prerequisite')
            disk_gate(out,digest);common.base.verify_pins(approval)
            files=[out/'launch.json',out/'replay/run.json',out/'replay/summary.json']
            files += [root/p for p in ('input.elf','inputs.json','command.json','console.log','work/run.vcs.log',
                                      'commit_trace.csv','trace_summary.json','strict_original.json',
                                      'child_outcome.unvalidated.json','runner_result.unvalidated.json')]
            terminal.update(status=PASS,pins_unchanged=True,evidence_pins={str(p):sha(p) for p in files},full_parent=True,linux=False)
        except BaseException as error:
            abort.set();first_cause(out,dict(kind='WORKER_FIRST_CAUSE',error=repr(error)))
            terminal.update(status='NOT_PASS',error=repr(error))
            if(root/'child_outcome.unvalidated.json').exists(): terminal['unvalidated_child']=read(root/'child_outcome.unvalidated.json')
        finally:
            terminal['finished']=time.time();common.publish(out,terminal,abort);timer.cancel()
    return int(terminal['status']!=PASS)

worker.cases=cases;worker.NAMES=[NAME];worker.JOBS=1;worker.TIMEOUT=TIMEOUT;worker.OUTER=OUTER
worker.HERE=HERE;worker.IMAGE=IMAGE;worker.checker=checker;worker.monitored=monitored

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','dryrun','run'])
    p.add_argument('--out',type=Path,required=True);p.add_argument('--plan-sha256')
    p.add_argument('--entry-review',type=Path);p.add_argument('--entry-sha256')
    p.add_argument('--parent-review',type=Path);p.add_argument('--parent-sha256');a=p.parse_args()
    out=a.out.resolve();require(out.parent==HERE,'Owned output')
    if a.mode=='prepare': prepare(out);return 0
    if a.mode=='dryrun': dryrun(out,a.plan_sha256);return 0
    env=common.base.shared.environment();env.update(XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}',
        DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
    os.environ.clear();os.environ.update(env)
    return run(out,a.plan_sha256,a.entry_review,a.entry_sha256,a.parent_review,a.parent_sha256)

if __name__=='__main__': raise SystemExit(main())
