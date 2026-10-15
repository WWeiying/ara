"""Preparation-only by default; mature single-job numeric-first M9 worker."""
import argparse,json,os,shlex,sys,time
from pathlib import Path
import checker
from checker import HERE,REF,REFERENCE,SOURCE,READY_SHA,SHAPES,SHAPE,read,sha,require,common
core=checker.load('sentinel_private_mature_worker',HERE.parent/'full_e8_mf4_o2_vcs_m9_successor02/replay.py')
IMAGE=core.IMAGE
JOBS,CASE_BOUND,WORKER_BOUND,OUTER=1,10800,12000,13200
UNIT='ara-arithmetic-original-e16-m8-sentinel-full4095-m9-01.service'
PASS='PASS_M9_FULL_ORIGINAL_E16_M8_SENTINEL_4095_CALLS_NOT_LINUX'
WATCHDOG='+COMMIT_WATCHDOG=1000000'
durable=core.durable;numeric_monitor=core.monitored_with_outcome
checked_runner=core.checked_runner;owner_gate=core.owner_gate
def monitored_with_outcome(original,abort):
    wrapped=numeric_monitor(original,abort)
    def monitored(command,cwd,console,timeout,cancel_event=None):
        root=Path(console).parent;record=read(root/'command.json')
        require(record['command']==[str(x) for x in command] and record['cwd']==str(cwd),'Actual generic command identity')
        require(not any(str(x).startswith('+COMMIT_WATCHDOG') for x in command),'No duplicate diagnostic')
        command=[*command,WATCHDOG];durable(root/'generic_command.before_diagnostic.json',record)
        record['command']=[str(x) for x in command]
        with (root/'command.json').open('w') as f:
            json.dump(record,f,indent=2);f.flush();os.fsync(f.fileno())
        print('PHASE actual_monitor START watchdog=1000000',flush=True)
        outcome=wrapped(command,cwd,console,timeout,cancel_event)
        print('PHASE actual_monitor SAVED rc='+str(outcome[0]),flush=True)
        return outcome
    return monitored
def scope():
    spec=checker.specification()
    return [dict(id=checker.ID,original_name=SHAPE,shape=SHAPE,elf=spec['backend']['elf'],
        sha256=checker.ELF_SHA,timeout_s=CASE_BOUND,pass_markers=[checker.marker()])]
def reference_pins():
    require(sha(REFERENCE/'READY.json')==READY_SHA,'Original new producer READY')
    ready=read(REFERENCE/'READY.json')
    path=HERE.parent/'m8_sentinel_mask_static_review_hilbert01/REFERENCE_COMBINED_TERMINAL_REVIEW.json'
    require(sha(path)=='0c48ae6f4f264edabe6521e521e82e330c2ae7621f3c95ff54b3447ac043d244','Actual independent combined review')
    review=read(path)
    require(review['status']=='ACCEPTED_REFERENCE_ONLY_NOT_DUT' and not review['blocking_findings']
        and review['original_READY_sha256']==READY_SHA and not review['DUT_authorized'],'Reference acceptance, not launch permission')
    require([ready[k] for k in ('calls','results','guards','returned_vstart_zero','helper_instructions','packed_output_reads')]==
        [4095,2096640,8190,4095,53235,528255] and ready['firmware']==2540955<=3000000
        and ready['reference_attempts']==1 and ready['DUT_runs']==0,'Complete source/reference cost')
    supplement=REFERENCE/'capacity_supplement01'
    require(sha(supplement/'READY.json')==review['supplement_READY_sha256']
        and sha(supplement/'result.json')==review['supplement_result_sha256']
        and sha(REFERENCE/'reference01/result.json')==review['reference_result_sha256'],'Original audit + capacity pins')
    pins=dict(read(supplement/'READY.json')['pins'])
    for p in (path,supplement/'READY.json'):pins[str(p)]=sha(p)
    common.base.verify_pins(pins)
    return pins
