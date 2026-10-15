"""One corrected startup observation; no launch, stop, or CSV content reads."""
import importlib.util
import os
from pathlib import Path
import sys
import time
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('owned_launch_metadata',Path(__file__).with_name('launch_once.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def sample():
    p=m.service()
    base=Path('/sys/fs/cgroup')/p['ControlGroup'].lstrip('/')
    ids={int(x) for f in base.rglob('cgroup.procs') for x in f.read_text().split()}
    procs=[]
    for pid in ids:
        proc=Path('/proc')/str(pid)
        argv=(proc/'cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
        if '+TESTCASE='+m.r.NAME not in argv:continue
        tail=(proc/'stat').read_text().rsplit(')',1)[1].split()
        procs.append(dict(pid=pid,exe=str((proc/'exe').resolve()),argv=argv,
                          ticks=int(tail[11])+int(tail[12]),start_ticks=int(tail[19]),
                          cgroup=(proc/'cgroup').read_text()))
    raw=m.PLAN/'replay/tests'/m.r.NAME/'commit_trace.csv'
    return dict(service=p,simv=procs,trace_bytes=raw.stat().st_size,time=time.time(),CSV_content_reads=0)

a=sample();m.r.durable(m.HERE/'startup_cgroup_before.json',a)
time.sleep(2)
b=sample();m.r.durable(m.HERE/'startup_cgroup_after.json',b)
m.r.require(len(a['simv'])==len(b['simv'])==1,'One owned simv')
x,y=a['simv'][0],b['simv'][0]
m.r.require(x['pid']==y['pid'] and x['start_ticks']==y['start_ticks'] and y['ticks']>x['ticks'] and b['trace_bytes']>a['trace_bytes'],'CPU/trace progress')
m.r.require(y['argv']==m.r.read(m.PLAN/'replay/tests'/m.r.NAME/'command.json')['command'],'Actual command')
m.r.durable(m.HERE/'STARTUP_CONFIRMED_CGROUP.json',dict(worker_pid=int(b['service']['MainPID']),simv_pid=y['pid'],
    cpu_tick_delta=y['ticks']-x['ticks'],trace_before=a['trace_bytes'],trace_after=b['trace_bytes'],
    unit=m.r.UNIT,CSV_content_reads=0,no_retry=True,observer_only=True,
    earlier_observation_limitation='Main-thread children misses simulator spawned by runner worker thread'))
print(m.r.read(m.HERE/'STARTUP_CONFIRMED_CGROUP.json'),flush=True)
