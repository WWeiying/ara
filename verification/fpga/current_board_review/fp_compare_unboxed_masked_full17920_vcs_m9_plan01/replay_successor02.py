"""Masked bindings around the actual mature successor02 worker/local engine hook."""
from scope import *
from shared import module
runtime=module('masked17920_shared_worker','replay_successor02.py')


def reference_pins():
    require(sha(REVIEW)==REVIEW_SHA and sha(FPR_REVIEW)==FPR_REVIEW_SHA,'Accepted reference/FPR chain')
    review=read(REVIEW);root=REF/'run01';complete=read(root/'COMPLETE.json')
    require(review['status']=='ACCEPTED_MASKED_FULL17920_REFERENCE_ONLY_NOT_DUT' and review['accepted'] is True,
        'Actual masked reference acceptance')
    bindings={root/'COMPLETE.json':review['complete_sha256'],root/'audit01/result.json':review['audit_result_sha256'],
        root/'spike.wait.json':review['spike_wait_sha256'],root/'audit.wait.json':review['audit_wait_sha256']}
    for p,h in bindings.items():require(sha(p)==h,'Actual reference receipt pin')
    require(complete['pins_unchanged'] is True and complete['attempts']==1,'Exactly one complete reference')
    result=complete['result']
    require([result[k] for k in ('calls','result_bits','guards','flags','vstarts','helper_instructions','stores','input_LD','output_LWU','record_LD')]
        ==[17920,286720,35840,17920,17920,326144,734720,143360,17920,8960], 'Actual masked full scope')
    require(result['firmware_to_HTIF']==2780558 and result['EOF_pure_park'] is True and
        result['closed_raw_parses']==1 and result['raw_sha256']==review['recorded_raw_sha256'],'Closed reference identity')
    for p in (root/'spike.wait.json',root/'audit.wait.json'):
        r=read(p);require(type(r['actual_wait_exit'])is int and r['actual_wait_exit']==0 and r['timed_out'] is False,'Actual numeric reference exits')
    pins=runtime.merge_pins(read(REF/'input_pins.json'),read(PREP/'SOFTWARE_READY.json')['pins'],
        {str(p):h for p,h in bindings.items()})
    fpr=read(FPR_REVIEW)
    pins=runtime.merge_pins(pins,{str(Path(fpr['frozen_root'])/p):h for p,h in fpr['source_pins'].items()})
    for p in (REVIEW,REVIEW.with_suffix('.md'),FPR_REVIEW,FPR_REVIEW.with_suffix('.md'),
        PREP/'SOFTWARE_READY.json',REF/'input_pins.json',REF/'ENTRY.json'):
        pins=runtime.merge_pins(pins,{str(p):sha(p)})
    return pins


def validate(plan):
    require(plan['status']=='PREPARED_NOT_RUN' and plan['cases']==runtime.cases() and plan['image']==str(IMAGE)
        and plan['image_sha256']==sha(IMAGE/'image.json')==IMAGE_SHA,'Exact masked case/image/ELF')
    require((plan['jobs'],plan['case_timeout_s'],plan['worker_timeout_s'],plan['service_timeout_s'],plan['unit'],plan['reserved_slots'])
        ==(1,10800,12000,13200,UNIT,0),'Fixed contract')
    require(plan['service_terminal_contract']==runtime.service_contract() and
        plan['detail_monitor']==runtime.detail_monitor.contract(),'Actual local automatic hook/monitor')
    require(plan['spec']==runtime.specification() and plan['owner_contract']==runtime.owner_contract(),'Source-derived new spec/owners')
    require(all(plan[k] is True for k in ('no_build','no_retry','no_fsdb','stop_first_fail','numeric_before_postcheck')),'Restrictions')
    host=read(runtime.HOST);wait=read(HERE/'host.wait.json')
    require(host['status']=='PASS_HOST_ONLY_NOT_DUT' and host['failures']==host['errors']==0 and
        wait['actual_wait_exit']==0 and wait['timed_out'] is False,'Actual necessary Host outcome')
    expected=runtime.merge_pins(reference_pins(),runtime.owned_pins(),host['pins'])
    require(all(plan['pins'].get(p)==h for p,h in expected.items()),'All consumed pins membership')
    runtime.common.base.verify_pins(plan['pins'])


