#!/usr/bin/env python3
"""Narrow private adapter to sealed numeric-first682 worker; M9 original700 only."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import checker
from checker import common, read, sha, require
from newscope import *

_spec = importlib.util.spec_from_file_location('sealed_fp682_worker_private700',PREVIOUS/'replay.py')
legacy = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = legacy
_spec.loader.exec_module(legacy)
worker = legacy.worker
durable, monitored = legacy.durable, legacy.monitored
HOST_REPORT = 'host_worker03.json'
ENTRY = HERE/'ENTRY.json'


def reference_inputs():
    require(sha(READY)==READY_SHA,'Frozen source700 READY')
    ready = read(READY)
    require(ready['status']=='SOURCE700_HOST_COMPILE_FULL_REFERENCE_READY_NOT_DUT'
            and sha(PREP/'pins.json')==ready['pins_sha256'],'Source actual schema/pins')
    ref = read(PREP/'reference01/result.json')
    require(ref['status']=='SOURCE700_FULL_DYNAMIC_REFERENCE_ACCEPTED_NOT_DUT'
            and [ref[k] for k in ('calls','predecessors','result_bits','guards','flags','vstarts','helper_instructions')]
            ==[700,699,358400,1400,700,700,12880] and ref['pins_pre_post_unchanged'] is True,
            'Full original source700 reference')
    for key in ('actual_reference','actual_audit'):
        require(type(ref[key]['returncode']) is int and ref[key]['returncode']==0
                and ref[key]['timed_out'] is False,'Actual reference/audit wait0')
    require(ref['margin20_projection_s']<TIMEOUT and ref['firmware']<3000000,'Fixed measured budget')
    proof = read(PREP/'source_delta.json')
    require(proof['status']=='EXACT_SOURCE_DELTA700_PASS_NOT_DUT' and
            all(proof[k] is True for k in ('first682_rows_a_b_mask_allowed_flags_identical',
                'first682_packed_records_identical','original_input_ROM_rows_identical',
                'source_only_name_and_single_stop_change')),'Narrow source preservation proof')
    pins = legacy.merge_pins(read(PREP/'pins.json'),proof['pins'])
    for p in (READY,PREP/'pins.json',PREP/'source_delta.json',PREP/'reference01/result.json',
              HERE/'USER_AUTHORIZATION.md'):
        pins = legacy.merge_pins(pins,{str(p):sha(p)})
    common.base.verify_pins(pins)
    return pins


def cases():
    elf = PREP/'prepared01/soc.elf'
    require(sha(elf)==read(READY)['soc_elf_sha256'],'Actual original700 SoC ELF')
    return [dict(id=NAME,original_name=NAME,source_label=HISTORICAL,elf=str(elf),sha256=sha(elf),
                 timeout_s=TIMEOUT,pass_markers=[MARKER,'BOARD_CASE_PASS '+NAME,'BOARD_REPLAY_PASS'])]


def validate(plan,image):
    require(image==IMAGE and plan['image_sha256']==sha(IMAGE/'image.json')==IMAGE_SHA,'Frozen M9')
    require(plan['status']=='PREPARED_NOT_RUN' and plan['cases']==cases() and plan['jobs']==1
            and plan['timeout_s']==TIMEOUT and plan['service_timeout_s']==OUTER and plan['unit']==UNIT
            and plan['reference_ready_sha256']==READY_SHA
            and plan['specs']=={NAME:checker.specification(Path(cases()[0]['elf']))}
            and all(plan[k] is True for k in ('no_build','no_retry','no_fsdb','no_code_coverage',
                       'no_ucli','stop_first_fail','numeric_monitor_before_postcheck')),'Exact700 fixed contract')
    expected = reference_inputs()
    host = read(HERE/HOST_REPORT)
    require(host['status']=='PASS_HOST_ONLY_NOT_DUT' and host['failures']==host['errors']==0,'Actual Host acceptance')
    expected = legacy.merge_pins(expected,host['pins'])
    require(all(plan['pins'].get(p)==h for p,h in expected.items()),'Complete required pin membership')
    require(plan['pins'][str(HERE/'replay.py')]==sha(HERE/'replay.py'),'Actual worker pin')
    common.base.verify_pins(plan['pins'])


def terminal_plan_gate(out,digest,image):
    require(sha(out/'plan.json')==digest,'Late disk plan drift')
    validate(read(out/'plan.json'),image)
    require(sha(out/'plan.json')==digest,'Late plan race')


def authorization_gate(digest,path,parent_sha):
    require(path==ENTRY and sha(path)==parent_sha,'Actual independent review path/hash')
    entry = read(path)
    require(entry['decision']=='NO_BLOCKER_ENTRY_ORIGINAL700_M9' and entry['no_blocker'] is True
            and entry['plan_sha256']==digest and entry['worker_sha256']==sha(HERE/'replay.py')
            and entry['checker_sha256']==sha(HERE/'checker.py') and entry['ready_sha256']==READY_SHA,
            'Actual independent Tesla exact entry')
    common.base.verify_pins(entry['pins'])
    return legacy.merge_pins(entry['pins'],{str(path):parent_sha,
                                         str(HERE/'USER_AUTHORIZATION.md'):sha(HERE/'USER_AUTHORIZATION.md')})


def service_identity():
    keys='Id,LoadState,ActiveState,SubState,MainPID,ControlGroup,RuntimeMaxUSec,KillMode,Restart'
    q=subprocess.run(['systemctl','--user','show',UNIT,'--property='+keys],text=True,capture_output=True,timeout=10)
    require(q.returncode==0 and not q.stderr.strip(),'Actual service query')
    p=dict(line.split('=',1) for line in q.stdout.splitlines())
    cg=Path('/proc/self/cgroup').read_text()
    require(p['Id']==UNIT and p['LoadState']=='loaded' and p['ActiveState']=='active'
            and p['SubState']=='running' and p['MainPID']==str(os.getpid())
            and p['ControlGroup'].endswith('/'+UNIT) and p['ControlGroup'] in
            [line.split(':',2)[-1] for line in cg.splitlines()] and p['RuntimeMaxUSec']=='2h 30min'
            and p['KillMode']=='control-group' and p['Restart']=='no','Direct single9000s worker owner')
    return dict(properties=p,cgroup=cg,pid=os.getpid())


def prepare(out):
    require(out.parent==HERE and not out.exists(),'Fresh owned plan')
    pins = reference_inputs()
    host=read(HERE/HOST_REPORT)
    require(host['status']=='PASS_HOST_ONLY_NOT_DUT' and host['failures']==host['errors']==0,'Actual focused Host')
    pins = legacy.merge_pins(pins,host['pins'])
    ledger,repo,_=common.image_context(IMAGE)
    require(Path(ledger['snapshot']).parent.name=='current_board_memory_candidate09','M9 snapshot')
    pins=legacy.merge_pins(pins,common.image_pins(IMAGE,ledger,repo))
    for mod in list(sys.modules.values()):
        p=getattr(mod,'__file__',None)
        if p and Path(p).is_file() and Path(p).resolve().is_relative_to(HERE.parents[4]):
            pins=legacy.merge_pins(pins,{str(Path(p).resolve()):sha(Path(p))})
    for path in [*HERE.glob('*.py'),HERE/HOST_REPORT,HERE/'USER_AUTHORIZATION.md']:
        pins=legacy.merge_pins(pins,{str(path):sha(path)})
    plan=dict(status='PREPARED_NOT_RUN',image=str(IMAGE),image_sha256=IMAGE_SHA,snapshot_sha256=ledger['snapshot_sha256'],
         cases=cases(),specs={NAME:checker.specification(Path(cases()[0]['elf']))},pins=pins,jobs=1,
         timeout_s=TIMEOUT,service_timeout_s=OUTER,unit=UNIT,reserved_slots=0,
         no_build=True,no_retry=True,no_fsdb=True,no_code_coverage=True,no_ucli=True,stop_first_fail=True,
         numeric_monitor_before_postcheck=True,reference_ready_sha256=READY_SHA,
         scope='Original first700/699predecessors; retained report union21; not17920/Linux',
         budget=dict(case_s=TIMEOUT,service_s=OUTER,no_autoextension=True))
    validate(plan,IMAGE)
    out.mkdir();durable(out/'plan.json',plan);digest=sha(out/'plan.json')
    argv=[sys.executable,'-B',str(HERE/'replay.py'),'run','--out',str(out),'--plan-sha256',digest,
          '--authorize-run','--parent-review',str(ENTRY),
          '--parent-review-sha256','__ACTUAL_ENTRY_SHA256__']
    service=['systemd-run','--user','--unit='+UNIT,'--property=Type=exec',
             '--property=RemainAfterExit=yes','--property=RuntimeMaxSec='+str(OUTER),
             '--property=KillMode=control-group','--property=Restart=no',
             '--property=WorkingDirectory='+str(HERE),'--property=StandardOutput=append:'+str(out/'service.log'),
             '--property=StandardError=append:'+str(out/'service.log'),*argv]
    durable(out/'ready.json',dict(status='PREPARED_NOT_LAUNCHED',plan_sha256=digest,
             service_argv=service,service_command=shlex.join(service),DUT_started=False))
    print('PREPARED700_M9',digest,flush=True)


legacy.cases=cases
legacy.validate=validate
legacy.terminal_plan_gate=terminal_plan_gate
legacy.authorization_gate=authorization_gate
legacy.service_identity=service_identity
worker.cases=cases


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','dryrun','run'])
    p.add_argument('--out',type=Path,required=True);p.add_argument('--plan-sha256')
    p.add_argument('--authorize-run',action='store_true');p.add_argument('--parent-review',type=Path)
    p.add_argument('--parent-review-sha256');a=p.parse_args();out=a.out.resolve()
    require(out.parent==HERE,'Owned direct output')
    env=common.base.shared.environment();env.update(XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}',
        DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
    os.environ.clear();os.environ.update(env)
    if a.mode=='prepare':prepare(out)
    elif a.mode=='dryrun':legacy.dryrun(IMAGE,out,a.plan_sha256)
    else:raise SystemExit(legacy.run(IMAGE,out,a.plan_sha256,a.authorize_run,a.parent_review,a.parent_review_sha256))