def validate(plan,image):
    require(image==IMAGE and plan['status']=='PREPARED_NOT_RUN' and plan['image']==str(image)
        and plan['image_sha256']==sha(image/'image.json'),'Exact frozen M9')
    require(plan['cases']==scope() and plan['jobs']==1 and plan['case_timeout_s']==10800
        and plan['worker_timeout_s']==12000 and plan['service_timeout_s']==13200 and plan['unit']==UNIT
        and plan['reserved_slots']==0 and all(plan[k] is True for k in ('no_build','no_retry','no_fsdb','stop_first_fail')),'Exact scope/bounds')
    require(plan['reference_ready_sha256']==READY_SHA and plan['owner_contract']==checker.owner_contract()
        and plan['specs']=={SHAPE:checker.specification()} and plan['diagnostic_plusargs']==[WATCHDOG]
        and plan['cost']==read(HERE/'runtime_basis.json'),'Exact source/owner/diagnostic/runtime basis')
    common.base.verify_pins(plan['pins'])
def reviews(plan,digest,entry_path,entry_sha,parent_path,parent_sha):
    require(entry_path and entry_sha and sha(entry_path)==entry_sha,'Actual independent worker entry')
    entry=read(entry_path)
    require(entry['status']=='NO_BLOCKER_ENTRY_REVIEW' and entry['plan_sha256']==digest
        and entry['image_sha256']==plan['image_sha256'] and entry['reference_ready_sha256']==READY_SHA
        and entry['scope']==[checker.ID] and entry['pins']==plan['pins'],'Actual independent exact binding')
    require(parent_path and parent_sha and sha(parent_path)==parent_sha,'New explicit parent approval required')
    parent=read(parent_path)
    require(parent['status']=='APPROVED_ONCE' and parent['plan_sha256']==digest
        and parent['entry_review_sha256']==entry_sha and parent['runtime_risk_accepted'] is True
        and parent['case_timeout_s']==10800,'Preparation is not automatic launch admission')
    return {str(entry_path):entry_sha,str(parent_path):parent_sha}
def prepare(image,out,reserved):
    require(image==IMAGE and not out.exists() and reserved==0,'Own fresh preparation/reserved0')
    host=read(HERE/'host01.json');execution=read(HERE/'host01_process_exit.json')
    require(host['status']=='PASS_HOST_ONLY' and host['failures']==0 and host['tests']>=23
        and host['actual_abi_entry_checked'] and host['full4095_streams']==1
        and host['full_positive_shapes']==[SHAPE] and execution['returncode']==0
        and not execution['timed_out'],'Actual new full Host gate')
    common.base.verify_pins(host['pins'])
    short=read(HERE/'preflight_result.json')
    require(short['status']=='PASS_SHORT_NEW_SOC_PREFLIGHT' and short['ELF_sha256']==checker.ELF_SHA,'Actual short new ABI/marker')
    pins=reference_pins();ledger,repo,_=common.image_context(image)
    require(Path(ledger['snapshot']).parent.name=='current_board_memory_candidate09','Frozen M9')
    pins.update(common.image_pins(image,ledger,repo));pins.update(host['pins'])
    for module in list(sys.modules.values()):
        path=getattr(module,'__file__',None)
        if path and Path(path).is_file() and Path(path).resolve().is_relative_to(checker.G.parents[2]):
            pins[str(Path(path).resolve())]=sha(path)
    profile=read(HERE/'reset_profile.json');pins.update(profile['rtl_pins'])
    for p in (REF/'model.py',HERE.parent/'full_e16_mf4_prepare01/model.py',
        HERE.parent/'full_e8_mf4_o2_vcs_m9_successor02/reset_profile.json'):
        pins[str(p)]=sha(p)
    pins.update(read(HERE/'soc_profile.json')['source_inputs'])
    for p in HERE.iterdir():
        if p.is_file():pins[str(p.resolve())]=sha(p)
    plan=dict(status='PREPARED_NOT_RUN',image=str(image),image_sha256=sha(image/'image.json'),
        snapshot_sha256=ledger['snapshot_sha256'],cases=scope(),specs={SHAPE:checker.specification()},
        pins=pins,jobs=1,case_timeout_s=10800,worker_timeout_s=12000,service_timeout_s=13200,unit=UNIT,
        reserved_slots=0,no_build=True,no_retry=True,no_fsdb=True,stop_first_fail=True,
        reference_ready_sha256=READY_SHA,user_conditional_authorization=False,
        resources_checked_only_at_run=True,owner_contract=checker.owner_contract(),
        diagnostic_plusargs=[WATCHDOG],cost=read(HERE/'runtime_basis.json'),
        scope='Full original4095 sentinel successor; not Linux historical stall closure')
    validate(plan,image);out.mkdir();durable(out/'plan.json',plan);digest=sha(out/'plan.json')
    command=[sys.executable,'-B',str(HERE/'replay.py'),'run','--image',str(image),'--out',str(out),
        '--plan-sha256',digest,'--authorize-run']
    service=['systemd-run','--user','--unit='+UNIT,'--property=RuntimeMaxSec=13200',
        '--property=TimeoutStopSec=360','--property=KillMode=control-group','--property=Restart=no',
        '--property=WorkingDirectory='+str(HERE),'--property=StandardOutput=append:'+str(out/'service.log'),
        '--property=StandardError=append:'+str(out/'service.log'),'--property=ExecStopPost='+shlex.join(
            [sys.executable,'-B',str(HERE/'exit_hook.py'),'--out',str(out)]),*command]
    durable(out/'ready.json',dict(status='PREPARED_PENDING_HILBERT_AND_PARENT_RUNTIME_NO_DUT',
        plan_sha256=digest,command=command,service_command=shlex.join(service),pin_count=len(pins),DUT_started=False))
    print('PREPARED',digest,flush=True)
