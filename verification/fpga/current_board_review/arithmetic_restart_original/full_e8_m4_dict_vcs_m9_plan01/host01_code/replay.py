#!/usr/bin/env python3
"""Single full4095 M9 successor, mature numeric-first engine, never builds."""
import argparse
import importlib.util
import os
from pathlib import Path
import shlex
import sys
sys.dont_write_bytecode=True
import checker
from checker import HERE,REF,READY_SHA,SHAPES,SHAPE,read,sha,require,common
CORE_PATH=HERE.parent/'full_e8_mf4_o2_vcs_m9_successor02/replay.py'
core=checker.load('full4095_private_mature_worker',CORE_PATH)
IMAGE=core.IMAGE
JOBS,CASE_BOUND,WORKER_BOUND,OUTER=1,10800,12000,13200
UNIT='ara-arithmetic-original-e8-m4-full4095-m9-01.service'
PASS='PASS_M9_FULL_ORIGINAL_E8_M4_4095_CALLS_NOT_LINUX'
durable=core.durable
monitored_with_outcome=core.monitored_with_outcome
checked_runner=core.checked_runner
owner_gate=core.owner_gate

def scope():
    spec=checker.specification()
    return [dict(id=checker.ID,original_name=SHAPE,shape=SHAPE,elf=spec['backend']['elf'],
        sha256=checker.ELF_SHA,timeout_s=CASE_BOUND,pass_markers=[checker.marker()])]

def reference_pins():
    require(sha(REF/'READY.json')==READY_SHA,'Accepted source READY')
    ready=read(REF/'READY.json')
    require(ready['status']=='READY_SOFTWARE_REFERENCE_ONLY_NOT_DUT' and ready['full_calls']==4095 and
        ready['firmware']==2646649 and ready['Spike_invocations_total']==1 and ready['pins_pre_post_unchanged'],
        'Full original source/ref actual cost')
    require(ready['old_STOPPED_preserved'] and not ready['original_Linux_historical_stall_closed'],'Qualified recovery not old observer PASS')
    pins=read(REF/'offline_successor01/preflight.json')['pins']
    for path in (REF/'READY.json',REF/'pins.json',REF/'proof.json',REF/'offline_successor01/result.json',
        REF/'offline_successor01/audit_execution.json',REF/'offline_successor01/audit_command.json',
        REF/'offline_successor01/host_result.json',REF/'offline_successor01/host_execution.json',
        REF/'offline_successor01/run_offline.py',REF/'offline_successor01/test_host.py',
        HERE.parent/'full_e8_m4_dict_reference_entry01/offline_entry02.json'):
        pins[str(path)]=sha(path)
    require(sha(REF/'offline_successor01/result.json')==ready['reference_result_sha256'],'Actual full reference result')
    for path,limit in ((REF/'reference01/execution.json',120),(REF/'offline_successor01/audit_execution.json',600)):
        outcome=read(path)
        require(type(outcome['actual_wait_returncode'])is int and outcome['actual_wait_returncode']==0 and
            outcome['timed_out'] is False and outcome['retries']==0 and outcome['elapsed_s']<=limit,'Actual source/ref numeric exit')
    common.base.verify_pins(pins)
    return pins

def validate(plan,image):
    require(image==IMAGE and plan['status']=='PREPARED_NOT_RUN' and plan['image']==str(IMAGE) and
        plan['image_sha256']==sha(IMAGE/'image.json'),'Exact frozen M9 image')
    require(plan['cases']==scope() and plan['jobs']==1 and plan['case_timeout_s']==10800 and
        plan['worker_timeout_s']==12000 and plan['service_timeout_s']==13200 and plan['unit']==UNIT and
        plan['reserved_slots']==0 and all(plan[k] is True for k in ('no_build','no_retry','no_fsdb','stop_first_fail')),
        'Exact single original4095/bounds/no-retry')
    require(plan['reference_ready_sha256']==READY_SHA and plan['user_conditional_authorization'] is True,'Actual source/reference admission')
    require(plan['specs']=={SHAPE:checker.specification()},'Actual ELF spec drift')
    common.base.verify_pins(plan['pins'])
    for name in ('checker.py','replay.py','reset_profile.json','collect.py','exit_hook.py'):
        require(plan['pins'].get(str(HERE/name))==sha(HERE/name),'Consumed own worker file drift')

