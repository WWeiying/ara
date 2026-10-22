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
UNIT='ara-arithmetic-original-e8-m8-full4095-m9-01.service'
PASS='PASS_M9_FULL_ORIGINAL_E8_M8_4095_CALLS_NOT_LINUX'
durable=core.durable
monitored_with_outcome=core.monitored_with_outcome
checked_runner=core.checked_runner
owner_gate=core.owner_gate

def scope():
    spec=checker.specification()
    return [dict(id=checker.ID,original_name=SHAPE,shape=SHAPE,elf=spec['backend']['elf'],
        sha256=checker.ELF_SHA,timeout_s=CASE_BOUND,pass_markers=[checker.marker()])]

def reference_pins():
    require(sha(REF/'READY.json')==READY_SHA,'Accepted full source READY')
    ready=read(REF/'READY.json');result=read(REF/'reference01/result.json')
    require(ready['status']=='REFERENCE_FULL4095_PASS_SOFTWARE_ONLY_NOT_DUT' and
        [ready[k] for k in ('calls','results','guards','returned_vstart_zero','helper_instructions')]==
        [4095,4193280,8190,4095,53235] and ready['firmware']==2825046 and
        ready['reference_attempts']==1 and ready['DUT_runs']==0 and ready['source_pins_unchanged'] is True,
        'Full original e8m8 software/ref scope')
    require(sha(REF/'reference01/result.json')==ready['reference_sha256'] and
        sha(REF/'entry.json')==ready['entry_sha256'] and result['pins_unchanged'] is True and
        result['raw_parse_count']==result['closed_raw_parses']==1 and result['packed_output_reads']==528255 and
        result['physical_mask_bytes']==128,'Full original raw observer/entry identity')
    pins=dict(read(REF/'reference01/preflight_pins.json'))
    for name,limit in (('execution.json',120),('audit_execution.json',600)):
        outcome=read(REF/'reference01'/name)
        require(type(outcome['returncode']) is int and outcome['returncode']==0 and
            outcome['timeout'] is False and outcome['retries']==0 and outcome['elapsed_s']<=limit,
            'Actual reference/parser numeric child exit')
    for path in (REF/'READY.json',REF/'reference01/result.json',REF/'reference01/execution.json',
        REF/'reference01/audit_execution.json',REF/'reference01/command.json',
        REF/'reference01/audit_command.json',REF/'reference01/preflight_pins.json',REF/'REFERENCE_RESULT.md'):
        pins[str(path)]=sha(path)
    pins[str(REF/'reference01/commits.log')]=result['raw_sha256']
    common.base.verify_pins(pins)
    return pins

def validate(plan,image):
    require(image==IMAGE and plan['status']=='PREPARED_NOT_RUN' and plan['image']==str(IMAGE) and
        plan['image_sha256']==sha(IMAGE/'image.json'),'Exact frozen M9 image')
    require(plan['cases']==scope() and plan['jobs']==1 and plan['case_timeout_s']==10800 and
        plan['worker_timeout_s']==12000 and plan['service_timeout_s']==13200 and plan['unit']==UNIT and
        type(plan['reserved_slots']) is int and 0<=plan['reserved_slots']<=24 and all(plan[k] is True for k in ('no_build','no_retry','no_fsdb','stop_first_fail')),
        'Exact single original4095/bounds/no-retry')
    require(plan['reference_ready_sha256']==READY_SHA and plan['user_conditional_authorization'] is True,'Actual source/reference admission')
    require(plan['specs']=={SHAPE:checker.specification()} and plan['owner_counts']==checker.owner_counts(),'Actual ELF spec/model owner drift')
    common.base.verify_pins(plan['pins'])
    for name in ('checker.py','replay.py','reset_profile.json','collect.py','exit_hook.py'):
        require(plan['pins'].get(str(HERE/name))==sha(HERE/name),'Consumed own worker file drift')

