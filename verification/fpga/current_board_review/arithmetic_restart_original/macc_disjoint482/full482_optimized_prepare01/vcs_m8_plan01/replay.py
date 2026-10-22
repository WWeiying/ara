#!/usr/bin/env python3
"""One immutable M8 full482 run, preserving real monitor outcome before postchecks."""
import argparse
from contextlib import contextmanager
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import threading
import time
import checker as c

sys.dont_write_bytecode=True
HERE=c.HERE
common=c.common
require,read,sha=c.require,c.read,c.sha
UNIT='ara-macc-full482-scalar64-m8-01.service'
TIMEOUT,WORKER,OUTER,JOBS=10800,12000,13200,1
PASS='PASS_FULL482_M8_ARCHITECTURAL_NOT_LINUX'
SOFTWARE_REVIEW=HERE.parent.parent/'full482_optimized_review01/REVIEW.json'
SOFTWARE_REVIEW_SHA='391fa11498565d44cbf24134aa956172e5049a179473ffbe17b162213b23f405'


def save(path,data):
    with Path(path).open('x') as stream:
        json.dump(data,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())


def numeric_gate(outcome):
    code,elapsed,timeout,failure=outcome
    require(type(code) is int and type(timeout) is bool and type(failure) is bool,
        'Actual monitor tuple types')
    return code==0 and not timeout and not failure and 0<=elapsed<=TIMEOUT


def image_gate():
    ledger,repo,framework=common.image_context(c.IMAGE)
    path=c.IMAGE.parents[1]/'BUILD_ACCEPTED.json';build=read(path)
    require(build['status']=='BUILD_ONLY_NOT_DUT_PASS' and
        build['snapshot_sha256']==ledger['snapshot_sha256'] and
        build['image_sha256']==sha(c.IMAGE/'image.json'),'Actual accepted M8 image')
    files=read(Path(ledger['snapshot'])/'snapshot.json')['files']
    require(all(files[p]==h for p,h in build['approved_source_sha256'].items()),'M8 approved source binding')
    pins=common.image_pins(c.IMAGE,ledger,repo);pins[str(path)]=sha(path)
    return ledger,repo,framework,pins


def source_gate():
    ready=read(c.REF/'READY.json')
    require(sha(c.REF/'READY.json')==c.READY_SHA and
        ready['status']=='READY_SOURCE_EQUIVALENT_FULL482_OPTIMIZED_REFERENCE_ONLY_NOT_DUT' and
        (ready['calls'],ready['predecessors'],ready['results'],ready['guards'],ready['helper_instructions'],
        ready['capacity'],ready['vlenb'],ready['physical_mask_bytes'])==(482,481,246784,964,6266,512,128,128) and
        type(ready['actual_reference_child_returncode']) is int and ready['actual_reference_child_returncode']==0,
        'Exact full482 accepted software/reference')
    pins=dict(ready['pins'])
    pre=read(c.REF/'PRE_REFERENCE.json');pins.update(pre['pins'])
    reference=c.REF/'reference/status.json';receipt=c.REF/'reference/execution.json'
    require(sha(reference)==ready['reference_sha256'],'Stored full reference identity')
    require(read(receipt)['actual_child_returncode']==0 and type(read(receipt)['actual_child_returncode']) is int and
        read(receipt)['retries']==0,'Actual reference child receipt')
    review=read(SOFTWARE_REVIEW)
    require(sha(SOFTWARE_REVIEW)==SOFTWARE_REVIEW_SHA and review['ready_sha256']==c.READY_SHA and
        review['verdict']=='NO_BLOCKER_WORK05_SOFTWARE_REFERENCE_EVIDENCE_ONLY' and
        review['blocking_findings']==[] and review['actual_process_waited'] is True and
        type(review['actual_review_process_exit']) is int and review['actual_review_process_exit']==0,
        'Actual independent source review, not DUT entry approval')
    for path in (c.REF/'READY.json',c.REF/'PRE_REFERENCE.json',reference,receipt,
            SOFTWARE_REVIEW,SOFTWARE_REVIEW.with_suffix('.md')):pins[str(path)]=sha(path)
    common.base.verify_pins(pins)
    return ready,pins


