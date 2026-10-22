#!/usr/bin/env python3
"""Prepare/dryrun one existing M6 ELF; run needs pinned parent authorization."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
sys.dont_write_bytecode=True
import checker
from checker import HERE,REF,G,NAME,HISTORICAL,READY_SHA,require,read,sha,common,load

worker=load('negative_stride_frozen_worker',G/'merge_original_prefix98_vcs_m6_plan01/replay.py')
outcome=load('negative_stride_durable_outcome',G/'fp_compare_unboxed_prefix265_vcs_m6_plan01/provenance_recovery01/adapter.py')
TIMEOUT,OUTER=3600,4800
UNIT='ara-negative-stride-load-m6-01.service'
IMAGE_SHA='a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0'
AUDIT=HERE.parent/'negative_stride_load_adapter_review01'
AUDIT_PINS={str(AUDIT/'REVIEW_FINAL01.md'):'99fabe9cf0ee0dd3dad424ee8eedc93b0646d4fcc2f3c1fb11ac6514842e71f7',
            str(AUDIT/'decision01.json'):'3346d98ac482324d1edb01fd5c3b67a8d1b87a7e2cdc7e0987dd32e32b32deb0'}

def accepted_adapter():
    common.base.verify_pins(AUDIT_PINS);a=read(AUDIT/'decision01.json')
    require(a['status']=='APPROVED_SEALED_ADAPTER_STATIC_REVIEW_ONLY' and a['blocking_findings']==[] and
            a['ready_sha256']==READY_SHA and a['ready_pin_count']==64 and
            a['DUT_launch_authorized_by_this_review'] is False and
            a['independent_raw_reference_recomputation'] is False,'Actual static review schema/scope')
    return dict(AUDIT_PINS)

def scope():
    spec=checker.specification()
    return dict(id=NAME,original_name=HISTORICAL,elf=spec['elf'],sha256=spec['elf_sha256'],
                timeout_s=TIMEOUT,pass_markers=['NEGATIVE_STRIDE_SINGLE_PASS']),spec

def validate(data,image):
    case,spec=scope()
    require(data['status']=='PREPARED_NOT_RUN' and data['image']==str(image) and
            data['image_sha256']==sha(image/'image.json')==IMAGE_SHA,'Image/plan drift')
    require(data['case']==case and data['spec']==spec and data['jobs']==1 and data['timeout_s']==TIMEOUT and
            data['service_timeout_s']==OUTER and data['unit']==UNIT and data['no_retry'] and data['no_build'] and
            data['no_fsdb'] and data['reference_ready_sha256']==READY_SHA,'Scope/budget drift')
    require(data['adapter_review_pins']==accepted_adapter(),'Static review pins differ')
    require(data['pins'].get(str(Path(__file__).resolve()))==sha(Path(__file__)),'Worker drift')
    original=read(REF/'READY.json')['pins']
    require(len(original)==64 and all(data['pins'].get(p)==h for p,h in original.items()),'All original64 pins must survive')
    common.base.verify_pins(data['pins'])

def prepare(image,out,reserved):
    require(not out.exists(),'Fresh prepared directory only')
    require(sha(REF/'READY.json')==READY_SHA,'Reference READY drift')
    r=read(REF/'READY.json');pins=dict(r['pins'])
    require(len(pins)==64 and r['no_DUT_launch'] and r['source_cases']==1,'Exact reference scope')
    pins[str(REF/'READY.json')]=READY_SHA;pins.update(accepted_adapter())
    ledger,repo,_=common.image_context(image)
    require(sha(image/'image.json')==IMAGE_SHA and Path(ledger['snapshot']).parent.name=='current_board_memory_candidate06','Frozen M6 only')
    pins.update(common.image_pins(image,ledger,repo));case,spec=scope()
    for path in (HERE/'host02.json',HERE/'csv_host03/status.json'):
        host=read(path);require(host['status']=='PASS_HOST_ONLY_NOT_DUT','Host gate missing/failing')
        common.base.verify_pins(host['pins']);pins.update(host['pins']);pins[str(path)]=sha(path)
    for module in list(sys.modules.values()):
        f=getattr(module,'__file__',None)
        if f and Path(f).is_file() and Path(f).resolve().is_relative_to(G.parents[2]):
            pins[str(Path(f).resolve())]=sha(Path(f))
    for name in ('replay.py','checker.py','csv_check.py','test_host.py','test_csv.py','README.md'):
        pins[str(HERE/name)]=sha(HERE/name)
    require(type(reserved) is int and 0<=reserved<=24,'Unused reservation only, live counted once')
    common.base.verify_pins(pins);out.mkdir()
    common.save(out/'plan.json',dict(status='PREPARED_NOT_RUN',image=str(image),image_sha256=IMAGE_SHA,
        snapshot_sha256=ledger['snapshot_sha256'],case=case,spec=spec,pins=pins,jobs=1,timeout_s=TIMEOUT,
        service_timeout_s=OUTER,unit=UNIT,reserved_slots=reserved,no_build=True,no_retry=True,no_fsdb=True,
        reference_ready_sha256=READY_SHA,reference_original_pin_count=64,adapter_review_pins=AUDIT_PINS,
        adapter_review_scope='Static adapter only, not independent raw-reference acceptance or DUT launch',
        runtime_testcase=NAME,monitor_numeric_outcome_before_validation=True,
        budget=dict(reference_firmware_records=836971,proxy743_plus20_s=836971/743*1.2,
                    slow273_plus20_s=836971/273*1.2,slow_proxy_exceeds_3600=True,
                    guarantee=False,automatic_extension=False),
        source_single=True,linux_or_parent96_acceptance=False,resource_snapshot=None,
        resource_check_deferred_to_authorized_run=True))
    digest=sha(out/'plan.json')
    cmd=[sys.executable,'-B',str(Path(__file__).resolve()),'run','--image',str(image),'--out',str(out),
         '--plan-sha256',digest,'--authorize-run','--parent-review','PARENT_REVIEW_JSON',
         '--parent-review-sha256','PARENT_REVIEW_SHA256']
    service=['systemd-run','--user','--unit='+UNIT,'--property=RuntimeMaxSec='+str(OUTER),
             '--property=KillMode=control-group','--property=Restart=no','--property=WorkingDirectory='+str(HERE),
             '--property=StandardOutput=append:'+str(out/'service.log'),'--property=StandardError=append:'+str(out/'service.log'),*cmd]
    common.save(out/'ready.json',dict(status='PREPARED_NOT_ADMITTED_NO_DUT',plan_sha256=digest,
        command=cmd,service_command=shlex.join(service),pins=len(pins),DUT_started=False))
    print('PREPARED_NOT_ADMITTED_NO_DUT',digest,flush=True)

def authorization_gate(plan,digest,path,digest_review):
    require(path is not None and digest_review and sha(path)==digest_review,'Pinned new parent authorization required')
    review=read(path)
    require(review['decision']=='AUTHORIZE_NEGATIVE_STRIDE_SINGLE_M6_ONCE' and review['plan_sha256']==digest and
            review['unit']==UNIT and review['reference_ready_sha256']==READY_SHA and
            review['adapter_review_pins']==accepted_adapter() and review['budget_risk_accepted'] is True,
            'Parent scope/review/budget authorization')
    return {str(path):digest_review,**accepted_adapter(),str(REF/'READY.json'):READY_SHA}

def service_identity(unit):
    runtime=Path('/run/user')/str(os.getuid())
    require(runtime.is_dir() and runtime.stat().st_uid==os.getuid() and (runtime/'bus').is_socket(),'Trusted user bus unavailable')
    env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(runtime/'bus'))
    names=('Id','LoadState','ActiveState','SubState','MainPID','ControlGroup','RuntimeMaxUSec','KillMode','Restart')
    q=subprocess.run(['systemctl','--user','show',unit,'--property='+','.join(names)],env=env,text=True,capture_output=True,timeout=10)
    require(q.returncode==0 and not q.stderr.strip(),'Service query error')
    props=dict(line.split('=',1) for line in q.stdout.splitlines());cgroup=Path('/proc/self/cgroup').read_text()
    require(set(props)==set(names) and props['Id']==unit and props['LoadState']=='loaded' and
            props['ActiveState']=='active' and props['SubState']=='running' and props['MainPID']==str(os.getpid()) and
            props['ControlGroup'].endswith('/'+unit) and any(x.split(':',2)[-1]==props['ControlGroup'] for x in cgroup.splitlines()) and
            props['RuntimeMaxUSec']=='1h 20min' and props['KillMode']=='control-group' and props['Restart']=='no','Wrong direct service owner/budget')
    return dict(pid=os.getpid(),properties=props,cgroup=cgroup,query_stdout=q.stdout)

def durable_monitor(original):
    def monitored(command,cwd,console_path,timeout_s,cancel_event=None):
        rc,elapsed,timed_out,failure_seen=original(command,cwd,console_path,timeout_s,cancel_event)
        require(type(rc) is int,'Actual monitored wait code missing')
        record=dict(schema='UNVALIDATED_MONITOR_OUTCOME_V1',architectural_acceptance=False,
            returncode=rc,elapsed_s=elapsed,timed_out=timed_out,failure_seen=failure_seen,
            abort_set=bool(cancel_event and cancel_event.is_set()),command=list(map(str,command)),cwd=str(cwd),
            command_sha256=sha(Path(console_path).parent/'command.json'))
        with (Path(console_path).parent/'monitor_outcome.unvalidated.json').open('x') as f:
            json.dump(record,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        return rc,elapsed,timed_out,failure_seen
    return monitored

def checked_runner(parent,abort,check):
    inherited=outcome.successor_checked_runner(parent,abort,check)
    class Runner(inherited):
        def _run_test(self,*args):
            import ara_verify.runner as engine
            saved=engine._run_monitored;engine._run_monitored=durable_monitor(saved)
            try:return super()._run_test(*args)
            finally:engine._run_monitored=saved
    return Runner

worker.HERE=HERE;worker.REF=REF;worker.NAME=NAME;worker.TIMEOUT=TIMEOUT;worker.OUTER=OUTER;worker.UNIT=UNIT
worker.PASS='PASS_M6_NEGATIVE_STRIDE_SOURCE_SINGLE_NOT_LINUX'
worker.prepare=prepare;worker.scope=scope;worker.validate=validate
worker.authorization_gate=authorization_gate;worker.service_identity=service_identity;worker.checked_runner=checked_runner
if __name__=='__main__':raise SystemExit(worker.main())
