"""Authorized exact-argv submission and one bounded startup observation only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
OUT=HERE.parent
ROOT=OUT.parent
UNIT='ara-fp-unboxed-full17920-m9-01.service'
NAME='fp_compare_unboxed_e16_mf4_full17920'
PINS={
    ROOT/'parent_runtime_admission01.json':'a280fb18c8b2600c2cfdc882df1f4693469e0009bf67c2297825a5e72a3a7878',
    ROOT/'ENTRY_REVIEW.json':'d22f9d4999cc334f0a23f93d5d9c3f7729648fe669d9cfd5cf4afa1acf2cc781',
    OUT/'plan.json':'b6d0677124a045a35294a1c0be4a7b0f6a004f52e9f570e6e5b9478c4296bdbd',
    OUT/'ready.json':'89c37924aefdcca6ada87dfb1430ce0bc8e6853c4827297eec10340b37e1339f',
}

def require(ok,msg):
    if not ok: raise ValueError(msg)
def read(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,obj):
    with Path(p).open('x') as f:
        json.dump(obj,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    fd=os.open(Path(p).parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
def verify():
    for p,h in PINS.items(): require(sha(p)==h,'Admission pin drift '+str(p))

def manager(env):
    keys='Id,LoadState,ActiveState,SubState,MainPID,ControlGroup,RuntimeMaxUSec,RemainAfterExit,KillMode,Restart,ExecStopPost'
    cmd=['systemctl','--user','show',UNIT,'--property='+keys]
    q=subprocess.run(cmd,env=env,text=True,capture_output=True,timeout=15)
    props={}
    for line in q.stdout.splitlines():
        require('=' in line,'Unknown manager output')
        k,v=line.split('=',1);require(k not in props,'Duplicate manager property');props[k]=v
    return dict(command=cmd,returncode=q.returncode,stdout=q.stdout,stderr=q.stderr,properties=props,observed_at=time.time())

def process(pid):
    p=Path('/proc')/str(pid);raw=(p/'stat').read_text();fields=raw[raw.rfind(')')+2:].split()
    return dict(pid=pid,start_ticks=int(fields[19]),cpu_ticks=int(fields[11])+int(fields[12]),
        argv=(p/'cmdline').read_bytes().decode().rstrip('\0').split('\0'),exe=str((p/'exe').resolve()),
        cwd=str((p/'cwd').resolve()),cgroup=(p/'cgroup').read_text(),observed_at=time.time())

def candidates(group,simv):
    found=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            if str((p/'exe').resolve())!=str(simv):continue
            x=process(int(p.name))
            if group in [r.split(':',2)[-1] for r in x['cgroup'].splitlines()]:found.append(x)
        except (FileNotFoundError,ProcessLookupError,PermissionError):continue
    return found

def main():
    verify()
    require(not any((OUT/p).exists() for p in ('replay','launch.json','complete.json','service_exit.json')),'Existing execution; no repeat')
    require(not(HERE/'launch_command.json').exists(),'Submission already attempted')
    uid=os.getuid();runtime=Path('/run/user')/str(uid)
    require(runtime.stat().st_uid==uid and (runtime/'bus').is_socket(),'Trusted user bus')
    env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(runtime/'bus'))
    old=manager(env);save(HERE/'unit_before.json',old);p=old['properties']
    require(old['returncode']==0 and not old['stderr'] and p['Id']==UNIT and p['LoadState']=='not-found'
            and p['MainPID']=='0' and p['ControlGroup']=='' and p['ActiveState']=='inactive' and p['SubState']=='dead',
            'Fresh absent unit required; no replace/restart/GC exit inference')
    preflight="""import replay as r