def prepare(image,out,reserved):
    require(image==IMAGE and not out.exists() and type(reserved) is int and 0<=reserved<=24,'Fresh exact own output')
    host=read(HERE/'host02.json');exit=read(HERE/'host02_process_exit.json')
    require(host['status']=='FAIL_HOST_ONLY' and host['failures']==1 and host['tests']==23 and
        host['full4095_streams']==1 and type(exit['returncode']) is int and exit['returncode']==1 and
        exit['timed_out'] is False and exit['pins_unchanged'] is True,'Preserved complete Host02 outcome')
    log=(HERE/'host02.log').read_text()
    require(log.count(' ... ok')==22 and log.count(' ... FAIL')==1 and
        'test_full4095_complete_data (test_host.Host) ... ok' in log and
        'test_actual_elf_abi (test_host.Host) ... ok' in log and
        'test_middle_sh_not_completion (test_host.Host) ... FAIL' in log and
        'ValueError: Actual source initialized values out' in log and
        'does not match' in log,'Only documented negative-message mismatch; no other failure')
    focused=read(HERE/'host_negative03.json');focused_exit=read(HERE/'host_negative03_exit.json')
    require(focused['status']=='PASS_FOCUSED_HOST_NEGATIVES_NOT_DUT' and focused['tests']==2 and
        focused['failures']==0 and type(focused_exit['returncode']) is int and focused_exit['returncode']==0 and
        focused_exit['timed_out'] is False and focused_exit['pins_unchanged'] is True,
        'Actual two semantic successor negatives; no relaxed checker')
    actual_host_pins=dict(host['pins'])
    original_host_worker=HERE/'host02_code/replay.py'
    require(sha(original_host_worker)==actual_host_pins.pop(str(HERE/'replay.py')),'Preserved actual Host02 worker')
    actual_host_pins[str(original_host_worker)]=sha(original_host_worker)
    actual_host_pins.update(focused['pins'])
    common.base.verify_pins(actual_host_pins)
    pins=reference_pins();ledger,repo,_=common.image_context(image)
    require(Path(ledger['snapshot']).parent.name=='current_board_memory_candidate09','Frozen M9')
    pins.update(common.image_pins(image,ledger,repo));pins.update(actual_host_pins)
    for module in list(sys.modules.values()):
        path=getattr(module,'__file__',None)
        if path and Path(path).is_file() and Path(path).resolve().is_relative_to(checker.G.parents[2]):
            pins[str(Path(path).resolve())]=sha(path)
    profile=read(HERE/'reset_profile.json');pins.update(profile['rtl_pins'])
    pins[str(HERE.parent/'full_e8_mf4_o2_vcs_m9_successor02/reset_profile.json')]=profile['authority_sha256']
    for name in ('checker.py','replay.py','reset_profile.json','collect.py','exit_hook.py','test_host.py','host_records.py',
        'host_successor02.py','host02.json','host02.log','host02_process_exit.json','README.md','USER_AUTHORIZATION.md','launch_once.py','HOST_HISTORY.md',
        'run_host.py','host01.log','host01_command.json','host01_process_exit.json','host01_code/replay.py',
        'host02_code/replay.py','host02_command.json','host_negative03.py','host_negative03.json',
        'host_negative03_exit.json','host_negative03_command.json','host_negative03.log'):
        pins[str(HERE/name)]=sha(HERE/name)
    plan=dict(status='PREPARED_NOT_RUN',image=str(image),image_sha256=sha(image/'image.json'),snapshot_sha256=ledger['snapshot_sha256'],
        cases=scope(),specs={SHAPE:checker.specification()},owner_counts=checker.owner_counts(),pins=pins,jobs=1,case_timeout_s=10800,worker_timeout_s=12000,
        service_timeout_s=13200,unit=UNIT,reserved_slots=reserved,no_build=True,no_retry=True,no_fsdb=True,stop_first_fail=True,
        reference_ready_sha256=READY_SHA,user_conditional_authorization=True,resources_checked_only_at_run=True,
        scope='Original e8/m8 full4095 continuous source port, not original Linux stall closure',
        cost=dict(budget_gate='FIT_PROJECTION_ONLY',conservative_projection_s=read(REF/'READY.json')['projected_seconds_20percent_margin'],
            actual_reference_firmware=2825046,not_wall_clock_guarantee=True))
    validate(plan,image);out.mkdir();durable(out/'plan.json',plan);digest=sha(out/'plan.json')
    command=[sys.executable,'-B',str(HERE/'replay.py'),'run','--image',str(image),'--out',str(out),'--plan-sha256',digest,'--authorize-run']
    service=['systemd-run','--user','--unit='+UNIT,'--property=RuntimeMaxSec=13200','--property=TimeoutStopSec=360','--property=KillMode=control-group',
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