def command_for(root,simv):
    return [str(simv),'-l','run.vcs.log','+ntb_random_seed=1','+PRELOAD='+str(root/'input.elf'),
        '+TESTCASE='+c.ID,'+NO_FSDB','+COMMIT_TRACE='+str(root/'commit_trace.csv')]


def validate(out,digest):
    require(sha(out/'plan.json')==digest,'Disk plan identity')
    plan=read(out/'plan.json')
    require((plan['unit'],plan['jobs'],plan['case_timeout_s'],plan['worker_timeout_s'],plan['outer_timeout_s'],
        plan['reserved_slots'],plan['retries'])==(UNIT,JOBS,TIMEOUT,WORKER,OUTER,0,0) and
        plan['image']==str(c.IMAGE) and len(plan['cases'])==1 and
        plan['cases'][0]['id']==c.ID and plan['cases'][0]['original_name']==c.SOURCE and
        plan['cases'][0]['sha256']==c.ELF_SHA,'Exact once-only full482 contract')
    common.base.verify_pins(plan['pins'])
    return plan


def prepare(out):
    require(not out.exists(),'Fresh preparation directory')
    host=read(HERE/'host02.json')
    require(host['status']=='PASS' and host['tests']>0 and host['errors']==host['failures']==0 and
        host['actual_child_returncode']==0 and type(host['actual_child_returncode']) is int,'Actual final Host')
    common.base.verify_pins(host['code_pins'])
    ledger,repo,_,pins=image_gate();ready,bound=source_gate();pins.update(bound)
    profile=read(HERE/'reset_profile.json');c.validate_profile(profile)
    require(profile==c.make_profile(ledger),'Actual same M8 reset profile')
    spec=c.specification()
    case=dict(id=c.ID,original_name=c.SOURCE,elf=spec['elf'],sha256=c.ELF_SHA,timeout_s=TIMEOUT,
        pass_markers=ready['programs']['soc']['pass_markers'])
    for path in list(HERE.glob('*.py'))+[HERE/'host02.json',HERE/'reset_profile.json',
            HERE/'host_final02/execution.json',HERE/'host_final02/stdout.log',HERE/'host_final02/stderr.log',
            Path(common.__file__),Path(common.base.__file__),Path(common.base.shared.__file__),
            c.G/'integration/prepare.py',
            c.LEGACY,c.GENERIC,c.transport.TRANSPORT,c.PROFILE_SOURCE,c.PROFILE_REVIEW,
            c.G.parents[1]/'ara_verify/trace.py',c.G.parents[1]/'coverage/scoped_rv64c_memory.py']:
        pins[str(path)]=sha(path)
    pins.update(profile['rtl_pins']);pins.update(profile['proof_pins'])
    common.base.verify_pins(pins)
    out.mkdir()
    plan=dict(status='PREPARED_NO_DUT',unit=UNIT,jobs=JOBS,cases=[case],case_timeout_s=TIMEOUT,
        worker_timeout_s=WORKER,outer_timeout_s=OUTER,reserved_slots=0,retries=0,
        image=str(c.IMAGE),image_sha256=sha(c.IMAGE/'image.json'),snapshot_sha256=ledger['snapshot_sha256'],
        configuration_sha256=ledger['configuration_sha256'],source_ready_sha256=c.READY_SHA,
        source_review_sha256=SOFTWARE_REVIEW_SHA,spec=spec,reset_profile=profile,pins=pins,
        budget=dict(scalar_retired_proxy=835145,samehelper_M4_max_cycles_per_call=3295,
            vector_cycles_proxy=482*3295,total_cycles_proxy=835145+482*3295,
            measured_cross_program_min_cycles_per_s=873,margin=2,
            projected_seconds=(835145+482*3295)/873*2,
            limitation='Cross-program/M4-to-M8 proxy; not measured M8 full482 duration or guarantee'),
        user_authorization='User authorizes once M8 after qualified independent final entry review',
        full22400_accepted=False,original_Linux_history_closed=False,no_build=True,first_failure_stop=True)
    save(out/'plan.json',plan)
    digest=sha(out/'plan.json')
    command=['systemd-run','--user','--unit='+UNIT,'--property=RuntimeMaxSec='+str(OUTER),
        '--property=KillMode=control-group','--property=Restart=no','--property=WorkingDirectory='+str(HERE),
        '--property=StandardOutput=append:'+str(out/'service.log'),
        '--property=StandardError=append:'+str(out/'service.log'),sys.executable,'-B',str(HERE/'replay.py'),
        'run','--out',str(out),'--plan-sha256',digest,
        '--entry-review','REPLACE_WITH_ACTUAL_HILBERT_ENTRY_JSON',
        '--entry-sha256','REPLACE_WITH_ACTUAL_HILBERT_ENTRY_SHA']
    save(out/'ready.json',dict(status='PREPARED_NO_DUT_FINAL_ENTRY_REQUIRED',plan_sha256=digest,
        service_command_template=command,service_command_shell_template=shlex.join(command)))
    print(digest,flush=True)