def prepare(image,out,reserved):
    require(image==IMAGE and not out.exists() and reserved==0,'Fresh exact own output')
    host=read(HERE/'host01.json');exit=read(HERE/'host_process_exit.json')
    require(host['status']=='PASS_HOST_ONLY' and host['failures']==0 and host['tests']>=14 and
        host['actual_abi_entry_checked'] and host['full4095_streams']==1 and
        host['full_positive_shapes']==[SHAPE] and exit['returncode']==0 and exit['timed_out'] is False,'Actual full Host/ABI gate')
    common.base.verify_pins(host['pins'])
    pins=reference_pins();ledger,repo,_=common.image_context(image)
    require(Path(ledger['snapshot']).parent.name=='current_board_memory_candidate09','Frozen M9')
    pins.update(common.image_pins(image,ledger,repo));pins.update(host['pins'])
    for module in list(sys.modules.values()):
        path=getattr(module,'__file__',None)
        if path and Path(path).is_file() and Path(path).resolve().is_relative_to(checker.G.parents[2]):
            pins[str(Path(path).resolve())]=sha(path)
    profile=read(HERE/'reset_profile.json');pins.update(profile['rtl_pins'])
    pins[str(HERE.parent/'full_e8_mf4_o2_vcs_m9_successor02/reset_profile.json')]=profile['authority_sha256']
    for name in ('checker.py','replay.py','reset_profile.json','collect.py','exit_hook.py','test_host.py','host_records.py',
        'run_host.py','host01.json','host01.log','host_process_exit.json','README.md','USER_AUTHORIZATION.md','launch_once.py'):
        pins[str(HERE/name)]=sha(HERE/name)
    plan=dict(status='PREPARED_NOT_RUN',image=str(image),image_sha256=sha(image/'image.json'),snapshot_sha256=ledger['snapshot_sha256'],
        cases=scope(),specs={SHAPE:checker.specification()},pins=pins,jobs=1,case_timeout_s=10800,worker_timeout_s=12000,
        service_timeout_s=13200,unit=UNIT,reserved_slots=0,no_build=True,no_retry=True,no_fsdb=True,stop_first_fail=True,
        reference_ready_sha256=READY_SHA,user_conditional_authorization=True,resources_checked_only_at_run=True,
        scope='Original e8/m4 full4095 continuous source port, not original Linux stall closure',
        cost=dict(budget_gate='FIT_PROJECTION_ONLY',conservative_projection_s=read(REF/'READY.json')['projection_s_with_20_percent_margin'],
            actual_reference_firmware=2646649,not_wall_clock_guarantee=True))
    validate(plan,image);out.mkdir();durable(out/'plan.json',plan);digest=sha(out/'plan.json')
    command=[sys.executable,'-B',str(HERE/'replay.py'),'run','--image',str(image),'--out',str(out),'--plan-sha256',digest,'--authorize-run']
    service=['systemd-run','--user','--unit='+UNIT,'--property=RuntimeMaxSec=13200','--property=KillMode=control-group',
        '--property=Restart=no','--property=WorkingDirectory='+str(HERE),'--property=StandardOutput=append:'+str(out/'service.log'),
        '--property=StandardError=append:'+str(out/'service.log'),'--property=ExecStopPost='+shlex.join([
            sys.executable,'-B',str(HERE/'exit_hook.py'),'--out',str(out)]),*command]
    durable(out/'ready.json',dict(status='PREPARED_PENDING_EXACT_TESLA_ENTRY_NO_DUT',plan_sha256=digest,command=command,
        service_command=shlex.join(service),pin_count=len(pins),DUT_started=False))
    print('PREPARED',digest,flush=True)

def terminal_disk_gate(out,digest,image):
    require(sha(out/'plan.json')==digest,'Late plan drift');validate(read(out/'plan.json'),image)

# This imported worker has a private namespace. Original sealed module/files are untouched.
core.UNIT,core.PASS,core.scope,core.validate,core.reference_pins=UNIT,PASS,scope,validate,reference_pins
core.terminal_disk_gate=terminal_disk_gate
core.HERE,core.REF,core.READY_SHA,core.SHAPES=HERE,REF,READY_SHA,SHAPES
reviews=core.reviews

def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('prepare','dryrun','run'))
    for name in ('image','out'):parser.add_argument('--'+name,type=Path,required=True)
    for name in ('authorize-prepare','authorize-run'):parser.add_argument('--'+name,action='store_true')
    parser.add_argument('--reserved-slots',type=int,default=0)
    for name in ('plan-sha256','entry-review-sha256','parent-review-sha256'):parser.add_argument('--'+name)
    for name in ('entry-review','parent-review'):parser.add_argument('--'+name,type=Path)
    args=parser.parse_args();image,out=args.image.resolve(),args.out.resolve()
    require(out.parent==HERE,'Own direct-child output only')
    env=common.base.shared.environment();os.environ.clear();os.environ.update(env)
    if args.mode=='prepare':
        require(args.authorize_prepare,'Explicit prepare');prepare(image,out,args.reserved_slots);return 0
    if args.mode=='dryrun':
        require(sha(out/'plan.json')==args.plan_sha256,'Exact dryrun plan');validate(read(out/'plan.json'),image)
        ledger,_,_=common.image_context(image);case=scope()[0];root=out/'replay/tests'/case['id']
        durable(out/'dryrun.json',dict(status='DRYRUN_ONLY_NO_PROCESS',plan_sha256=args.plan_sha256,commands=[dict(cwd=str(root/'work'),
            command=[ledger['simv'],'-l','run.vcs.log','+ntb_random_seed=1','+PRELOAD='+str(root/'input.elf'),
                '+TESTCASE='+case['id'],'+NO_FSDB','+COMMIT_TRACE='+str(root/'commit_trace.csv')])]))
        print('DRYRUN_ONLY_NO_PROCESS');return 0
    return core.run(image,out,args.plan_sha256,args.authorize_run,args.entry_review,args.entry_review_sha256,args.parent_review,args.parent_review_sha256)

if __name__=='__main__':raise SystemExit(main())
