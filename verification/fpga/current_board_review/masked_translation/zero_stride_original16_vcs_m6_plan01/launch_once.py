#!/usr/bin/env python3
"""Authorized one-shot startup receipt; bounded discovery, never long-run polling."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
sys.dont_write_bytecode=True
import replay as app
c=app.checker

def busenv():
    root=Path('/run/user')/str(os.getuid())
    c.require(root.is_dir() and root.stat().st_uid==os.getuid() and (root/'bus').is_socket(),'Trusted user bus')
    return dict(os.environ,XDG_RUNTIME_DIR=str(root),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(root/'bus'))

def props():
    q=subprocess.run(['systemctl','--user','show',app.UNIT,'--property=Id,LoadState,ActiveState,SubState,MainPID,ControlGroup,Result,ExecMainStatus'],
                     env=busenv(),capture_output=True,text=True,timeout=10)
    c.require(q.returncode==0 and not q.stderr.strip() and q.stdout.strip(),'Service query must succeed')
    return dict(s.split('=',1) for s in q.stdout.splitlines())

def sample(pid,trace):
    p=Path('/proc')/str(pid);v=(p/'stat').read_text().rsplit(')',1)[1].split()
    data=b''
    if trace.exists():
        with trace.open('rb') as f:f.seek(max(0,trace.stat().st_size-65536));data=f.read()
    lines=data.split(b'\n')[:-1];cycle=None
    for line in reversed(lines):
        try:cycle=int(line.split(b',',1)[0]);break
        except ValueError:continue
    return dict(pid=pid,start_ticks=int(v[19]),cpu_ticks=int(v[11])+int(v[12]),cycle=cycle,
                trace_bytes=trace.stat().st_size if trace.exists() else 0,exe=str((p/'exe').resolve()),
                cwd=str((p/'cwd').resolve()),cgroup=(p/'cgroup').read_text(),
                argv=(p/'cmdline').read_bytes().decode().strip('\0').split('\0'),time=time.time())

def main(out,digest):
    app.disk_gate(out,digest,app.IMAGE)
    c.require(not (out/'launch.json').exists() and not (app.HERE/'LAUNCH_RECEIPT.json').exists(),'No duplicate launch')
    initial=props()
    c.require(initial['Id']==app.UNIT and initial['LoadState']=='not-found' and initial['ActiveState']=='inactive' and
              initial['MainPID']=='0' and initial['ControlGroup']=='','Existing/unknown unit; no duplicate')
    resources=c.common.resources(out,1,c.read(out/'plan.json')['reserved_slots'])
    ready=c.read(out/'ready.json');c.require(ready['plan_sha256']==digest,'Ready plan identity')
    start=time.time();r=subprocess.run(ready['service_command'],env=busenv(),text=True,capture_output=True,timeout=30)
    c.common.save(app.HERE/'LAUNCH_RECEIPT.json',dict(command=ready['service_command'],actual_wait_returncode=r.returncode,
      stdout=r.stdout,stderr=r.stderr,started=start,resources=resources,initial_unit=initial,plan_sha256=digest,
      launcher_sha256=c.sha(Path(__file__)),authorization='Explicit main once-M6 after Hilbert and Host; no extra gate'))
    c.require(r.returncode==0,'Service launch failed; do not retry automatically')
    trace=out/'replay/tests'/app.NAME/'commit_trace.csv';deadline=time.monotonic()+90;before=None
    expected='+COMMIT_TRACE='+str(trace)
    while time.monotonic()<deadline:
        found=[]
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():continue
            try:
                argv=(p/'cmdline').read_bytes().decode().strip('\0').split('\0')
                if expected in argv and Path(argv[0]).name=='simv':found.append(int(p.name))
            except (FileNotFoundError,ProcessLookupError,PermissionError,UnicodeError):continue
        c.require(len(found)<=1,'Duplicate own simv')
        if found:
            before=sample(found[0],trace)
            if before['cycle'] is not None and before['cycle']>0:break
        if (out/'complete.json').exists():break
        time.sleep(2)
    c.require(before is not None and before['cycle'] is not None and before['cycle']>0,'No positive own trace within bounded discovery; inspect saved service evidence, no retry')
    time.sleep(6);after=sample(before['pid'],trace);owner=props()
    ledger=c.read(app.IMAGE/'image.json')
    good=(after['start_ticks']==before['start_ticks'] and after['cpu_ticks']>before['cpu_ticks'] and
          after['cycle']>before['cycle']>0 and after['trace_bytes']>before['trace_bytes'] and
          after['exe']==str(Path(ledger['simv']).resolve()) and after['cwd']==str(trace.parent/'work') and
          '+NO_FSDB' in after['argv'] and owner['ControlGroup'] in [x.split(':',2)[-1] for x in after['cgroup'].splitlines()] and
          owner['MainPID']==str(c.read(out/'launch.json')['owner']['pid']))
    c.common.save(app.HERE/'STARTUP.json',dict(status='CONFIRMED_M6_SIMV_CPU_CYCLE_PROGRESS' if good else 'NOT_CONFIRMED',
      plan_sha256=digest,before=before,after=after,owner=owner,automatic_terminal_checker=True,
      image=ledger['simv'],baseline_not_current_worktree=True,long_polling=False))
    c.require(good,'Startup identity/progress not confirmed; no automatic retry')
    print(json.dumps(dict(status='CONFIRMED_M6_SIMV_CPU_CYCLE_PROGRESS',pid=after['pid'],worker=owner['MainPID'],
      cycles=[before['cycle'],after['cycle']],cpu_ticks=[before['cpu_ticks'],after['cpu_ticks']],unit=app.UNIT),indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--plan-sha256',required=True)
    a=p.parse_args();main(a.out.resolve(),a.plan_sha256)
