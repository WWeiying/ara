"""Exclusive direct-service launch for metadata collection, never a DUT runner."""
import os
import subprocess
import sys
import audit as a
import collect

if __name__=='__main__':
    hook=a.H.parent/'unit_fof_e64_suffix_two_vcs_m9_plan01/pinned_service_exit.py'
    a.need(a.sha(hook)=='05ed8d7d400d9940d30f77bdbd287f40d9a5623e43bdf8c05bf3b4ed0718a517',
           'Reviewed actual systemd exit hook')
    files=[a.H/n for n in ('audit.py','collect.py','events.py','test_events.py','launch.py','HOST_RECEIPT.md')]
    files += [hook,a.P/'plan.json',a.P/'service_launch.json',
              a.H.parent/'fof_two_singles_m9_entry_review01/result.json']
    a.need(a.sha(a.P/'plan.json')==a.PLAN and a.sha(a.P/'service_launch.json')==a.ENVELOPE,
           'Exact already launched producer')
    pins={str(p):a.sha(p) for p in files}
    a.save(a.H/'READY.json',dict(status='PREPARED_EVENT_TERMINAL_COLLECTOR_NOT_ACCEPTANCE',pins=pins,
        producer_plan_sha256=a.PLAN,wait_bound_s=4200,service_bound_s=4500,
        authorized='User authorized independent event terminal collection without another approval',
        CSV_semantic_reparse=False,DUT_or_reference_started=False))
    cmd=['systemd-run','--user','--collect','--unit='+collect.UNIT,
         '--property=RuntimeMaxSec=4500','--property=KillMode=control-group','--property=Restart=no',
         '--property=WorkingDirectory='+str(a.H),
         '--property=StandardOutput=append:'+str(a.H/'service.log'),
         '--property=StandardError=append:'+str(a.H/'service.log'),
         '--property=ExecStopPost=/usr/bin/python3 -B '+str(hook)+' '+str(a.H/'service_exit.json'),
         '/usr/bin/python3','-B',str(a.H/'collect.py')]
    a.save(a.H/'launch.json',dict(command=cmd,ready_sha256=a.sha(a.H/'READY.json'),pins=pins))
    env=dict(os.environ,XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}',
             DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
    r=subprocess.run(cmd,env=env,text=True,capture_output=True,timeout=30)
    a.save(a.H/'launch_receipt.json',dict(actual_systemd_run_returncode=r.returncode,
        stdout=r.stdout,stderr=r.stderr,collector_exit_not_yet_observed=True))
    print(r.stdout+r.stderr,flush=True)
    raise SystemExit(r.returncode)
