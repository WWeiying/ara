"""Case binding to sealed M9 numeric-first worker; prepare/dryrun are no-run."""
import argparse
from contextlib import contextmanager
import os
import re
import shlex
import checker
from scope import *
from specification import specification,owner_contract
base=load('full6720_mature_worker',MATURE/'replay02.py')
common=base.common
durable,merge_pins=base.durable,base.merge_pins
ENTRY=HERE/'ENTRY_REVIEW.json'
HOST=HERE/'host01.wait.json'
DETAIL_PATTERN=(r'(?m:^RVV_FP_REDSPECIAL_DETAIL scenario=(?P<scenario>[0-9]+) op=(?P<op>[0-9]+)'
                r' vl=(?P<vl>[0-9]+) mask=(?P<mask>[0-9]+) frm=(?P<frm>[0-9]+)'
                r' flags=(?P<flags>[0-9]+) expected_flags=(?P<expected_flags>[0-9]+)\n)')
DETAIL=re.compile(DETAIL_PATTERN)
def monitored(original,abort,roots,simv):
    numeric_first=base.monitored(original,abort,roots,simv)
    def call(command,cwd,console,timeout,cancel_event=None):
        outcome=numeric_first(command,cwd,console,timeout,cancel_event)
        # The mature wrapper has already durably recorded the actual numeric
        # tuple and latched abort, even if reading this diagnostic fails.
        if outcome[3]:
            found=DETAIL.search(Path(console).read_text())
            if found:durable(Path(console).parent/'detail_firstfailure.json',dict(kind='COMPLETE_ORIGINAL_DETAIL',line=found[0],fields=found.groupdict()))
        return outcome
    return call
@contextmanager
def engine_hooks(engine,abort,roots,simv):
    old_monitor,old_fail=engine._run_monitored,engine.FAIL_RE
    engine._run_monitored=monitored(old_monitor,abort,roots,simv)
    engine.FAIL_RE=re.compile('(?:'+old_fail.pattern+')|'+DETAIL_PATTERN+r'|RVV_FP_REDSPECIAL_(?:FAIL|CAPACITY_FAIL)|BOARD_\w*(?:FAIL|TRAP|MISMATCH)',old_fail.flags)
    try:yield
    finally:engine._run_monitored,engine.FAIL_RE=old_monitor,old_fail
def cases():
    return [dict(id=NAME,original_name=NAME,historical_name=HISTORICAL,elf=str(ELF),sha256=ELF_SHA,timeout_s=TIMEOUT,
                 pass_markers=[MARKER,'BOARD_CASE_PASS '+NAME,'BOARD_REPLAY_PASS'])]
def reference_pins():
    require(sha(REVIEW)==REVIEW_SHA,'Actual reference terminal review')
    review=read(REVIEW);root=REF/'reference01';complete=read(root/'COMPLETE.json');result=read(root/'audit01/result.json')
    require(review['status']=='ACCEPTED_REFERENCE_ONLY_NOT_DUT' and review['accepted'] is True and review['blockers']==[],'Independent reference acceptance')
    require(sha(root/'COMPLETE.json')==review['complete_sha256'] and sha(root/'audit01/result.json')==review['audit_result_sha256'],'Actual reference terminal identity')
    require([result[k] for k in ('calls','output_bytes','flags','vstarts','helper_instructions','capacity_instructions')]==[6720,967680,6720,6720,141120,3],'Full reference scope')
    pins=read(root/'inputs_after.json');require(pins==read(root/'inputs_before.json'),'Reference unchanged pins')
    for label,p in [('spike',root/'spike.wait.json'),('audit',root/'audit.wait.json'),('controller',REF/'controller01.wait.json')]:
        v=read(p);require(type(v['actual_wait_exit']) is int and v['actual_wait_exit']==0 and not v['timed_out'] and sha(p)==review['actual_waits'][label]['receipt_sha256'],'Actual reference numeric waits')
        pins=merge_pins(pins,{str(p):sha(p)})
    for p in [REVIEW,root/'COMPLETE.json',root/'audit01/result.json',PREP/'READY.json',PREP/'linked01/soc.json']:
        pins=merge_pins(pins,{str(p):sha(p)})
    raw=complete['raw'];inherited=review['raw_identity_inherited_not_rehashed']
    require((raw['bytes'],raw['sha256'])==(inherited['bytes'],inherited['sha256']) and Path(raw['path']).stat().st_size==raw['bytes'],'Closed raw identity inherited from accepted audit')
    require(raw['path'] not in pins,'Raw must not enter repeated input hashing')
    return pins
def validate(plan):
    require(plan['status']=='PREPARED_NOT_RUN' and plan['cases']==cases() and plan['image']==str(IMAGE) and plan['image_sha256']==sha(IMAGE/'image.json')==IMAGE_SHA,'Exact scope/image/ELF')
    require((plan['jobs'],plan['case_timeout_s'],plan['worker_timeout_s'],plan['service_timeout_s'],plan['unit'],plan['reserved_slots'])==(1,10800,12000,13200,UNIT,0),'Fixed resource and budgets')
    require(plan['spec']==specification() and plan['owner_contract']==owner_contract(),'Actual SoC source/owner spec')
    require(all(plan[k] is True for k in ('no_build','no_retry','no_fsdb','stop_first_fail','numeric_before_postcheck')),'Execution restrictions')
    host=read(HOST);require(type(host['actual_wait_exit']) is int and host['actual_wait_exit']==0 and not host['timed_out'] and host['log_sha256']==sha(HERE/'host01.log'),'Actual short Host')
    mh=read(HERE/'monitor_host01.wait.json');require(type(mh['actual_wait_exit']) is int and mh['actual_wait_exit']==0 and not mh['timed_out'] and mh['log_sha256']==sha(HERE/'monitor_host01.log'),'Actual local run-hook short test')
    require(plan['detail_pattern']==DETAIL_PATTERN and plan['reference_raw_identity']==read(REF/'reference01/COMPLETE.json')['raw'],'Complete DETAIL and inherited raw contracts')
    expected=merge_pins(reference_pins(),base.owned_pins())
    require(all(plan['pins'].get(p)==h for p,h in expected.items()),'Current full pins membership');common.base.verify_pins(plan['pins'])
