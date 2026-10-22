"""Small pinned launch envelope; direct worker MainPID, no scheduler or retry."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode=True
import checker as c
import replay as w
H=c.HERE
OUT=H/'prepared01'
PLAN_SHA='3bc80c42d8e6bf7f722d81184ef8fc4bcac099e2518547292f5172665324e949'

def prepare():
    c.require(not (OUT/'service_launch.json').exists(),'Fresh launch envelope')
    w.terminal_plan_gate(OUT,PLAN_SHA,w.IMAGE)
    host=c.read(H/'service_exit_host.json')
    c.require(host['status']=='HOST_SERVICE_EXIT_PASS_NOT_SYSTEMD_EVIDENCE'
              and host['actual_service_exit_written'] is False
              and host['helper_sha256']==c.sha(H/'pinned_service_exit.py'),'Actual standalone Host binding')
    hook=f"/usr/bin/python3 -B {H/'pinned_service_exit.py'} {OUT/'service_exit.json'}"
    command=['systemd-run','--user','--collect','--unit='+w.UNIT,
        '--property=RuntimeMaxSec=4200','--property=KillMode=control-group','--property=Restart=no',
        '--property=WorkingDirectory='+str(H),'--property=StandardOutput=append:'+str(OUT/'service.log'),
        '--property=StandardError=append:'+str(OUT/'service.log'),'--property=ExecStopPost='+hook,
        '/usr/bin/python3','-B',str(H/'replay.py'),'run','--image',str(w.IMAGE),'--out',str(OUT),
        '--authorize-run','--plan-sha256',PLAN_SHA,'--parent-review','TESLA_REVIEW',
        '--parent-review-sha256','TESLA_REVIEW_SHA']
    files=[H/n for n in ('service_launch.py','pinned_service_exit.py','test_service_exit.py',
                         'service_exit_host.json','OWNER_DELTA.md','replay.py','checker.py','source_owners.py')]
    files += [OUT/'plan.json',OUT/'dryrun_gate.json']
    pins={str(p):c.sha(p) for p in files}
    c.common.save(OUT/'service_launch.json',dict(status='PREPARED_NOT_LAUNCHED',plan_sha256=PLAN_SHA,
        command_template=command,ExecStopPost=hook,pins=pins,
        service_exit_source='systemd-injected EXIT_CODE/EXIT_STATUS/SERVICE_RESULT only',
        direct_worker_MainPID=True,no_retry=True,resources='worker single live admission only'))
    print('LAUNCH_ENVELOPE',c.sha(OUT/'service_launch.json'),flush=True)

def launch(digest,review,review_sha):
    c.require(c.sha(OUT/'service_launch.json')==digest,'Pinned launch envelope')
    envelope=c.read(OUT/'service_launch.json')
    c.common.base.verify_pins(envelope['pins'])
    c.require(envelope['plan_sha256']==PLAN_SHA,'Exact worker plan')
    w.authorization_gate(c.read(OUT/'plan.json'),PLAN_SHA,review,review_sha)
    for name in ('launch_command.json','launch.json','complete.json','service_exit.json','replay'):
        c.require(not (OUT/name).exists(),'No existing launch/output: '+name)
    env=dict(os.environ,XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}',
             DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
    q=subprocess.run(['systemctl','--user','show',w.UNIT,'-p','LoadState'],env=env,
                     text=True,capture_output=True,timeout=10)
    c.require(q.returncode==0 and q.stdout.strip()=='LoadState=not-found' and not q.stderr.strip(),
              'Existing or unqueryable service; no collision/retry')
    command=[str(review) if v=='TESLA_REVIEW' else review_sha if v=='TESLA_REVIEW_SHA' else v
             for v in envelope['command_template']]
    c.common.save(OUT/'launch_command.json',dict(command=command,service_launch_sha256=digest,
        review=str(review),review_sha256=review_sha,helper_pins=envelope['pins']))
    result=subprocess.run(command,env=env,text=True,capture_output=True,timeout=30)
    c.common.save(OUT/'systemd_run_receipt.json',dict(actual_systemd_run_returncode=result.returncode,
        stdout=result.stdout,stderr=result.stderr,worker_exit_not_yet_observed=True))
    print(result.stdout+result.stderr,flush=True)
    c.require(result.returncode==0,'systemd-run failed; no retry')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','launch'])
    p.add_argument('--launch-sha256');p.add_argument('--review',type=Path);p.add_argument('--review-sha256')
    a=p.parse_args()
    if a.mode=='prepare':prepare()
    else:launch(a.launch_sha256,a.review.resolve(),a.review_sha256)
