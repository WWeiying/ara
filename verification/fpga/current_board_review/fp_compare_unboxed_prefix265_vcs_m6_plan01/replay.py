#!/usr/bin/env python3
"""Thin scope adapter over frozen worker; preparation is not launch permission."""
import argparse
import importlib.util
import os
from pathlib import Path
import shlex
import subprocess
import sys
sys.dont_write_bytecode=True
import checker
from checker import HERE,REF,NAME,READY_SHA,require,common,read,sha
LEGACY=HERE.parent/'merge_original_prefix98_vcs_m6_plan01/replay.py'
spec=importlib.util.spec_from_file_location('frozen_merge_execution',LEGACY)
worker=importlib.util.module_from_spec(spec);sys.modules[spec.name]=worker;spec.loader.exec_module(worker)
TIMEOUT,OUTER=5400,6600
UNIT='ara-fp-unboxed-original265-m6-01.service'
IMAGE_SHA='a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0'
PASS='PASS_M6_ORIGINAL_UNBOXED265_NOT_FULL_PARENT'
def reference_inputs():
    require(sha(REF/'READY.json')==READY_SHA,'Reference READY drift')
    r=read(REF/'READY.json');require(r['scope']==dict(calls=265,predecessors=264,capacity=16,result_bits=4240,guards=530,vstart=265,flags=265),'Exact original scope')
    pins={**r['baseline_pins'],**r['owned_pins'],str(REF/'READY.json'):READY_SHA}
    common.base.verify_pins(pins);return pins
def scope():
    e=read(REF/'READY.json')['soc_elf']
    return dict(id=NAME,original_name='rvv_fp_compare_unboxed_unmasked_e16_mf4',elf=e['path'],sha256=e['sha256'],timeout_s=TIMEOUT,pass_markers=e['pass_markers']),checker.specification(Path(e['path']))
def validate(data,image):
    require(data['status']=='PREPARED_NOT_RUN' and data['image']==str(image) and sha(image/'image.json')==data['image_sha256']==IMAGE_SHA,'Image/plan drift')
    case,s=scope()
    require(data['case']==case and data['spec']==s and data['jobs']==1 and data['timeout_s']==TIMEOUT and data['service_timeout_s']==OUTER and data['unit']==UNIT,'Case/budget/service drift')
    require(data['reference_ready_sha256']==READY_SHA and all(data[k] for k in ('no_build','no_retry','no_fsdb')),'Scope/retry drift')
    require(data['pins'].get(str(Path(__file__).resolve()))==sha(Path(__file__)),'Worker drift')
    common.base.verify_pins(data['pins'])
def authorization_gate(plan,digest,path,hashvalue):
    require(path is not None and hashvalue and sha(path)==hashvalue,'New explicit parent review required')
    review=read(path)
    require(review['decision']=='AUTHORIZE_UNBOXED_ORIGINAL265_ONCE' and review['plan_sha256']==digest and review['unit']==UNIT and review['reference_ready_sha256']==READY_SHA and review['budget_risk_accepted'] is True,'Parent authorization scope')
    # Actual independently written schema is validated here, never fabricated in prepare.
    ap=Path(review['reference_audit']['path']);rp=Path(review['reference_review']['path'])
    pins={str(path):hashvalue,str(ap):review['reference_audit']['sha256'],str(rp):review['reference_review']['sha256']}
    common.base.verify_pins(pins)
    audit=read(ap)
    require(audit.get('status')=='ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT' and audit.get('ready_sha256')==READY_SHA,
            'Independent audit not accepted/bound; actual schema must be reviewed before launch')
    pins.update(reference_inputs());return pins
def service_identity(unit):
    runtime=Path('/run/user')/str(os.getuid())
    require(runtime.is_dir() and runtime.stat().st_uid==os.getuid() and (runtime/'bus').is_socket(),'Trusted user bus unavailable')
    env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(runtime/'bus'))
    names=('Id','LoadState','ActiveState','SubState','MainPID','ControlGroup','RuntimeMaxUSec','KillMode','Restart')
    r=subprocess.run(['systemctl','--user','show',unit,'--property='+','.join(names)],env=env,capture_output=True,text=True,timeout=10)
    require(r.returncode==0 and not r.stderr.strip(),'User-manager query failed')
    p=dict(l.split('=',1) for l in r.stdout.splitlines());cg=Path('/proc/self/cgroup').read_text()
    require(set(p)==set(names) and p['Id']==unit and p['LoadState']=='loaded' and p['ActiveState']=='active' and p['SubState']=='running' and p['MainPID']==str(os.getpid()) and p['ControlGroup'].endswith('/'+unit) and
            any(l.split(':',2)[-1]==p['ControlGroup'] for l in cg.splitlines()) and p['RuntimeMaxUSec']=='1h 50min' and p['KillMode']=='control-group' and p['Restart']=='no','Direct service ownership/deadline')
    return dict(properties=p,cgroup=cg,pid=os.getpid(),query_stdout=r.stdout)