def entry_gate(path,digest,plan_sha):
    require(path is not None and sha(path)==digest,'Actual final independent entry report hash')
    entry=read(path)
    require(entry['status']=='APPROVED_M8_FULL482_ENTRY_NOT_DUT_PASS' and
        entry['plan_sha256']==plan_sha and entry['source_ready_sha256']==c.READY_SHA and
        entry['blocking_findings']==[] and entry['actual_process_waited'] is True and
        type(entry['actual_review_process_exit']) is int and entry['actual_review_process_exit']==0,
        'Actual final worker/Host/plan review; software-only review cannot authorize entry')
    common.base.verify_pins(entry['verified_input_pins'])
    return entry


def owner():
    runtime=Path('/run/user')/str(os.getuid())
    require(runtime.stat().st_uid==os.getuid() and (runtime/'bus').is_socket(),'Trusted user bus')
    env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(runtime/'bus'))
    query=subprocess.run(['systemctl','--user','show',UNIT,
        '--property=Id,ActiveState,SubState,MainPID,ControlGroup,RuntimeMaxUSec,KillMode,Restart'],
        env=env,text=True,capture_output=True,timeout=10)
    require(query.returncode==0 and not query.stderr.strip(),'Actual service query')
    props=dict(line.split('=',1) for line in query.stdout.splitlines())
    group=Path('/proc/self/cgroup').read_text()
    require(props['Id']==UNIT and props['ActiveState']=='active' and props['SubState']=='running' and
        props['MainPID']==str(os.getpid()) and props['ControlGroup'].endswith('/'+UNIT) and
        props['ControlGroup'] in [r.split(':',2)[-1] for r in group.splitlines()] and
        props['RuntimeMaxUSec']=='3h 40min' and props['KillMode']=='control-group' and props['Restart']=='no',
        'Direct MainPID/cgroup/exact runtime owner')
    return dict(properties=props,cgroup=group,pid=os.getpid())


def last_cycle(path):
    if not path.exists():return 0
    with path.open('rb') as stream:
        stream.seek(0,2);size=stream.tell();stream.seek(max(0,size-65536));data=stream.read()
    lines=data.splitlines()
    if not data.endswith(b'\n'):lines=lines[:-1]
    for line in reversed(lines):
        token=line.split(b',',1)[0]
        if token.isdigit():return int(token)
    return 0


def growth(a,b):
    return (a['pid'],a['generation'],a['command'])==(b['pid'],b['generation'],b['command']) and \
        a['bytes']>0 and a['ticks']>0 and a['cycle']>0 and \
        b['bytes']>a['bytes'] and b['ticks']>a['ticks'] and b['cycle']>a['cycle']