out=r.HERE/'prepared02'
digest='b6d0677124a045a35294a1c0be4a7b0f6a004f52e9f570e6e5b9478c4296bdbd'
r.disk_gate(out,digest)
approval=r.approval_gate(out,digest,r.HERE/'ENTRY_REVIEW.json','d22f9d4999cc334f0a23f93d5d9c3f7729648fe669d9cfd5cf4afa1acf2cc781',r.HERE/'parent_runtime_admission01.json','a280fb18c8b2600c2cfdc882df1f4693469e0009bf67c2297825a5e72a3a7878')
resource=r.common.resources(out,1,0)
r.durable(out/'startup01/preflight.json',dict(approval_pins=approval,resources=resource,status='ACTUAL_PREFLIGHT_PASS_NOT_LAUNCH'))
"""
    cmd=[sys.executable,'-B','-c',preflight]
    save(HERE/'preflight_command.json',dict(command=cmd,cwd=str(ROOT),timeout_s=120))
    t=time.monotonic();q=subprocess.run(cmd,cwd=ROOT,env=env,text=True,capture_output=True,timeout=120)
    save(HERE/'preflight_wait.json',dict(returncode=q.returncode,stdout=q.stdout,stderr=q.stderr,elapsed_s=time.monotonic()-t))
    require(q.returncode==0,'Actual immutable worker preflight failed; no launch')
    verify();ready=read(OUT/'ready.json');argv=ready['service_argv']
    substitutions={'__ACTUAL_INDEPENDENT_ENTRY_SHA__':PINS[ROOT/'ENTRY_REVIEW.json'],
        '__NEW_PARENT_RUN_JSON__':str(ROOT/'parent_runtime_admission01.json'),
        '__ACTUAL_PARENT_SHA__':PINS[ROOT/'parent_runtime_admission01.json']}
    require(all(argv.count(k)==1 for k in substitutions),'Exact three placeholders')
    actual=[substitutions.get(x,x) for x in argv]
    require('--property=RemainAfterExit=no' in actual and '--property=RemainAfterExit=yes' not in actual,'Automatic exit contract')
    require(actual[actual.index('--entry-review')+1]==str(ROOT/'ENTRY_REVIEW.json'),'Exact existing entry path')
    save(HERE/'launch_command.json',dict(command=actual,ready_sha256=PINS[OUT/'ready.json'],
        substitutions=substitutions,admission_pins={str(p):h for p,h in PINS.items()},launcher_sha256=sha(__file__)))
    t=time.monotonic();q=subprocess.run(actual,cwd=ROOT,env=env,text=True,capture_output=True,timeout=30)
    save(HERE/'systemd_run.json',dict(actual_returncode=q.returncode,stdout=q.stdout,stderr=q.stderr,
        elapsed_s=time.monotonic()-t,submitted_at=time.time()))
    require(q.returncode==0,'Submission failed; no retry')
    # Only bounded discovery, then one positive-baseline CPU/file-size interval.
    simv=Path(read(read(OUT/'plan.json')['image']+'/image.json')['simv']).resolve()
    trace=OUT/'replay/tests'/NAME/'commit_trace.csv'
    discovery=[];first=None;state=None
    for _ in range(6):
        time.sleep(20)
        state=manager(env);props=state['properties'];group=props.get('ControlGroup','')
        found=candidates(group,simv) if group else []
        discovery.append(dict(manager=state,matching_simv_pids=[x['pid'] for x in found],trace_exists=trace.exists()))
        if len(found)==1 and trace.exists() and trace.stat().st_size>0:
            first=found[0];break
        if (OUT/'complete.json').exists() or props.get('ActiveState') in ('failed','inactive'):break
    save(HERE/'startup_discovery.json',discovery)
    require(first is not None,'Startup not confirmed within bound; do not restart')
    props=state['properties'];launch=read(OUT/'launch.json')
    require(state['returncode']==0 and not state['stderr'] and props['LoadState']=='loaded' and
        props['ActiveState']=='active' and props['SubState']=='running' and props['RemainAfterExit']=='no' and
        props['RuntimeMaxUSec']=='3h 40min' and props['KillMode']=='control-group' and props['Restart']=='no' and
        str(ROOT/'exit_hook02.py') in props['ExecStopPost'] and str(OUT) in props['ExecStopPost'], 'Actual service properties')
    require(int(props['MainPID'])==launch['owner']['pid'] and first['cwd']==str(trace.parent/'work') and
        first['argv']==read(trace.parent/'command.json')['command'],'Actual owner and private simulator command')
    worker=process(int(props['MainPID']));size1=trace.stat().st_size
    time.sleep(3)
    second=process(first['pid']);size2=trace.stat().st_size
    require(second['start_ticks']==first['start_ticks'] and second['exe']==first['exe'] and second['argv']==first['argv'],
            'Same simulator generation')
    require(second['cpu_ticks']>first['cpu_ticks'] and size2>size1>0,'Positive CPU/CSV byte growth')
    verify()
    save(HERE/'startup_receipt.json',dict(status='ACTUAL_M9_SIMULATOR_STARTUP_PROGRESS_CONFIRMED_NOT_TERMINAL',
        unit=UNIT,worker=worker,manager=state,simulator_before=first,simulator_after=second,
        csv_bytes_before=size1,csv_bytes_after=size2,CSV_rows_read=0,interval_s=3,
        plan_sha256=PINS[OUT/'plan.json'],ready_sha256=PINS[OUT/'ready.json'],
        admission_sha256=PINS[ROOT/'parent_runtime_admission01.json'],budget_s=[10800,12000,13200],
        retries=0,terminal_acceptance=False,observations_finished=True))
    print(json.dumps(dict(status='STARTUP_CONFIRMED',worker=worker['pid'],simv=first['pid'],
        csv_bytes=[size1,size2],cpu_ticks=[first['cpu_ticks'],second['cpu_ticks']],receipt=str(HERE/'startup_receipt.json'))),flush=True)

if __name__=='__main__':
    try:main()
    except BaseException as error:
        save(HERE/'launcher_firstcause.json',dict(error=repr(error),observed_at=time.time(),retry=False))
        raise