def approval_gate(out,digest,entry,entrysha,parent,parentsha):
    require(entry==runtime.ENTRY and sha(entry)==entrysha,'Actual independent entry')
    e=read(entry)
    require(e['decision']=='NO_BLOCKER_MASKED_FULL17920_M9_ENTRY' and e['plan_sha256']==digest and
        e['worker_sha256']==sha(HERE/'replay_successor02.py') and e['checker_sha256']==sha(HERE/'checker.py') and
        e['strict_sha256']==sha(HERE/'strict.py') and e['reference_review_sha256']==REVIEW_SHA,'Exact entry binding')
    require(parent and sha(parent)==parentsha,'Separate parent launch permission')
    p=read(parent)
    require(p['decision']=='AUTHORIZE_MASKED_FULL17920_M9_ONCE' and p['plan_sha256']==digest and
        p['entry_sha256']==entrysha and p['unit']==UNIT and p['budget_s']==[10800,12000,13200] and p['jobs']==1,
        'Preparation is not launch authority')
    return {str(entry):entrysha,str(parent):parentsha}


def prepare(out):
    require(out.parent==HERE and not out.exists(),'Fresh owned output')
    ledger,repo,_=runtime.common.image_context(IMAGE)
    require(sha(IMAGE/'image.json')==IMAGE_SHA,'Frozen M9')
    host=read(runtime.HOST)
    pins=runtime.merge_pins(reference_pins(),runtime.owned_pins(),host['pins'],runtime.common.image_pins(IMAGE,ledger,repo))
    for name in ('host.json','host.wait.json','host.log','host.command.json'):
        pins=runtime.merge_pins(pins,{str(HERE/name):sha(HERE/name)})
    plan=dict(status='PREPARED_NOT_RUN',cases=runtime.cases(),spec=runtime.specification(),owner_contract=runtime.owner_contract(),
        image=str(IMAGE),image_sha256=IMAGE_SHA,snapshot_sha256=ledger['snapshot_sha256'],pins=pins,
        jobs=1,case_timeout_s=10800,worker_timeout_s=12000,service_timeout_s=13200,unit=UNIT,reserved_slots=0,
        max_live_simv=24,min_available_GiB=32,no_build=True,no_retry=True,no_fsdb=True,
        stop_first_fail=True,numeric_before_postcheck=True,full_parent=True,linux=False,
        scope='Original masked17920 contiguous/full bits+guards+flags+vstart/fresh/FPR; not unmasked substitute',
        service_terminal_contract=runtime.service_contract(),detail_monitor=runtime.detail_monitor.contract(),
        reference_raw_identity={k:read(REF/'run01/COMPLETE.json')['result'][k] for k in ('raw_sha256','raw_bytes')},
        launch_gate='Independent exact entry plus separate actual parent launch record; parent will launch')
    validate(plan);out.mkdir();runtime.durable(out/'plan.json',plan);digest=sha(out/'plan.json')
    command=[sys.executable,'-B',str(HERE/'replay_successor02.py'),'run','--out',str(out),'--plan-sha256',digest,
        '--entry-review',str(runtime.ENTRY),'--entry-sha256','__ACTUAL_INDEPENDENT_ENTRY_SHA__',
        '--parent-review','__NEW_PARENT_RUN_JSON__','--parent-sha256','__ACTUAL_PARENT_SHA__']
    import shlex
    service=['systemd-run','--user','--unit='+UNIT,'--property=Type=exec','--property=RemainAfterExit=no',
        '--property=TimeoutStopSec=300','--property=RuntimeMaxSec=13200','--property=KillMode=control-group','--property=Restart=no',
        '--property=WorkingDirectory='+str(HERE),'--property=StandardOutput=append:'+str(out/'service.log'),
        '--property=StandardError=append:'+str(out/'service.log'),
        '--property=ExecStopPost='+shlex.join([sys.executable,'-B',str(HERE/'exit_hook_successor.py'),'--out',str(out)]),*command]
    runtime.durable(out/'ready.json',dict(status='PREPARED_PENDING_INDEPENDENT_ENTRY_NO_LAUNCH',plan_sha256=digest,
        service_argv=service,service_command=shlex.join(service),DUT_started=False))
    print('PREPARED_NOT_LAUNCHED',digest,flush=True)


runtime.reference_pins=reference_pins;runtime.validate=validate;runtime.prepare=prepare;runtime.approval_gate=approval_gate
runtime.HOST=HERE/'host.json'
if __name__=='__main__':raise SystemExit(runtime.main())
else:sys.modules[__name__]=runtime