def prepare(out):
    require(out.parent==HERE and not out.exists(),'Fresh owned preparation')
    ledger,repo,_=common.image_context(IMAGE)
    require(sha(IMAGE/'image.json')==IMAGE_SHA and Path(ledger['snapshot']).parent.name=='current_board_memory_candidate09','Frozen M9')
    pins=merge_pins(reference_pins(),base.owned_pins(),common.image_pins(IMAGE,ledger,repo))
    for p in (HOST,HERE/'host01.log',HERE/'host01.command.json',HERE/'monitor_host01.wait.json',HERE/'monitor_host01.log',HERE/'monitor_host01.command.json'):pins=merge_pins(pins,{str(p):sha(p)})
    plan=dict(status='PREPARED_NOT_RUN',cases=cases(),spec=specification(),owner_contract=owner_contract(),image=str(IMAGE),image_sha256=IMAGE_SHA,
              snapshot_sha256=ledger['snapshot_sha256'],pins=pins,jobs=1,case_timeout_s=TIMEOUT,worker_timeout_s=WORKER,service_timeout_s=OUTER,
              unit=UNIT,reserved_slots=0,max_live_simv=24,min_available_GiB=32,no_build=True,no_retry=True,no_fsdb=True,stop_first_fail=True,
              numeric_before_postcheck=True,full_parent=True,linux=False,scope='Original contiguous6720;967680 bytes;6720flags/vstarts; no partition reset',
              detail_pattern=DETAIL_PATTERN,reference_raw_identity=read(REF/'reference01/COMPLETE.json')['raw'],
              service_terminal_contract=dict(RemainAfterExit=False,exit_hook_sha256=sha(HERE/'exit_hook.py'),collector_sha256=sha(HERE/'collect.py')))
    validate(plan);out.mkdir();durable(out/'plan.json',plan);digest=sha(out/'plan.json')
    command=[sys.executable,'-B',str(HERE/'replay.py'),'run','--out',str(out),'--plan-sha256',digest,
             '--entry-review',str(ENTRY),'--entry-sha256','__ACTUAL_ENTRY_SHA__','--parent-review','__ACTUAL_PARENT_JSON__','--parent-sha256','__ACTUAL_PARENT_SHA__']
    service=['systemd-run','--user','--unit='+UNIT,'--property=Type=exec','--property=RemainAfterExit=no','--property=RuntimeMaxSec='+str(OUTER),
             '--property=KillMode=control-group','--property=Restart=no','--property=WorkingDirectory='+str(HERE),
             '--property=StandardOutput=append:'+str(out/'service.log'),'--property=StandardError=append:'+str(out/'service.log'),
             '--property=ExecStopPost='+shlex.join([sys.executable,'-B',str(HERE/'exit_hook.py'),'--out',str(out)]),*command]
    durable(out/'ready.json',dict(status='PREPARED_NOT_LAUNCHED',plan_sha256=digest,service_argv=service,service_command=shlex.join(service),DUT_started=False))
    print('PREPARED_NOT_LAUNCHED',digest,flush=True)
def approval_gate(out,digest,entry,entrysha,parent,parentsha):
    require(entry==ENTRY and sha(entry)==entrysha,'Actual independent entry binding');v=read(entry)
    require(v['decision']=='NO_BLOCKER_FULL6720_M9_ENTRY' and v['plan_sha256']==digest and v['worker_sha256']==sha(HERE/'replay.py') and
            v['strict_sha256']==sha(HERE/'strict.py') and v['checker_sha256']==sha(HERE/'checker.py') and v['reference_review_sha256']==REVIEW_SHA,'Exact entry')
    require(parent and sha(parent)==parentsha,'Separate parent launch approval');v=read(parent)
    require(v['decision']=='AUTHORIZE_FULL6720_M9_ONCE' and v['plan_sha256']==digest and v['entry_sha256']==entrysha and v['unit']==UNIT and v['budget_s']==[10800,12000,13200] and v['jobs']==1,'Prepare is not launch permission')
    return {str(entry):entrysha,str(parent):parentsha}
base.cases=cases;base.reference_pins=reference_pins;base.validate=validate;base.approval_gate=approval_gate
base.worker.cases=cases
base.worker.engine_hooks=engine_hooks
disk_gate=base.disk_gate
def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','dryrun','run']);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--plan-sha256');p.add_argument('--entry-review',type=Path);p.add_argument('--entry-sha256');p.add_argument('--parent-review',type=Path);p.add_argument('--parent-sha256');a=p.parse_args()
    out=a.out.resolve();require(out.parent==HERE,'Owned output')
    if a.mode=='prepare':prepare(out);return 0
    if a.mode=='dryrun':base.dryrun(out,a.plan_sha256);return 0
    env=common.base.shared.environment();env.update(XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}',DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
    os.environ.clear();os.environ.update(env)
    return base.run(out,a.plan_sha256,a.entry_review,a.entry_sha256,a.parent_review,a.parent_sha256)
if __name__=='__main__':raise SystemExit(main())