def terminal_disk_gate(out,digest,image):
    require(sha(out/'plan.json')==digest,'Late plan drift');validate(read(out/'plan.json'),image)
core.UNIT,core.PASS,core.scope,core.validate,core.reference_pins=UNIT,PASS,scope,validate,reference_pins
core.HERE,core.REF,core.READY_SHA,core.SHAPES=HERE,REF,READY_SHA,SHAPES
core.reviews=reviews;core.monitored_with_outcome=monitored_with_outcome;core.terminal_disk_gate=terminal_disk_gate
def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','dryrun','run'))
    for n in ('image','out'):p.add_argument('--'+n,type=Path,required=True)
    for n in ('authorize-prepare','authorize-run'):p.add_argument('--'+n,action='store_true')
    p.add_argument('--reserved-slots',type=int,default=0)
    for n in ('plan-sha256','entry-review-sha256','parent-review-sha256'):p.add_argument('--'+n)
    for n in ('entry-review','parent-review'):p.add_argument('--'+n,type=Path)
    args=p.parse_args();image,out=args.image.resolve(),args.out.resolve()
    require(out.parent==HERE,'Owned direct-child output')
    if args.mode=='prepare':
        require(args.authorize_prepare,'Explicit prepare');prepare(image,out,args.reserved_slots);return 0
    if args.mode=='dryrun':
        require(sha(out/'plan.json')==args.plan_sha256,'Exact dryrun plan');validate(read(out/'plan.json'),image)
        ledger,_,_=common.image_context(image);case=scope()[0];root=out/'replay/tests'/case['id']
        durable(out/'dryrun.json',dict(status='DRYRUN_ONLY_NO_PROCESS',plan_sha256=args.plan_sha256,
            commands=[dict(cwd=str(root/'work'),command=[ledger['simv'],'-l','run.vcs.log',
                '+ntb_random_seed=1','+PRELOAD='+str(root/'input.elf'),'+TESTCASE='+case['id'],
                '+NO_FSDB','+COMMIT_TRACE='+str(root/'commit_trace.csv'),WATCHDOG])]))
        print('DRYRUN_ONLY_NO_PROCESS');return 0
    env=common.base.shared.environment();os.environ.clear();os.environ.update(env)
    return core.run(image,out,args.plan_sha256,args.authorize_run,args.entry_review,args.entry_review_sha256,
        args.parent_review,args.parent_review_sha256)
if __name__=='__main__':raise SystemExit(main())
