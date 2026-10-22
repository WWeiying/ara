#!/usr/bin/env python3
"""Prepare one no-build M6 job; run requires a new pinned parent authorization."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
sys.dont_write_bytecode=True
import checker
from checker import HERE,NAME,READY_SHA,require,read,sha,common

ROOT=HERE.parents[2]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module

worker=load('nf2_frozen_worker',ROOT/'merge_original_prefix98_vcs_m6_plan01/replay.py')
outcome=load('nf2_outcome_adapter',ROOT/'fp_compare_unboxed_prefix265_vcs_m6_plan01/provenance_recovery01/adapter.py')
TIMEOUT,OUTER=6300,6900
UNIT='ara-nf2-remaining4-m6-01.service'
IMAGE_SHA='a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0'
AUDIT=HERE.parent/'nf2_remaining4_reference_audit01'
AUDIT_PINS={str(AUDIT/'REVIEW.md'):'47fc85fe429f9be67ae48b5c0bc73b979a808ed60e6750e5bdf21b954abab582',
            str(AUDIT/'result.json'):'f7c60873358baeeea6d8a0798a6ec8e0bdf5ad0f9daeb2750784ec0f23c918e6'}

def accepted_reference():
    common.base.verify_pins(AUDIT_PINS)
    result=read(AUDIT/'result.json')
    require(result['status']=='ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT' and
            result['ready_sha256']==READY_SHA and result['cases']==[c['id'] for c in checker.CASES] and
            result['pins_pre_post_unchanged'] is True and result['rebuilt']['checks']==3567 and
            result['DUT_executed'] is False,'Independent source/reference acceptance differs')
    return dict(AUDIT_PINS)

def scope():
    ready=read(HERE/'READY.json');elf=ready['soc_elf']
    return dict(id=NAME,original_name='rvv_fault_replay_segment_nf2_e16_m1',
                historical_names=[c['historical_name'] for c in checker.CASES],
                elf=elf['path'],sha256=elf['sha256'],timeout_s=TIMEOUT,
                pass_markers=['NF2_REMAINING4_SV39_PASS']),checker.specification()

def validate(data,image):
    case,spec=scope()
    require(data['status']=='PREPARED_NOT_RUN' and data['image']==str(image) and
            data['image_sha256']==sha(image/'image.json')==IMAGE_SHA,'Image/plan drift')
    require(data['case']==case and data['spec']==spec and data['timeout_s']==TIMEOUT and
            data['service_timeout_s']==OUTER and data['jobs']==1 and data['unit']==UNIT and
            data['no_build'] and data['no_retry'] and data['no_fsdb'] and
            data['reference_ready_sha256']==READY_SHA,'Scope/budget/identity drift')
    require(sha(HERE/'READY.json')==READY_SHA,'Reference READY drift')
    require(data['independent_reference_pins']==accepted_reference(),'Independent reference binding drift')
    require(data['pins'].get(str(Path(__file__).resolve()))==sha(Path(__file__)),'Worker drift')
    common.base.verify_pins(data['pins'])

def prepare(image,out,reserved):
    require(not out.exists(),'Fresh plan only')
    require(sha(HERE/'READY.json')==READY_SHA,'Reference READY drift')
    ready=read(HERE/'READY.json');require(ready['status']=='SOURCE_REFERENCE_PASS_PENDING_INDEPENDENT_REVIEW_NOT_DUT',
                                     'Source/reference scope')
    pins={**ready['pins'],str(HERE/'READY.json'):READY_SHA}
    pins.update(accepted_reference())
    ledger,repo,_=common.image_context(image)
    require(sha(image/'image.json')==IMAGE_SHA,'Exact M6 only')
    pins.update(common.image_pins(image,ledger,repo))
    case,spec=scope()
    require(checker.ref.symbols(Path(case['elf']))==spec['symbols'],'Actual ELF symbols differ')
    for p in (HERE/'observer_host02/status.json',HERE/'worker_host04.json'):
        host=read(p);require(host['status']=='PASS_HOST_ONLY_NOT_DUT','Host gates incomplete')
        common.base.verify_pins(host['pins']);pins.update(host['pins']);pins[str(p)]=sha(p)
    for module in list(sys.modules.values()):
        p=getattr(module,'__file__',None)
        if p and Path(p).is_file() and Path(p).resolve().is_relative_to(ROOT.parents[2]):
            pins[str(Path(p).resolve())]=sha(Path(p))
    for name in ('replay.py','checker.py','csv_check.py','test_csv.py','test_worker.py','VCS_PLAN.md'):
        pins[str(HERE/name)]=sha(HERE/name)
    require(type(reserved) is int and 0<=reserved<=24,'Unused reservations only')
    common.base.verify_pins(pins)
    out.mkdir()
    common.save(out/'plan.json',dict(status='PREPARED_NOT_RUN',image=str(image),image_sha256=IMAGE_SHA,
        snapshot_sha256=ledger['snapshot_sha256'],case=case,spec=spec,pins=pins,jobs=1,
        timeout_s=TIMEOUT,service_timeout_s=OUTER,unit=UNIT,reserved_slots=reserved,
        no_build=True,no_retry=True,no_fsdb=True,reference_ready_sha256=READY_SHA,
        independent_reference_acceptance='ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT',
        independent_reference_pins=AUDIT_PINS,
        runtime_testcase=NAME,unvalidated_child_outcome_before_postcheck=True,
        budget=dict(parsed_spike_records=1315037,conservative_records_per_second=273,
                    proxy_plus20percent_s=1315037/273*1.2,guaranteed=False),
        resource_snapshot=None,resource_check_deferred_to_authorized_run=True))
    digest=sha(out/'plan.json')
    cmd=[sys.executable,'-B',str(Path(__file__).resolve()),'run','--image',str(image),'--out',str(out),
         '--plan-sha256',digest,'--authorize-run','--parent-review','PARENT_REVIEW_JSON',
         '--parent-review-sha256','PARENT_REVIEW_SHA256']
    service=['systemd-run','--user','--unit='+UNIT,'--property=RuntimeMaxSec='+str(OUTER),
             '--property=KillMode=control-group','--property=Restart=no','--property=WorkingDirectory='+str(HERE),
             '--property=StandardOutput=append:'+str(out/'service.log'),
             '--property=StandardError=append:'+str(out/'service.log'),*cmd]
    common.save(out/'ready.json',dict(status='PREPARED_NOT_ADMITTED_NO_DUT',plan_sha256=digest,pins=len(pins),
        command=cmd,service_command=shlex.join(service),VCS_started=False))
    print('PREPARED_NOT_ADMITTED_NO_DUT',digest)

def authorization_gate(plan,digest,path,path_sha):
    require(path is not None and path_sha and sha(path)==path_sha,'Pinned new parent authorization required')
    review=read(path)
    require(review['decision']=='AUTHORIZE_NF2_REMAINING4_ONCE' and review['plan_sha256']==digest and
            review['unit']==UNIT and review['reference_ready_sha256']==READY_SHA and
            review['budget_risk_accepted'] is True and review['independent_reference_accepted'] is True,
            'Parent scope/reference/budget authorization')
    evidence=review['independent_reference_evidence']
    require(evidence==accepted_reference(),'Actual pinned independent review/result required')
    common.base.verify_pins(evidence)
    return {**evidence,str(path):path_sha,str(HERE/'READY.json'):READY_SHA}

def service_identity(unit):
    runtime=Path('/run/user')/str(os.getuid())
    require(runtime.is_dir() and runtime.stat().st_uid==os.getuid() and (runtime/'bus').is_socket(),
            'Trusted user bus unavailable')
    env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(runtime/'bus'))
    names=('Id','LoadState','ActiveState','SubState','MainPID','ControlGroup','RuntimeMaxUSec','KillMode','Restart')
    query=subprocess.run(['systemctl','--user','show',unit,'--property='+','.join(names)],
                         env=env,text=True,capture_output=True,timeout=10)
    require(query.returncode==0 and not query.stderr.strip(),'Service query failed')
    props=dict(line.split('=',1) for line in query.stdout.splitlines())
    cgroup=Path('/proc/self/cgroup').read_text()
    require(set(props)==set(names) and props['Id']==unit and props['LoadState']=='loaded' and
            props['ActiveState']=='active' and props['SubState']=='running' and props['MainPID']==str(os.getpid()) and
            props['ControlGroup'].endswith('/'+unit) and
            any(line.split(':',2)[-1]==props['ControlGroup'] for line in cgroup.splitlines()) and
            props['RuntimeMaxUSec']=='1h 55min' and props['KillMode']=='control-group' and props['Restart']=='no',
            'Wrong direct service owner/bound')
    return dict(properties=props,cgroup=cgroup,pid=os.getpid(),query_stdout=query.stdout)

# Bind the new case-specific checks and durable outcome to the mature worker;
# its pinned files remain unmodified. No import or prepare starts a simulator.
worker.HERE=HERE;worker.NAME=NAME;worker.TIMEOUT=TIMEOUT;worker.OUTER=OUTER;worker.UNIT=UNIT
worker.PASS='PASS_M6_NF2_REMAINING4_SV39_NOT_LINUX'
worker.prepare=prepare;worker.scope=scope;worker.validate=validate
worker.authorization_gate=authorization_gate;worker.service_identity=service_identity
worker.checked_runner=outcome.successor_checked_runner
if __name__=='__main__':raise SystemExit(worker.main())
