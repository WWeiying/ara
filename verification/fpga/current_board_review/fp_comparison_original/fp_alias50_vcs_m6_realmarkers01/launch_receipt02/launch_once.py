"""Authorized once-only management launch and one startup observation."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import replay as r

HERE=Path(__file__).resolve().parent
PLAN=r.HERE/'prepared01'
PARENT=r.HERE/'parent_review.json'
READY=r.read(r.HERE/'READY.json')

def service():
    keys='Id,LoadState,ActiveState,SubState,MainPID,Result,ExecMainCode,ExecMainStatus,ControlGroup'
    q=subprocess.run(['systemctl','--user','show',r.UNIT,'--property='+keys],
                     text=True,capture_output=True,timeout=10)
    r.require(q.returncode==0,'Service metadata query failed')
    return dict(line.split('=',1) for line in q.stdout.splitlines())

def children(pid):
    path=Path('/proc')/str(pid)/'task'/str(pid)/'children'
    if not path.exists():return []
    found=[int(x) for x in path.read_text().split()]
    return found+[d for p in found for d in children(p)]

def sample():
    props=service();pid=int(props['MainPID']);procs=[]
    simv=Path(r.common.read(r.IMAGE/'image.json')['simv']).resolve()
    for p in children(pid) if pid else []:
        try:
            base=Path('/proc')/str(p)
            exe=(base/'exe').resolve()
            if exe!=simv:continue
            tail=(base/'stat').read_text().rsplit(')',1)[1].split()
            procs.append(dict(pid=p,exe=str(exe),ticks=int(tail[11])+int(tail[12]),
                              start_ticks=int(tail[19]),command=(base/'cmdline').read_bytes().replace(b'\0',b' ').decode()))
        except (FileNotFoundError,ProcessLookupError):continue
    trace=PLAN/'replay/tests'/r.NAME/'commit_trace.csv'
    return dict(time=time.time(),service=props,simv=procs,
                trace_bytes=trace.stat().st_size if trace.exists() else None,CSV_content_reads=0)

def main():
    r.require(not(HERE/'ATTEMPT_STARTED.json').exists(),'No duplicate launch')
    digest=READY['plan_sha256'];ph=r.sha(PARENT)
    approval=r.authorization_gate(digest,PARENT,ph)
    r.terminal_plan_gate(PLAN,digest,r.IMAGE)
    cmd=[str(PARENT) if x=='UNRESOLVED_PARENT_REVIEW_JSON' else
         ph if x=='UNRESOLVED_PARENT_REVIEW_SHA256' else x
         for x in shlex.split(READY['service_command'])]
    r.require('--unit='+r.UNIT in cmd and r.UNIT!='ara-fp-alias-original50-m6-01.service','New unit only')
    r.durable(HERE/'ATTEMPT_STARTED.json',dict(command=cmd,parent_path=str(PARENT),
                  parent_sha256=ph,approval_pins=approval,plan_sha256=digest,started=time.time()))
    start=time.monotonic()
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    stdout,stderr=p.communicate()
    r.durable(HERE/'actual_launch_exit_unvalidated.json',dict(returncode=p.returncode,
                  elapsed_s=time.monotonic()-start,management_pid=p.pid,command=cmd,
                  DUT_architectural_acceptance=False))
    r.durable(HERE/'launch_result.json',dict(returncode=p.returncode,stdout=stdout,stderr=stderr))
    r.require(p.returncode==0,'Management launch failed; no retry')
    # One bounded startup confirmation, not periodic simulation polling.
    time.sleep(50)
    a=sample();r.durable(HERE/'startup_before.json',a)
    time.sleep(2)
    b=sample();r.durable(HERE/'startup_after.json',b)
    r.require(b['service']['ActiveState']=='active' and b['service']['SubState']=='running','Worker not active')
    r.require(len(a['simv'])==len(b['simv'])==1,'Exactly one owned actual simv')
    pa,pb=a['simv'][0],b['simv'][0]
    r.require((pa['pid'],pa['start_ticks'])==(pb['pid'],pb['start_ticks']) and pb['ticks']>pa['ticks'],'Actual simv CPU not progressing')
    r.require(a['trace_bytes'] is not None and b['trace_bytes']>a['trace_bytes'],'Trace file not growing')
    r.durable(HERE/'STARTUP_CONFIRMED.json',dict(worker_pid=int(b['service']['MainPID']),
        simv_pid=pb['pid'],cpu_tick_delta=pb['ticks']-pa['ticks'],trace_before=a['trace_bytes'],
        trace_after=b['trace_bytes'],parent_sha256=ph,plan_sha256=digest,
        unit=r.UNIT,CSV_content_reads=0,no_retry=True))
    print(json.dumps(r.read(HERE/'STARTUP_CONFIRMED.json')),flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
