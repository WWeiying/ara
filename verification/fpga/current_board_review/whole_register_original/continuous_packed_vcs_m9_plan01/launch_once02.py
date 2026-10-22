"""Single reviewed service submission and two fixed startup samples, no retry."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import time

HERE=Path(__file__).resolve().parent
OUT=HERE/'prepared02'
UNIT='ara-whole-continuous1134-m9-01.service'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,data):
    with (OUT/name).open('x') as f:json.dump(data,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def sample():
    owned=[];prefix='+COMMIT_TRACE='+str(OUT)+'/replay/'
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            argv=proc.joinpath('cmdline').read_bytes().decode(errors='replace').strip('\0').split('\0')
            if not argv or Path(argv[0]).name!='simv' or not any(x.startswith(prefix) for x in argv):continue
            fields=proc.joinpath('stat').read_text().rsplit(')',1)[1].split()
            owned.append(dict(pid=int(proc.name),argv=argv,cpu_ticks=int(fields[11])+int(fields[12]),
                cgroup=proc.joinpath('cgroup').read_text()))
        except (FileNotFoundError,ProcessLookupError):continue
    path=OUT/'replay/tests/whole_continuous_packed1134/commit_trace.csv'
    trace=None
    if path.exists():
        size=path.stat().st_size
        with path.open('rb') as f:
            f.seek(max(0,size-8192));tail=f.read();lines=tail.splitlines()
        if not tail.endswith(b'\n'):lines=lines[:-1]
        rows=[line.decode(errors='replace').split(',') for line in lines if len(line.split(b','))==14]
        trace=dict(path=str(path),bytes=size,last_observed_line=','.join(rows[-1]) if rows else '',
                   complete_cycle=int(rows[-1][0]) if rows else None,
                   complete_retire=max((int(row[2]) for row in rows if row[1]=='retire'),default=None))
    return dict(time=time.time(),owned=owned,trace=trace)

p=argparse.ArgumentParser();p.add_argument('--entry',type=Path,required=True);p.add_argument('--entry-sha256',required=True)
p.add_argument('--plan-sha256',required=True);p.add_argument('--out',type=Path,default=OUT);a=p.parse_args()
OUT=a.out.resolve();assert OUT.parent==HERE
PLAN=a.plan_sha256
assert sha(OUT/'plan.json')==PLAN and sha(a.entry)==a.entry_sha256
review=json.loads(a.entry.read_text());plan=json.loads((OUT/'plan.json').read_text())
assert review['status']=='NO_BLOCKER_ENTRY_REVIEW' and review['plan_sha256']==PLAN and review['pins']==plan['pins']
ready=json.loads((OUT/'ready.json').read_text());assert ready['plan_sha256']==PLAN
command=shlex.split(ready['service_command'])+['--entry-review',str(a.entry),'--entry-review-sha256',a.entry_sha256]
env=dict(os.environ,XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}',DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
save('launch_invocation.json',dict(command=command,plan_sha256=PLAN,entry=str(a.entry),entry_sha256=a.entry_sha256,
    actual_launcher_pid=os.getpid(),time=time.time(),no_retry=True))
completed=subprocess.run(command,env=env,text=True,capture_output=True,timeout=30)
save('service_submission.json',dict(returncode=completed.returncode,stdout=completed.stdout,stderr=completed.stderr,time=time.time()))
if completed.returncode:raise SystemExit(completed.returncode)
time.sleep(25);first=sample();time.sleep(5);second=sample()
q=subprocess.run(['systemctl','--user','show',UNIT,'--property=Id,LoadState,ActiveState,SubState,MainPID,ControlGroup'],
    env=env,text=True,capture_output=True,timeout=10)
props=dict(line.split('=',1) for line in q.stdout.splitlines() if '=' in line)
growing=(len(first['owned'])==len(second['owned'])==1 and first['owned'][0]['pid']==second['owned'][0]['pid'] and
    second['owned'][0]['cpu_ticks']>first['owned'][0]['cpu_ticks'] and first['trace'] is not None and
    second['trace'] is not None and second['trace']['bytes']>first['trace']['bytes'] and
    first['trace']['complete_cycle'] is not None and second['trace']['complete_cycle'] is not None and
    second['trace']['complete_cycle']>first['trace']['complete_cycle'] and
    UNIT in second['owned'][0]['cgroup'] and q.returncode==0 and props.get('ActiveState')=='active' and int(props.get('MainPID','0'))>0)
save('startup_observation.json',dict(status='LIVE_CPU_CSV_GROWTH_CONFIRMED' if growing else 'NOT_CONFIRMED_NO_RETRY',
    first=first,second=second,actual_systemctl_returncode=q.returncode,properties=props,stderr=q.stderr,
    admission_receipt=str(OUT/'launch.json'),no_poll_after_this=True,DUT_PASS_claimed=False))
print(json.dumps(dict(status='LIVE_CPU_CSV_GROWTH_CONFIRMED' if growing else 'NOT_CONFIRMED_NO_RETRY',
    main_pid=props.get('MainPID'),simv_pids=[x['pid'] for x in second['owned']],out=str(OUT))),flush=True)
raise SystemExit(0 if growing else 1)