def prepare(image,out,reserved):
    require(not out.exists(),'Fresh output only')
    pins=reference_inputs();ledger,repo,_=common.image_context(image)
    require(sha(image/'image.json')==IMAGE_SHA,'Exact M6 required')
    pins.update(common.image_pins(image,ledger,repo));case,s=scope()
    for module in list(sys.modules.values()):
        p=getattr(module,'__file__',None)
        if p and Path(p).is_file() and Path(p).resolve().is_relative_to(HERE.parents[3]):pins[str(Path(p).resolve())]=sha(Path(p))
    for p in HERE.glob('*'):
        if p.is_file():pins[str(p)]=sha(p)
    host=read(HERE/'host02.json');require(host['status']=='PASS_HOST_ONLY' and host['failures']==host['errors']==0 and host['script_sha256']==sha(HERE/'test_host.py'),'Host gates')
    require(type(reserved) is int and 0<=reserved<=24,'Unused reservations only')
    common.base.verify_pins(pins);out.mkdir()
    common.save(out/'plan.json',dict(status='PREPARED_NOT_RUN',image=str(image),image_sha256=IMAGE_SHA,snapshot_sha256=ledger['snapshot_sha256'],
        case=case,spec=s,pins=pins,jobs=1,timeout_s=TIMEOUT,service_timeout_s=OUTER,unit=UNIT,reserved_slots=reserved,
        no_build=True,no_retry=True,no_fsdb=True,reference_ready_sha256=READY_SHA,
        independent_reference_acceptance='PENDING_SEPARATE_AUDIT_NOT_LAUNCHABLE_WITHOUT_REVIEW',
        launch_requirements=['independent_audit_and_review_pins','new_parent_planSHA_authorization','direct_service_owner','runtime_resources'],
        budget=dict(reference_retired=701895,slow_proxy_retired_per_s=273,with20percent_s=701895/273*1.2,guaranteed=False),
        resource_snapshot=None,resource_check_deferred_to_authorized_run=True,
        original_failure=dict(op=4,seed=0,vl=15,mask=0,sticky=0,expected_flags=0,actual_flags=16,ordinal=265),full_parent_acceptance=False))
    digest=sha(out/'plan.json')
    command=[sys.executable,str(Path(__file__).resolve()),'run','--image',str(image),'--out',str(out),'--plan-sha256',digest,'--authorize-run','--parent-review','PARENT_REVIEW_JSON','--parent-review-sha256','PARENT_REVIEW_SHA256']
    service=['systemd-run','--user','--unit='+UNIT,'--property=RuntimeMaxSec='+str(OUTER),'--property=KillMode=control-group','--property=Restart=no','--property=WorkingDirectory='+str(HERE),'--property=StandardOutput=append:'+str(out/'service.log'),'--property=StandardError=append:'+str(out/'service.log'),*command]
    common.save(out/'ready.json',dict(status='PREPARED_NOT_ADMITTED_NO_DUT',plan_sha256=digest,command=command,service_command=shlex.join(service),pins=len(pins),vcs_started=False))
    print('PREPARED_NOT_ADMITTED_NO_DUT',digest)

# Scope parameters only change this imported module instance, never its frozen file.
for k,v in dict(NAME=NAME,HERE=HERE,REF=REF,TIMEOUT=TIMEOUT,OUTER=OUTER,UNIT=UNIT,PASS=PASS,
                scope=scope,validate=validate,authorization_gate=authorization_gate,service_identity=service_identity).items():setattr(worker,k,v)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','dryrun','run'))
    p.add_argument('--image',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--authorize-prepare',action='store_true');p.add_argument('--authorize-run',action='store_true')
    p.add_argument('--reserved-slots',type=int,default=0);p.add_argument('--plan-sha256');p.add_argument('--parent-review',type=Path);p.add_argument('--parent-review-sha256')
    a=p.parse_args();image,out=a.image.resolve(),a.out.resolve();require(out.parent==HERE,'Owned direct child')
    env=common.base.shared.environment();os.environ.clear();os.environ.update(env)
    if a.mode=='prepare':require(a.authorize_prepare,'Explicit prepare required');prepare(image,out,a.reserved_slots);return 0
    if a.mode=='dryrun':return worker.dryrun(image,out,a.plan_sha256)
    return worker.run(image,out,a.plan_sha256,a.authorize_run,a.parent_review,a.parent_review_sha256)
if __name__=='__main__':raise SystemExit(main())
