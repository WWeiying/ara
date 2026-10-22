"""One exact reviewed launch, two startup samples; never reads active CSV."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import time
import checker as c
import replay as r

def sample(out):
    owned=[];root=out/'replay/tests'/c.ID
    expected_simv=Path(c.read(r.IMAGE/'image.json')['simv']).resolve()
    exact_args=['+COMMIT_TRACE='+str(root/'commit_trace.csv'),'+PRELOAD='+str(root/'input.elf'),'+TESTCASE='+c.ID]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            argv=proc.joinpath('cmdline').read_bytes().decode(errors='replace').strip('\0').split('\0')
            if not argv or Path(argv[0]).name!='simv' or not all(arg in argv for arg in exact_args):continue
            executable=proc.joinpath('exe').resolve()
            if executable!=expected_simv:continue
            fields=proc.joinpath('stat').read_text().rsplit(')',1)[1].split()
            owned.append(dict(pid=int(proc.name),argv=argv,cpu_ticks=int(fields[11])+int(fields[12]),start_ticks=int(fields[19]),
                cgroup=proc.joinpath('cgroup').read_text(),actual_executable=str(executable)))
        except (FileNotFoundError,ProcessLookupError):continue
    path=root/'commit_trace.csv';elf=root/'input.elf'
    return dict(time=time.time(),owned=owned,private_elf_sha256=c.sha(elf) if elf.is_file() else None,
        trace=dict(path=str(path),bytes=path.stat().st_size) if path.exists() else None)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--entry',type=Path,required=True);parser.add_argument('--entry-sha256',required=True)
    args=parser.parse_args();out=args.out.resolve()
    c.require(out.parent==c.HERE,'Owned exact prepared output')
    digest=c.sha(out/'plan.json');plan=c.read(out/'plan.json');r.validate(plan,r.IMAGE)
    r.reviews(plan,digest,args.entry,args.entry_sha256,None,None)
    ready=c.read(out/'ready.json');c.require(ready['plan_sha256']==digest,'Ready exact plan')
    command=shlex.split(ready['service_command'])+['--entry-review',str(args.entry),'--entry-review-sha256',args.entry_sha256]
    runtime=Path('/run/user')/str(os.getuid());c.require(runtime.is_dir() and (runtime/'bus').is_socket(),'Trusted actual user bus')
    env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(runtime/'bus'))
    r.durable(out/'launch_invocation.json',dict(command=command,plan_sha256=digest,entry=str(args.entry),entry_sha256=args.entry_sha256,
        launcher_pid=os.getpid(),time=time.time(),no_retry=True))
    start=time.monotonic()
    with (out/'service_submission.log').open('x') as log:
        child=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT)
        rc=child.wait(timeout=30)
        r.durable(out/'service_submission.json',dict(actual_wait_returncode=rc,pid=child.pid,elapsed_s=time.monotonic()-start,time=time.time()))
    c.require(rc==0,'Actual systemd submission failed; no retry')
    time.sleep(25);first=sample(out);time.sleep(5);second=sample(out)
    query=subprocess.run(['systemctl','--user','show',r.UNIT,'--property=Id,LoadState,ActiveState,SubState,MainPID,ControlGroup,ExecStart,ExecStopPost,TimeoutStopUSec'],
        env=env,text=True,capture_output=True,timeout=10)
    props=dict(line.split('=',1) for line in query.stdout.splitlines() if '=' in line)
    growing=(len(first['owned'])==len(second['owned'])==1 and first['owned'][0]['pid']==second['owned'][0]['pid'] and
        first['owned'][0]['start_ticks']==second['owned'][0]['start_ticks'] and second['owned'][0]['cpu_ticks']>first['owned'][0]['cpu_ticks'] and
        first['trace'] is not None and second['trace'] is not None and second['trace']['bytes']>first['trace']['bytes'] and
        first['private_elf_sha256']==second['private_elf_sha256']==c.ELF_SHA and
        r.UNIT in second['owned'][0]['cgroup'] and query.returncode==0 and props.get('ActiveState')=='active' and int(props.get('MainPID','0'))>0)
    r.durable(out/'startup_observation.json',dict(status='LIVE_CPU_TRACE_GROWTH_CONFIRMED' if growing else 'NOT_CONFIRMED_NO_RETRY',
        first=first,second=second,actual_systemctl_returncode=query.returncode,properties=props,stderr=query.stderr,
        no_poll_after_this=True,active_CSV_content_reads=0,DUT_PASS_claimed=False,collector='Frozen ExecStopPost metadata-only child'))
    print(dict(status='LIVE_CPU_TRACE_GROWTH_CONFIRMED' if growing else 'NOT_CONFIRMED_NO_RETRY',worker_pid=props.get('MainPID'),
        simv_pids=[item['pid'] for item in second['owned']],out=str(out)),flush=True)
    return int(not growing)

if __name__=='__main__':raise SystemExit(main())

