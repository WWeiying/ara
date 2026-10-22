#!/usr/bin/env python3
"""Single full4095 M9 successor, mature numeric-first engine, never builds."""
import argparse
import importlib.util
import os
from pathlib import Path
import shlex
import sys
import time
sys.dont_write_bytecode=True
import checker
from checker import HERE,REF,READY_SHA,SHAPES,SHAPE,read,sha,require,common
CORE_PATH=HERE.parent/'full_e8_mf4_o2_vcs_m9_successor02/replay.py'
core=checker.load('full4095_private_mature_worker',CORE_PATH)
IMAGE=core.IMAGE
JOBS,CASE_BOUND,WORKER_BOUND,OUTER=1,10800,12000,13200
UNIT='ara-arithmetic-original-e16-m2-full4095-m9-01.service'
PASS='PASS_M9_FULL_ORIGINAL_E16_M2_4095_CALLS_NOT_LINUX'
durable=core.durable
numeric_monitor=core.monitored_with_outcome
def monitored_with_outcome(original,abort):
    wrapped=numeric_monitor(original,abort)
    def monitored(*args,**kwargs):
        start=time.monotonic();print('PHASE actual_monitor START',flush=True)
        outcome=wrapped(*args,**kwargs)
        print(f'PHASE actual_monitor SAVED rc={outcome[0]} elapsed={time.monotonic()-start:.3f}s',flush=True)
        return outcome
    return monitored
checked_runner=core.checked_runner
owner_gate=core.owner_gate

def scope():
    spec=checker.specification()
    return [dict(id=checker.ID,original_name=SHAPE,shape=SHAPE,elf=spec['backend']['elf'],
        sha256=checker.ELF_SHA,timeout_s=CASE_BOUND,pass_markers=[checker.marker()])]

def reference_pins():
    require(sha(REF/'READY.json')==READY_SHA,'Accepted exact typed16 READY')
    ready=read(REF/'READY.json')
    require(ready['status']=='REFERENCE_FULL4095_PASS_SOFTWARE_ONLY_NOT_DUT' and
        [ready[k] for k in ('calls','results','guards','returned_vstart_zero','helper_instructions','packed_output_reads',
            'checked_bytes_each','SEW','CAP','vtype')]==[4095,524160,8190,4095,53235,135135,260,16,128,9] and
        ready['LMUL']=='m2' and ready['firmware']==1072555 and ready['reference_attempts']==1 and
        ready['source_pins_pre_post_unchanged'] and ready['DUT_runs']==0 and ready['EOF_checked'] and
        not ready['original_Linux_historical_stall_closed'],'Actual full4095 source/ref scope')
    require([ready[k] for k in ('physical_registers','tail_bytes','typed_sentinel',
        'vlm_read_bytes','physical_mask_bytes')]==[2,4,'005b',16,128],
        'Actual two-register typed16 physical scope')
    pins=dict(read(REF/'reference01/preflight_pins.json'))
    require(sha(REF/'reference_entry.json')==ready['entry_sha256'],'Actual reference entry')
    review=HERE.parent/'full_e16_m2_source_review01/REFERENCE_ENTRY_REVIEW01.json'
    require(sha(review)==ready['actual_review_sha256'] and read(review)['status']==
        'NO_BLOCKER_SOURCE_SOFTWARE_FOR_ONE_BOUNDED_REFERENCE_NOT_DUT','Actual independent reference entry')
    require(sha(REF/'reference01/result.json')==ready['reference_sha256'],'Actual full reference result')
    for name,key,limit in (('execution.json','actual_reference_execution_sha256',120),
        ('audit_execution.json','actual_audit_execution_sha256',600)):
        path=REF/'reference01'/name;outcome=read(path)
        require(sha(path)==ready[key] and type(outcome['actual_wait_returncode'])is int and
            outcome['actual_wait_returncode']==0 and outcome['timed_out'] is False and
            outcome['retries']==0 and 0<outcome['elapsed_s']<=limit,'Actual source/ref numeric exit')
    # This file is written only from an actual completed independent terminal report.
    # Missing terminal binding is a hard preparation blocker, not an invented pin.
    binding=read(HERE/'reference_terminal_binding.json')
    path=Path(binding['path']);require(sha(path)==binding['sha256'],'Actual terminal report pin')
    require(binding['READY_sha256']==READY_SHA,'Exact terminal READY identity')
    # Adapt only after the independent actual report schema is available.
    # No absent report or Boolean-only attestation can admit this worker.
    terminal_gate=checker.load('actual_typed16_reference_terminal_gate',HERE/'terminal_gate.py')
    terminal_gate.verify(binding,ready)
    pins[str(path)]=binding['sha256']
    for path in (review,REF/'reference_entry.json',REF/'READY.json',REF/'reference01/result.json',
        REF/'reference01/execution.json',REF/'reference01/audit_execution.json',
        REF/'reference01/preflight_pins.json',REF/'reference01/command.json',REF/'reference01/audit_command.json',
        HERE/'reference_terminal_binding.json',HERE/'owner_policy.py',
        HERE/'owner_contract.json'):
        pins[str(path)]=sha(path)
    eligibility=checker.eligibility
    require(sha(eligibility.DISPATCHER)==eligibility.DISPATCHER_SHA,'Actual immutable M9 VI no-op decode')
    pins[str(eligibility.DISPATCHER)]=eligibility.DISPATCHER_SHA
    require(read(HERE/'owner_contract.json')==checker.owner_contract(),'Source-derived owner contract')
    common.base.verify_pins(pins)
    return pins

