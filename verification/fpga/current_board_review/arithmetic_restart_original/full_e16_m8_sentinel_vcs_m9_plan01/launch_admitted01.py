"""One admitted service submission and one bounded two-sample startup check."""
import os,shlex,subprocess,time
from pathlib import Path
import checker as c
import replay as r
OUT=c.HERE/'prepared01'
ENTRY=c.HERE.parent/'m8_sentinel_mask_static_review_hilbert01/WORKER_ENTRY01.json'
ENTRY_SHA='dec630626c9ca839037a0d0ef3e413614b5a9bf98b387f3d5b66fb3baee4cff3'
PARENT=c.HERE/'parent_runtime_admission01.json'
PARENT_SHA='ad9ef5e01aa944a49458fdf18b4daa946765e7334f76bfedf23850bc707a9ba0'
PLAN_SHA='0a2820506439278384569a58f72b76fcb72ae5276f4f302ba6a31f0c65a6335e'
def sample():
    root=OUT/'replay/tests'/c.ID
    expected=c.read(OUT/'dryrun.json')['commands'][0]['command']
    owned=[];workers=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            argv=proc.joinpath('cmdline').read_bytes().decode(errors='replace').strip('\0').split('\0')
            simulation=bool(argv and Path(argv[0]).name=='simv' and argv==expected)
            worker=bool(argv and Path(argv[0]).name.startswith('python') and str(c.HERE/'replay.py') in argv
                and str(OUT) in argv and 'run' in argv)
            if not simulation and not worker:continue
            fields=proc.joinpath('stat').read_text().rsplit(')',1)[1].split()
            item=dict(pid=int(proc.name),argv=argv,cpu_ticks=int(fields[11])+int(fields[12]),
                start_ticks=int(fields[19]),cgroup=proc.joinpath('cgroup').read_text(),
                actual_executable=str(proc.joinpath('exe').resolve()))
            (owned if simulation else workers).append(item)
        except (FileNotFoundError,ProcessLookupError,PermissionError):continue
    path=root/'commit_trace.csv';elf=root/'input.elf'
    return dict(time=time.time(),owned=owned,workers=workers,
        private_elf_sha256=c.sha(elf) if elf.is_file() else None,
        trace=dict(path=str(path),bytes=path.stat().st_size) if path.exists() else None)
def main():
    c.require(c.sha(OUT/'plan.json')==PLAN_SHA,'Exact admitted plan')
    plan=c.read(OUT/'plan.json');r.validate(plan,r.IMAGE)
    r.reviews(plan,PLAN_SHA,ENTRY,ENTRY_SHA,PARENT,PARENT_SHA)
    c.require(not (OUT/'launch_invocation.json').exists() and not (OUT/'replay').exists(),'One submission only')
    ready=c.read(OUT/'ready.json');c.require(ready['plan_sha256']==PLAN_SHA,'Exact ready')
    command=shlex.split(ready['service_command'])+['--entry-review',str(ENTRY),'--entry-review-sha256',ENTRY_SHA,
        '--parent-review',str(PARENT),'--parent-review-sha256',PARENT_SHA]
    runtime=Path('/run/user')/str(os.getuid())
    c.require(runtime.is_dir() and (runtime/'bus').is_socket(),'Trusted actual user bus')
    env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(runtime/'bus'))
    r.durable(OUT/'launch_invocation.json',dict(command=command,plan_sha256=PLAN_SHA,
        entry_review_sha256=ENTRY_SHA,parent_review_sha256=PARENT_SHA,launcher_pid=os.getpid(),time=time.time(),
        launcher_sha256=c.sha(__file__),resource_ownership_gate='Exactly once in actual direct service worker',no_retry=True))
    start=time.monotonic();timed=False
    with (OUT/'service_submission.log').open('x') as log:
        child=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT)
        try:rc=child.wait(timeout=30)
        except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
        r.durable(OUT/'service_submission.json',dict(actual_wait_returncode=rc,pid=child.pid,
            elapsed_s=time.monotonic()-start,timed_out=timed,retries=0))
    c.require(rc==0 and not timed,'Submission failed; no resubmission')
    time.sleep(25);first=sample();time.sleep(5);second=sample()
    query=subprocess.run(['systemctl','--user','show',r.UNIT,
        '--property=Id,ActiveState,SubState,MainPID,ControlGroup,ExecStart,ExecStopPost,RuntimeMaxUSec,KillMode,Restart'],
        env=env,text=True,capture_output=True,timeout=10)
    props=dict(line.split('=',1) for line in query.stdout.splitlines() if '=' in line)
    growth=(len(first['owned'])==len(second['owned'])==len(second['workers'])==1
        and first['owned'][0]['pid']==second['owned'][0]['pid']
        and first['owned'][0]['start_ticks']==second['owned'][0]['start_ticks']
        and second['owned'][0]['cpu_ticks']>first['owned'][0]['cpu_ticks']
        and first['trace'] is not None and second['trace'] is not None
        and second['trace']['bytes']>first['trace']['bytes']
        and first['private_elf_sha256']==second['private_elf_sha256']==c.ELF_SHA
        and r.UNIT in second['owned'][0]['cgroup'] and r.UNIT in second['workers'][0]['cgroup']
        and query.returncode==0 and props.get('ActiveState')=='active'
        and int(props.get('MainPID','0'))==second['workers'][0]['pid'])
    hook=(str(c.HERE/'exit_hook.py') in props.get('ExecStopPost','')
        and str(OUT) in props.get('ExecStopPost','')
        and plan['pins'][str(c.HERE/'exit_hook.py')]==c.sha(c.HERE/'exit_hook.py')
        and plan['pins'][str(c.HERE/'collect.py')]==c.sha(c.HERE/'collect.py'))
    r.durable(OUT/'startup_observation.json',dict(
        status='LIVE_CPU_TRACE_GROWTH_AND_EXITCOLLECTOR_CONFIRMED' if growth and hook else 'NOT_CONFIRMED_NO_RETRY',
        first=first,second=second,actual_systemctl_returncode=query.returncode,properties=props,stderr=query.stderr,
        exitcollector_attached=hook,no_poll_after_this=True,active_CSV_content_reads=0,DUT_PASS_claimed=False))
    print(dict(status='LIVE_CONFIRMED' if growth and hook else 'NOT_CONFIRMED_NO_RETRY',
        worker_pid=props.get('MainPID'),simv_pids=[item['pid'] for item in second['owned']],out=str(OUT)),flush=True)
    return int(not (growth and hook))
if __name__=='__main__':raise SystemExit(main())