def startup(out,ledger,abort,done):
    anchor=None;deadline=time.monotonic()+60
    root=out/'replay/tests'/c.ID;target=command_for(root,ledger['simv'])
    try:
        while time.monotonic()<deadline and not done.is_set() and not abort.is_set():
            matches=[]
            for proc in Path('/proc').iterdir():
                if not proc.name.isdigit():continue
                try:
                    args=(proc/'cmdline').read_bytes().decode(errors='replace').rstrip('\0').split('\0')
                    if '+TESTCASE='+c.ID not in args:continue
                    require(args==target and (proc/'cwd').resolve()==root/'work','Startup exact private command identity')
                    fields=(proc/'stat').read_text().rsplit(')',1)[1].split()
                    trace=root/'commit_trace.csv'
                    matches.append(dict(pid=int(proc.name),generation=fields[19],command=args,
                        ticks=int(fields[11])+int(fields[12]),bytes=trace.stat().st_size if trace.exists() else 0,
                        cycle=last_cycle(trace)))
                except (FileNotFoundError,ProcessLookupError):continue
            require(len(matches)<=1,'Duplicate owned simulator')
            if matches:
                current=matches[0]
                if anchor is not None:
                    require((anchor['pid'],anchor['generation'])==(current['pid'],current['generation']),
                        'Simulator restart forbidden')
                    if growth(anchor,current):
                        save(out/'actual_simv_confirmation.json',dict(status='ADVANCING_ACTUAL_M8_SIMV',
                            before=anchor,after=current,worker_pid=os.getpid(),original_budget_s=60));return
                elif all(current[k]>0 for k in ('ticks','bytes','cycle')):anchor=current
            done.wait(0.5)
        raise ValueError('Actual CPU/cycle/trace did not confirm within original 60s')
    except BaseException as error:
        abort.set();save(out/'startup_failure.json',dict(error=repr(error),anchor=anchor))


@contextmanager
def hooks(engine,out,ledger,abort):
    old_monitor,old_fail=engine._run_monitored,engine.FAIL_RE
    def monitor(command,cwd,console,timeout,cancel_event=None):
        root=out/'replay/tests'/c.ID
        require(list(map(str,command))==command_for(root,ledger['simv']) and Path(cwd)==root/'work' and
            Path(console)==root/'console.log' and timeout==TIMEOUT and cancel_event is abort,
            'Actual monitor command/private CWD/cancel/budget')
        outcome=old_monitor(command,cwd,console,timeout,cancel_event)
        code,elapsed,timed_out,failure=outcome
        save(root/'child_outcome.unvalidated.json',dict(schema='UNVALIDATED_MONITOR_OUTCOME_V1',
            architectural_acceptance=False,runtime_id=c.ID,source_label=c.SOURCE,
            returncode=code,elapsed_s=elapsed,timed_out=timed_out,failure_seen=failure,
            command=list(map(str,command)),cwd=str(cwd),timeout_s=timeout))
        if not numeric_gate(outcome):abort.set()
        return outcome
    engine._run_monitored=monitor;engine.FAIL_RE=re.compile(old_fail.pattern+'|'+c.VETO.pattern,re.I)
    try:yield
    finally:engine._run_monitored,engine.FAIL_RE=old_monitor,old_fail


def options(cls,repo,out,ledger,dry):
    return cls(repo_root=repo,output_root=out/('dryrun' if dry else 'replay'),config='default',jobs=JOBS,
        seed=1,dry_run=dry,build_only=False,skip_build=True,simv=Path(ledger['simv']),commit_trace=True,timeout_s=TIMEOUT)


