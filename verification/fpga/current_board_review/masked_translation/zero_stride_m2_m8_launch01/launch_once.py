#!/usr/bin/env python3
"""Once-only M7 launch receipts and one initial owned CPU/trace progress check."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parent.parent
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x') as f:
        json.dump(v,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def item(l):
    h=ROOT/f'zero_stride_e64_m{l}_original16_vcs_m7_plan01'
    return h,h/'prepared01'
def execute(l,mode):
    h,out=item(l);r=read(out/'ready.json')
    assert sha(out/'plan.json')==r['plan_sha256']
    cmd=list(r['command'])
    if mode=='dryrun':
        cmd[3]='dryrun';cmd.remove('--authorize-run')
    else:cmd=r['service_command']
    receipt=out/(mode+'_executor_wait.json');assert not receipt.exists()
    env=dict(os.environ)
    bus=Path('/run/user')/str(os.getuid())
    env.update(XDG_RUNTIME_DIR=str(bus),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(bus/'bus'))
    begin=time.monotonic()
    with (out/(mode+'_launcher.stdout')).open('x') as stdout,(out/(mode+'_launcher.stderr')).open('x') as stderr:
        child=subprocess.Popen(cmd,stdout=stdout,stderr=stderr,env=env)
        rc=child.wait()
        save(receipt,dict(actual_wait_exit=rc,child_pid=child.pid,command=cmd,elapsed_s=time.monotonic()-begin,
          plan_sha256=r['plan_sha256'],architectural_acceptance=False))
    assert rc==0,(l,mode,rc)
    return h,out
def query(l):
    h,out=item(l);plan=read(out/'plan.json');unit=plan['unit']
    bus=Path('/run/user')/str(os.getuid())
    env=dict(os.environ,XDG_RUNTIME_DIR=str(bus),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(bus/'bus'))
    cmd=['systemctl','--user','show',unit,'--property=Id,MainPID,ControlGroup,ActiveState,SubState,Result,ExecMainStatus']
    q=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=10)
    assert q.returncode==0
    props=dict(line.split('=',1) for line in q.stdout.splitlines())
    group=props['ControlGroup'];assert group.endswith('/'+unit)
    pids=[int(x) for x in (Path('/sys/fs/cgroup')/group.lstrip('/')/'cgroup.procs').read_text().split()]
    sims=[]
    for pid in pids:
        p=Path('/proc')/str(pid)
        try:
            args=p.joinpath('cmdline').read_bytes().decode().strip('\0').split('\0')
            if not args or Path(args[0]).name!='simv':continue
            fields=p.joinpath('stat').read_text().rsplit(')',1)[1].split()
            trace=next(Path(a.split('=',1)[1]) for a in args if a.startswith('+COMMIT_TRACE='))
            assert trace.is_relative_to(out/'replay/tests'/plan['case']['id'])
            assert '+TESTCASE='+plan['case']['id'] in args
            assert '+PRELOAD='+str(trace.parent/'input.elf') in args
            sims.append(dict(pid=pid,args=args,cpu_ticks=int(fields[11])+int(fields[12]),
              trace=str(trace),trace_bytes=trace.stat().st_size,cwd=str(p.joinpath('cwd').resolve())))
        except FileNotFoundError:continue
    return dict(properties=props,owned_pids=pids,simulators=sims,time=time.time(),raw_csv_parsed=False)
def main():
    a=argparse.ArgumentParser();a.add_argument('mode',choices=['dryrun','launch']);args=a.parse_args()
    for l in (2,8):execute(l,args.mode)
    if args.mode=='launch':
        time.sleep(25)
        first={l:query(l) for l in (2,8)}
        time.sleep(10)
        for l in (2,8):
            now=query(l);before=first[l]
            progressing=(len(now['simulators'])==len(before['simulators'])==1 and
              now['simulators'][0]['pid']==before['simulators'][0]['pid'] and
              now['simulators'][0]['cpu_ticks']>before['simulators'][0]['cpu_ticks'] and
              now['simulators'][0]['trace_bytes']>before['simulators'][0]['trace_bytes'])
            h,out=item(l);save(out/'initial_progress.json',dict(status='RUNNING_NOT_ACCEPTED' if progressing else 'PROGRESS_NOT_CONFIRMED',
              before=before,after=now,progressing=progressing,automatic_closed_csv_checker=True,no_retry=True))
            print(l,progressing,now['properties'],now['simulators'],flush=True)
if __name__=='__main__':main()

