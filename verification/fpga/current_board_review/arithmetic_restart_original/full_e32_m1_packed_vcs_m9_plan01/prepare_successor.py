"""Narrow prepare successor: preserve Host01 FAIL and reconcile one diagnostic."""
from replay import *
def prepare(image,out,reserved):
    require(image==IMAGE and not out.exists() and type(reserved) is int and 0<=reserved<=24,'Fresh exact own output')
    import host_correction02 as correction
    statuses=correction.original_gate()
    host=read(HERE/'host_reconciled.json');outcome=read(HERE/'host02_exit.json')
    require(host['status']=='HOST_RECONCILED_PASS_ORIGINAL_HOST01_RC1' and
        host['original_returncode']==1 and host['original_outcomes']==statuses and
        host['corrected_negative']==correction.FAILED and host['tests']==33 and
        host['full5985_streams']==1 and host['full_positive_shapes']==[SHAPE] and
        host['actual_abi_entry_checked'] is True and host['no_checker_change'] is True and
        host['no_full_replay'] is True and host['correction_returncode']==0 and
        type(outcome['returncode']) is int and outcome['returncode']==0 and
        outcome['timed_out'] is False and outcome['pins_unchanged'] is True and
        outcome['retries']==0,'Explicit corrected negative actual exit and original full positive')
    require(host['correction_result_sha256']==sha(HERE/'host02_result.json') and
        read(HERE/'host02_result.json')['status']=='CORRECTED_NEGATIVE_PASS_NO_CHECKER_CHANGE',
        'Exact correction result')
    actual_host_pins=dict(host['pins']);common.base.verify_pins(actual_host_pins)
    for name in ('prepare_successor.py','host_correction02.py','run_host_correction02.py',
        'host02_command.json','host02.log','host02_result.json','host02_exit.json',
        'host_reconciled.json','HOST_DIAGNOSTIC_CORRECTION.md'):
        actual_host_pins[str(HERE/name)]=sha(HERE/name)
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
        'host01.json','host01.log','host01_process_exit.json','README.md','USER_AUTHORIZATION.md','launch_once.py','lifecycle.py',
        'run_host.py','host01_command.json','prepare_assets.py'):
        pins[str(HERE/name)]=sha(HERE/name)
    plan=dict(status='PREPARED_NOT_RUN',image=str(image),image_sha256=sha(image/'image.json'),snapshot_sha256=ledger['snapshot_sha256'],
        cases=scope(),specs={SHAPE:checker.specification()},owner_counts=checker.owner_counts(),pins=pins,jobs=1,case_timeout_s=10800,worker_timeout_s=12000,
        service_timeout_s=13200,unit=UNIT,reserved_slots=reserved,no_build=True,no_retry=True,no_fsdb=True,stop_first_fail=True,
        reference_ready_sha256=READY_SHA,user_conditional_authorization=True,resources_checked_only_at_run=True,
        host_reconciliation=dict(original_host_returncode=1,corrected_negative_returncode=0,full_history_runs=1),
        scope='Original e32/m1 full5985 continuous source port, not original Linux stall closure',
        cost=dict(budget_gate='FIT_PROJECTION_ONLY',conservative_projection_s=read(REF/'READY.json')['projected_seconds_20percent_margin'],
            actual_reference_firmware=2472244,not_wall_clock_guarantee=True))
    validate(plan,image);out.mkdir();durable(out/'plan.json',plan);digest=sha(out/'plan.json')
    command=[sys.executable,'-B',str(HERE/'replay.py'),'run','--image',str(image),'--out',str(out),'--plan-sha256',digest,'--authorize-run']
    service=['systemd-run','--user','--unit='+UNIT,'--property=RuntimeMaxSec=13200','--property=TimeoutStopSec=360','--property=KillMode=control-group',
        '--property=Restart=no','--property=WorkingDirectory='+str(HERE),'--property=StandardOutput=append:'+str(out/'service.log'),
        '--property=StandardError=append:'+str(out/'service.log'),'--property=ExecStopPost='+shlex.join([
            sys.executable,'-B',str(HERE/'exit_hook.py'),'--out',str(out)]),*command]
    durable(out/'ready.json',dict(status='PREPARED_PENDING_EXACT_AVERROES_ENTRY_NO_DUT',plan_sha256=digest,command=command,
        service_command=shlex.join(service),pin_count=len(pins),DUT_started=False))
    print('PREPARED',digest,flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--image',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--reserved-slots',type=int,default=0)
    parser.add_argument('--authorize-prepare',action='store_true')
    args=parser.parse_args()
    require(args.authorize_prepare and args.out.resolve().parent==HERE,'Explicit owned prepare')
    prepare(args.image.resolve(),args.out.resolve(),args.reserved_slots)
