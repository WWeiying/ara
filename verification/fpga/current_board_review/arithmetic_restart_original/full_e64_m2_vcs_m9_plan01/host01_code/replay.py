#!/usr/bin/env python3
"""Single full5985 M9 successor, mature numeric-first engine, never builds."""
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
core=checker.load('full5985_private_mature_worker',CORE_PATH)
IMAGE=core.IMAGE
JOBS,CASE_BOUND,WORKER_BOUND,OUTER=1,10800,12000,13200
UNIT='ara-arithmetic-original-e64-m2-full5985-m9-01.service'
PASS='PASS_M9_FULL_ORIGINAL_E64_M2_5985_CALLS_NOT_LINUX'
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
    require(sha(REF/'READY.json')==READY_SHA,'Exact accepted reference READY')
    ready=read(REF/'READY.json')
    require(ready['status']=='REFERENCE_FULL5985_PASS_SOFTWARE_ONLY_NOT_DUT' and
        [ready[k] for k in ('calls','results','guards','returned_vstart_zero','helper_instructions','packed_output_reads','FP_calls','FP_input_scalar_writes')]==[5985,191520,11970,5985,77805,203490,1890,120960] and
        ready['firmware']==2263782 and ready['reference_attempts']==1 and ready['source_pins_unchanged'] and ready['DUT_runs']==0,'Actual full5985 scope')
    pins=dict(read(REF/'reference01/preflight_pins.json'))
    require(sha(REF/'entry.json')==ready['entry_sha256'] and sha(REF/'reference01/result.json')==ready['reference_sha256'],'Actual reference artifacts')
    for n,limit in (('execution.json',120),('audit_execution.json',600)):
        x=read(REF/'reference01'/n);require(type(x['returncode'])is int and x['returncode']==0 and not x['timeout'] and x['retries']==0 and 0<x['elapsed_s']<=limit,'Actual numeric source reference')
    binding=read(HERE/'reference_terminal_binding.json')
    checker.load('actual_e64_m2_terminal_schema',HERE/'terminal_gate.py').verify(binding,ready)
    pins[binding['path']]=binding['sha256']
    for p in (REF/'READY.json',REF/'entry.json',REF/'reference01/result.json',REF/'reference01/execution.json',
        REF/'reference01/audit_execution.json',REF/'reference01/preflight_pins.json',HERE/'reference_terminal_binding.json',
        HERE/'terminal_gate.py',HERE/'owner_policy.py',HERE/'owner_contract02.json'):
        pins[str(p)]=sha(p)
    require(sha(checker.eligibility.DISPATCHER)==checker.eligibility.DISPATCHER_SHA,'Exact M9 no-op RTL decode')
    pins[str(checker.eligibility.DISPATCHER)]=checker.eligibility.DISPATCHER_SHA
    require(read(HERE/'owner_contract02.json')==checker.owner_contract(),'Full source-derived owner contract')
    common.base.verify_pins(pins);return pins

def validate(plan,image):
    require(image==IMAGE and plan['status']=='PREPARED_NOT_RUN' and plan['image']==str(IMAGE) and
        plan['image_sha256']==sha(IMAGE/'image.json'),'Exact frozen M9 image')
    require(plan['cases']==scope() and plan['jobs']==1 and plan['case_timeout_s']==10800 and
        plan['worker_timeout_s']==12000 and plan['service_timeout_s']==13200 and plan['unit']==UNIT and
        plan['reserved_slots']==0 and all(plan[k] is True for k in ('no_build','no_retry','no_fsdb','stop_first_fail')),
        'Exact single original5985/bounds/no-retry')
    require(plan['owner_contract']==checker.owner_contract(),'Actual model owner eligibility')
    require(plan['reference_ready_sha256']==READY_SHA and plan['user_conditional_authorization'] is True,'Actual source/reference admission')
    require(plan['specs']=={SHAPE:checker.specification()},'Actual ELF spec drift')
    common.base.verify_pins(plan['pins'])
    for name in ('checker.py','replay.py','reset_profile.json','collect.py','exit_hook.py'):
        require(plan['pins'].get(str(HERE/name))==sha(HERE/name),'Consumed own worker file drift')

def prepare(image,out,reserved):
    require(image==IMAGE and not out.exists() and reserved==0,'Fresh exact own output')
    host=read(HERE/'host01.json');exit=read(HERE/'host01_process_exit.json')
    require(host['status']=='PASS_HOST_ONLY' and host['failures']==host['errors']==0 and host['tests']>=20 and
        host['actual_abi_entry_checked'] and host['full5985_streams']==1 and host['full_positive_shapes']==[SHAPE] and
        exit['returncode']==0 and not exit['timed_out'],'Actual full5985 Host/ABI gate')
    actual_host_pins=dict(host['pins'])
    require(host['input_pins_pre_post_unchanged'] and read(HERE/'host01_command.json')['input_pins']==actual_host_pins,'Exact Host input pins')
    common.base.verify_pins(actual_host_pins)
    pins=reference_pins();ledger,repo,_=common.image_context(image)
    require(Path(ledger['snapshot']).parent.name=='current_board_memory_candidate09','Frozen M9')
    pins.update(common.image_pins(image,ledger,repo));pins.update(actual_host_pins);
    for module in list(sys.modules.values()):
        path=getattr(module,'__file__',None)
        if path and Path(path).is_file() and Path(path).resolve().is_relative_to(checker.G.parents[2]):
            pins[str(Path(path).resolve())]=sha(path)
    profile=read(HERE/'reset_profile.json');pins.update(profile['rtl_pins'])
    pins[str(HERE.parent/'full_e8_mf4_o2_vcs_m9_successor02/reset_profile.json')]=profile['authority_sha256']
    for p in HERE.iterdir():
        if p.is_file():pins[str(p)]=sha(p)
    plan=dict(status='PREPARED_NOT_RUN',image=str(image),image_sha256=sha(image/'image.json'),snapshot_sha256=ledger['snapshot_sha256'],
        cases=scope(),specs={SHAPE:checker.specification()},pins=pins,jobs=1,case_timeout_s=10800,worker_timeout_s=12000,
        service_timeout_s=13200,unit=UNIT,reserved_slots=0,no_build=True,no_retry=True,no_fsdb=True,stop_first_fail=True,
        reference_ready_sha256=READY_SHA,user_conditional_authorization=True,resources_checked_only_at_run=True,
        scope='Original e64/m2 full5985 continuous source port, not original Linux stall closure',
        owner_contract=checker.owner_contract(),cost=dict(budget_gate='FIT_PROJECTION_ONLY',conservative_projection_s=read(REF/'READY.json')['projected_seconds_20percent_margin'],
            actual_reference_firmware=2263782,not_wall_clock_guarantee=True))
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