def execute(out,digest,dry=False,entry_path=None,entry_sha=None):
    plan=validate(out,digest)
    ledger,repo,(parent,opts,testcase,_),_=image_gate()
    cases=plan['cases'];abort,done=threading.Event(),threading.Event()
    import ara_verify.runner as engine
    import ara_verify.trace as protocol
    class Runner(parent):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.cancel_event=abort
        def build(self):return Path(ledger['simv'])
        def _run_test(self,test,image):
            try:
                require(not abort.is_set(),'Fail-stop before dispatch')
                if not dry:validate(out,digest);common.resources(out,JOBS,0)
                result=super()._run_test(test,image)
                if dry:return result
                save(result.artifact_dir/'runner_result.unvalidated.json',dict(asdict(result),artifact_dir=str(result.artifact_dir)))
                require(result.status=='PASS' and type(result.returncode) is int and result.returncode==0 and
                    not abort.is_set(),'Actual nonzero/timeout/abort cannot PASS')
                report=c.artifacts(result,cases[0],ledger,plan['spec'],plan['reset_profile'],protocol,abort)
                save(result.artifact_dir/'strict_full482.json',report)
                require(not abort.is_set(),'Late postcheck abort cannot PASS')
                return result
            except BaseException as error:
                abort.set();root=out/'replay/tests'/test.name
                if root.is_dir():save(root/'first_cause.json',dict(error=repr(error),
                    numeric_outcome_preserved=(root/'child_outcome.unvalidated.json').exists()))
                raise
    tests=[testcase(c.ID,'app','',Path(cases[0]['elf']),c.ID,TIMEOUT)]
    if dry:
        results=Runner(options(opts,repo,out,ledger,True),tests,sys.argv).run()
        require(len(results)==1 and results[0].status=='DRY_RUN' and results[0].returncode is None,'Only actual dryrun')
        root=out/'dryrun/tests'/c.ID
        expected=command_for(root,ledger['simv'])
        expected=[a if not a.startswith('+PRELOAD=') else '+PRELOAD='+cases[0]['elf'] for a in expected]
        require(read(root/'command.json')==dict(command=expected,cwd=str(root/'work')) and
            not (root/'commit_trace.csv').exists() and not (root/'console.log').exists(),'Dryrun command/no-DUT gate')
        validate(out,digest);save(out/'dryrun_gate.json',dict(status='DRYRUN_ONLY_NO_DUT',plan_sha256=digest,cases=[c.ID]))
        return 0
    entry_gate(entry_path,entry_sha,digest)
    require(read(out/'dryrun_gate.json')['plan_sha256']==digest and not (out/'replay').exists(),'Once-only launch after dryrun')
    save(out/'launch.json',dict(owner=owner(),resources=common.resources(out,JOBS,0),plan_sha256=digest,
        entry_review=str(entry_path),entry_sha256=entry_sha,started=time.time()))
    terminal=dict(status='NOT_ACCEPTED',plan_sha256=digest,retries=0,full22400_accepted=False,original_Linux_history_closed=False)
    thread=threading.Thread(target=startup,args=(out,ledger,abort,done),daemon=True)
    deadline=threading.Timer(WORKER,abort.set);deadline.daemon=True
    with common.abort_signals(abort),hooks(engine,out,ledger,abort):
        thread.start();deadline.start()
        try:
            results=Runner(options(opts,repo,out,ledger,False),tests,sys.argv).run()
            terminal['results']=[dict(asdict(r),artifact_dir=str(r.artifact_dir)) for r in results]
            common.check_stage(results,read(out/'replay/run.json'),cases,abort)
            require(read(out/'replay/summary.json')==terminal['results'],'Actual summary identity')
            require((out/'actual_simv_confirmation.json').exists(),'True startup confirmation')
            child=read(out/'replay/tests'/c.ID/'child_outcome.unvalidated.json')
            require(numeric_gate((child['returncode'],child['elapsed_s'],child['timed_out'],child['failure_seen'])),
                'Durable actual child tuple')
            validate(out,digest)
            require(not abort.is_set(),'Late cancellation cannot PASS')
            terminal.update(status=PASS,pins_unchanged=True,
                evidence_pins={str(p):sha(p) for p in (out/'replay').rglob('*') if p.is_file()})
        except BaseException as error:abort.set();terminal['error']=repr(error)
        finally:
            deadline.cancel();done.set();thread.join(timeout=2)
            if abort.is_set() and terminal['status']==PASS:terminal['status']='NOT_ACCEPTED_LATE_ABORT'
            terminal['finished']=time.time();save(out/'complete.json',terminal)
    print(terminal['status'],flush=True)
    return int(terminal['status']!=PASS)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','dryrun','run'))
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--plan-sha256')
    parser.add_argument('--entry-review',type=Path);parser.add_argument('--entry-sha256')
    args=parser.parse_args();out=args.out.resolve()
    require(out.parent==HERE,'Owned direct output directory')
    if args.mode=='prepare':prepare(out)
    else:
        env=common.base.shared.environment();os.environ.clear();os.environ.update(env)
        raise SystemExit(execute(out,args.plan_sha256,args.mode=='dryrun',args.entry_review,args.entry_sha256))