def validate(plan,image):
    require(image==IMAGE and plan['status']=='PREPARED_NOT_RUN' and plan['image']==str(IMAGE) and
        plan['image_sha256']==sha(IMAGE/'image.json'),'Exact frozen M9 image')
    require(plan['cases']==scope() and plan['jobs']==1 and plan['case_timeout_s']==10800 and
        plan['worker_timeout_s']==12000 and plan['service_timeout_s']==13200 and plan['unit']==UNIT and
        plan['reserved_slots']==0 and all(plan[k] is True for k in ('no_build','no_retry','no_fsdb','stop_first_fail')),
        'Exact single original4095/bounds/no-retry')
    require(plan['owner_contract']==checker.owner_contract(),'Actual model owner eligibility')
    require(plan['reference_ready_sha256']==READY_SHA and plan['user_conditional_authorization'] is True,'Actual source/reference admission')
    require(plan['specs']=={SHAPE:checker.specification()},'Actual ELF spec drift')
    common.base.verify_pins(plan['pins'])
    for name in ('checker.py','replay.py','reset_profile.json','collect.py','exit_hook.py'):
        require(plan['pins'].get(str(HERE/name))==sha(HERE/name),'Consumed own worker file drift')

def prepare(image,out,reserved):
    require(image==IMAGE and not out.exists() and reserved==0,'Fresh exact own output')
    host=read(HERE/'host01.json');exit=read(HERE/'host01_process_exit.json')
    require(host['status']=='PASS_HOST_ONLY' and host['failures']==0 and host['tests']>=20 and
        host['actual_abi_entry_checked'] and host['full4095_streams']==1 and
        host['full_positive_shapes']==[SHAPE] and exit['returncode']==0 and exit['timed_out'] is False,
        'Actual full Host/ABI gate')
    actual_host_pins=dict(host['pins'])
    require(host['input_pins_pre_post_unchanged'],'Actual fullHost stable input files')
    require(actual_host_pins[str(HERE/'replay.py')]==sha(HERE/'replay.py') and
        read(HERE/'host01_command.json')['input_pins']==actual_host_pins,
        'Exact prelaunch/Host worker files unchanged')
    common.base.verify_pins(actual_host_pins)
    short=read(HERE/'short_host_result.json');numeric=read(HERE/'short_host_execution.json')
    require(short['status']=='PASS_SHORT_OWNER_AND_TERMINAL_GATES' and short['tests']==3 and
        short['pins_pre_post_unchanged'] and numeric['actual_wait_returncode']==0 and not numeric['timed_out'],
        'Actual slidedown/terminal-schema supplemental Host')
    common.base.verify_pins(short['pins'])
    pins=reference_pins();ledger,repo,_=common.image_context(image)
    require(Path(ledger['snapshot']).parent.name=='current_board_memory_candidate09','Frozen M9')
    pins.update(common.image_pins(image,ledger,repo));pins.update(actual_host_pins);pins.update(short['pins'])
    for module in list(sys.modules.values()):
        path=getattr(module,'__file__',None)
        if path and Path(path).is_file() and Path(path).resolve().is_relative_to(checker.G.parents[2]):
            pins[str(Path(path).resolve())]=sha(path)
    profile=read(HERE/'reset_profile.json');pins.update(profile['rtl_pins'])
    pins[str(HERE.parent/'full_e8_mf4_o2_vcs_m9_successor02/reset_profile.json')]=profile['authority_sha256']
    for name in ('checker.py','replay.py','reset_profile.json','collect.py','exit_hook.py','test_host.py','host_records.py',
        'run_host.py','host01.json','host01.log','host01_process_exit.json','README.md','USER_AUTHORIZATION.md','launch_once.py'):
        pins[str(HERE/name)]=sha(HERE/name)
    for name in ('host01_command.json','host01_loaded_code_preflight.json','prepare_assets.py'):
        pins[str(HERE/name)]=sha(HERE/name)
    for name in ('test_slidedown_short.py','test_terminal_gate.py','run_short_host.py','short_host_result.json',
        'short_host_execution.json','short_host_command.json','short_host.log'):
        pins[str(HERE/name)]=sha(HERE/name)
    plan=dict(status='PREPARED_NOT_RUN',image=str(image),image_sha256=sha(image/'image.json'),snapshot_sha256=ledger['snapshot_sha256'],
        cases=scope(),specs={SHAPE:checker.specification()},pins=pins,jobs=1,case_timeout_s=10800,worker_timeout_s=12000,
        service_timeout_s=13200,unit=UNIT,reserved_slots=0,no_build=True,no_retry=True,no_fsdb=True,stop_first_fail=True,
        reference_ready_sha256=READY_SHA,user_conditional_authorization=True,resources_checked_only_at_run=True,
        scope='Original e16/m2 full4095 continuous source port, not original Linux stall closure',
        owner_contract=checker.owner_contract(),cost=dict(budget_gate='FIT_PROJECTION_ONLY',conservative_projection_s=read(REF/'READY.json')['projected_seconds_20percent_margin'],
            actual_reference_firmware=1072555,not_wall_clock_guarantee=True))
    validate(plan,image);out.mkdir();durable(out/'plan.json',plan);digest=sha(out/'plan.json')
    command=[sys.executable,'-B',str(HERE/'replay.py'),'run','--image',str(image),'--out',str(out),'--plan-sha256',digest,'--authorize-run']
    service=['systemd-run','--user','--unit='+UNIT,'--property=RuntimeMaxSec=13200','--property=TimeoutStopSec=360','--property=KillMode=control-group',
        '--property=Restart=no','--property=WorkingDirectory='+str(HERE),'--property=StandardOutput=append:'+str(out/'service.log'),
        '--property=StandardError=append:'+str(out/'service.log'),'--property=ExecStopPost='+shlex.join([
            sys.executable,'-B',str(HERE/'exit_hook.py'),'--out',str(out)]),*command]
    durable(out/'ready.json',dict(status='PREPARED_PENDING_EXACT_HILBERT_ENTRY_NO_DUT',plan_sha256=digest,command=command,
        service_command=shlex.join(service),pin_count=len(pins),DUT_started=False))
    print('PREPARED',digest,flush=True)

def terminal_disk_gate(out,digest,image):
    require(sha(out/'plan.json')==digest,'Late plan drift');validate(read(out/'plan.json'),image)

# This imported worker has a private namespace. Original sealed module/files are untouched.
core.UNIT,core.PASS,core.scope,core.validate,core.reference_pins=UNIT,PASS,scope,validate,reference_pins
core.terminal_disk_gate=terminal_disk_gate
core.monitored_with_outcome=monitored_with_outcome
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
