#!/usr/bin/env python3
"""Two authentic VI0 first112 prefixes on immutable M7; no build or retry."""
import argparse
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import threading
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'gather_repair05'))
import regression as common
import configure

UNIT = 'ara-gather-vi0-prefix112-m7-01.service'
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate07/campaign/image')
TIMEOUT, OUTER, JOBS = 9000, 9600, 2
KINDS = ('e8_m4', 'e16_m8')
PASS = 'PASS_TWO_M7_VI0_AUTHENTIC_PREFIX112_NOT_HISTORICAL_STALLS'
require, read, sha = common.require, common.read, common.sha


def save(path, data):
    with Path(path).open('x') as stream:
        json.dump(data, stream, indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())


def numeric_gate(outcome):
    code, elapsed, timed_out, failure = outcome
    require(type(code) is int and type(timed_out) is bool and type(failure) is bool,
            'Actual monitor tuple types')
    return code == 0 and not timed_out and not failure and 0 <= elapsed <= TIMEOUT


def image_gate():
    ledger, repo, framework = common.image_context(IMAGE)
    build_path = IMAGE.parents[1] / 'BUILD_ACCEPTED.json'
    build = read(build_path)
    require(build['status'] == 'BUILD_ONLY_NOT_DUT_PASS' and
            build['snapshot_sha256'] == ledger['snapshot_sha256'] and
            build['image_sha256'] == sha(IMAGE / 'image.json'), 'Actual M7 built identity')
    manifest = read(Path(ledger['snapshot']) / 'snapshot.json')['files']
    require(all(manifest[p] == h for p, h in build['approved_source_sha256'].items()), 'Approved M7 patch identity')
    old_snapshot = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen')
    old_files = read(old_snapshot / 'snapshot.json')['files']
    changed = {p for p in set(old_files) | set(manifest) if old_files.get(p) != manifest.get(p)}
    require(changed == set(build['approved_source_sha256']) | {'hardware/bender','frozen.filelist'},
            'Only approved RTL and relocation metadata may differ from M6')
    for relative in ('hardware/bender','frozen.filelist'):
        old_text = (old_snapshot / 'sources' / relative).read_text()
        new_text = (Path(ledger['snapshot']) / 'sources' / relative).read_text()
        require(old_text.replace(str(old_snapshot), str(ledger['snapshot'])) == new_text,
                'M6-to-M7 relocation must not change source semantics')
    pins = common.image_pins(IMAGE, ledger, repo)
    pins[str(build_path)] = sha(build_path)
    return ledger, repo, framework, pins


def reference_gate(kind):
    path = configure.PREPARATION / kind / 'READY.json'
    ready = read(path)
    require(ready['status'] == 'ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT' and
            type(ready['actual_reference_returncode']) is int and ready['actual_reference_returncode'] == 0 and
            (ready['calls'], ready['predecessors'], ready['capacity'], ready['vlenb'], ready['results'],
             ready['guards'], ready['helpers'], ready['setup_values_per_call'], ready['physical_predicate_bytes']) ==
            (112,111,512,128,57344,224,1456,2178,128) and ready['endpoint'] == [0,2,0,6,3,3] and
            ready['historical_stall_closed'] is False, 'Exact source/reference scope')
    common.base.verify_pins(ready['pins'])
    ref = Path(ready.get('original_artifact_root', str(path.parent)))
    proof = read(ref / 'original_binary_proof.json')
    require(proof['status'] == 'PASS_FULL_ORIGINAL_LINUX_ELF_BYTE_IDENTICAL' and
            type(proof['execution']['returncode']) is int and proof['execution']['returncode'] == 0 and
            sha(ref / 'original_binary_proof.json') == ready['original_binary_proof_sha256'], 'Original full Linux ELF proof')
    reference_path = path.parent / 'reference.json' if kind == 'e8_m4' else ref / 'reference/reference.json'
    require(sha(reference_path) == ready['reference_sha256'], 'Reference report binding')
    reference = read(reference_path)
    require(reference['target_hits'] == 112 and reference['routine_retire_counts'] == [112]*13 and
            reference['fullcap_scalar_checks'] == 57344 and reference['both_guard_checks'] == 224 and
            reference['returned_vstart_zero'] == 112 and reference['htif_store_value'] == 1 and
            reference['actual_source0'] == (185 if ready['sew'] == 8 else 61881), 'Full reference oracle')
    host_path = ref / 'host/host.json'
    host = read(host_path)
    require(sha(host_path) == ready['host_sha256'] and host['status'] == 'PASS_ORIGINAL_C_ONE_POSITIVE_SEVEN_ORACLE_MUTATIONS' and
            [t['mutation'] for t in host['tests']] == ['none','prestart','active','inactive','tail','guard0','guard1','vstart'] and
            [t['actual_returncode'] for t in host['tests']] == [0,1,1,1,1,1,1,1], 'Host mutation binding')
    pins = dict(ready['pins'])
    pins.update({str(path):sha(path), str(reference_path):sha(reference_path)})
    return ready, pins


def validate(out, digest):
    require(sha(out / 'plan.json') == digest, 'Disk plan hash')
    plan = read(out / 'plan.json')
    require(plan['unit'] == UNIT and plan['jobs'] == JOBS and plan['case_timeout_s'] == TIMEOUT and
            plan['outer_timeout_s'] == OUTER and plan['reserved_slots'] == 0 and
            plan['historical_stall_closed'] is False and len(plan['cases']) == 2, 'Exact launch scope')
    common.base.verify_pins(plan['pins'])
    return plan


def prepare(out):
    require(not out.exists(), 'Fresh output; no overwrite')
    host = read(HERE/'host02.json')
    require(host['status']=='PASS' and host['tests']==4 and host['errors']==host['failures']==0,
            'Actual host gate')
    common.base.verify_pins(host['code_pins'])
    ledger, repo, _, pins = image_gate()
    cases = []
    for kind in KINDS:
        ready, bound = reference_gate(kind)
        pins.update(bound)
        configure.generate(kind)
        checker = configure.load(kind)
        model = checker.model()
        require(model['rows'][-1]['tuple'] == [0,2,0,6,3,3], 'Full original natural sequence')
        case = dict(kind=kind, id=ready['runtime_id'], original_name=ready['source_label'],
                    elf=ready['soc_elf']['path'], sha256=ready['soc_elf']['sha256'], timeout_s=TIMEOUT,
                    pass_markers=['BOARD_CASE_PASS '+ready['runtime_id'], 'BOARD_REPLAY_PASS',
                        f'RVV_GATHER_PREFIX_PASS sew={ready["sew"]} cases=112 errors=0'],
                    spec=checker.specification(Path(ready['soc_elf']['path'])),
                    reference_ready_sha256=sha(configure.PREPARATION / kind / 'READY.json'),
                    actual_reference_retired=ready['actual_firmware_retired'],
                    estimated_DUT_s_at_conservative_600_retired_per_s=ready['actual_firmware_retired']/600)
        cases.append(case)
    pins.update({str(p):sha(p) for p in HERE.rglob('*.py')})
    pins[str(HERE/'host02.json')] = sha(HERE/'host02.json')
    pins[str(configure.TEMPLATE)] = sha(configure.TEMPLATE)
    out.mkdir()
    plan = dict(status='PREPARED_REFERENCE_ONLY_NO_DUT', unit=UNIT, jobs=JOBS, cases=cases,
                case_timeout_s=TIMEOUT, outer_timeout_s=OUTER, reserved_slots=0,
                image=str(IMAGE), snapshot_sha256=ledger['snapshot_sha256'],
                pins=pins, reference_audit='Own strict raw reference; no invented independent attestation',
                user_authorization='Latest direct user request authorizes M7 numerical regression after reference PASS',
                historical_stall_closed=False, full2688_accepted=False, Linux_execution=False, retries=0)
    save(out / 'plan.json', plan)
    digest = sha(out / 'plan.json')
    command = ['systemd-run','--user','--unit='+UNIT,'--property=RuntimeMaxSec='+str(OUTER),
               '--property=KillMode=control-group','--property=Restart=no','--property=WorkingDirectory='+str(HERE),
               '--property=StandardOutput=append:'+str(out/'service.log'),
               '--property=StandardError=append:'+str(out/'service.log'),
               sys.executable,'-B',str(HERE/'replay.py'),'run','--out',str(out),'--plan-sha256',digest]
    save(out/'ready.json', dict(status='PREPARED_NO_DUT', plan_sha256=digest, service_command=command,
         service_command_shell=shlex.join(command), first_failure_stop=True))
    print(digest, flush=True)


def options(cls, repo, out, ledger, dry=False):
    return cls(repo_root=repo, output_root=out / ('dryrun' if dry else 'replay'), config='default',
               jobs=JOBS,seed=1,dry_run=dry,build_only=False,skip_build=True,
               simv=Path(ledger['simv']),commit_trace=True,timeout_s=TIMEOUT)


def owner():
    runtime = Path('/run/user') / str(os.getuid())
    require(runtime.stat().st_uid == os.getuid() and (runtime/'bus').is_socket(), 'Trusted bus')
    env = dict(os.environ,XDG_RUNTIME_DIR=str(runtime),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(runtime/'bus'))
    q = subprocess.run(['systemctl','--user','show',UNIT,'--property=Id,ActiveState,SubState,MainPID,ControlGroup,RuntimeMaxUSec,KillMode,Restart'],
                       env=env,text=True,capture_output=True,timeout=10)
    require(q.returncode == 0 and not q.stderr.strip(), 'Owner query')
    props = dict(line.split('=',1) for line in q.stdout.splitlines())
    group = Path('/proc/self/cgroup').read_text()
    require(props['Id']==UNIT and props['ActiveState']=='active' and props['SubState']=='running' and
            props['MainPID']==str(os.getpid()) and props['ControlGroup'].endswith('/'+UNIT) and
            props['ControlGroup'] in [r.split(':',2)[-1] for r in group.splitlines()] and
            props['RuntimeMaxUSec']=='2h 40min' and props['KillMode']=='control-group' and props['Restart']=='no',
            'Direct service ownership/budget')
    return dict(properties=props,cgroup=group,pid=os.getpid())


def command_for(root, name, simv):
    return [str(simv),'-l','run.vcs.log','+ntb_random_seed=1','+PRELOAD='+str(root/'input.elf'),
            '+TESTCASE='+name,'+NO_FSDB','+COMMIT_TRACE='+str(root/'commit_trace.csv')]


def growth(a, b):
    return (a['pid'],a['generation'],a['command']) == (b['pid'],b['generation'],b['command']) and \
        a['bytes'] > 0 and a['ticks'] > 0 and b['bytes'] > a['bytes'] and b['ticks'] > a['ticks']


def startup(out, cases, ledger, abort, done):
    anchors, accepted = {}, {}
    deadline = time.monotonic()+60
    try:
        while time.monotonic() < deadline and not done.is_set() and not abort.is_set():
            for case in cases:
                name = case['id']
                if name in accepted:
                    continue
                root = out/'replay/tests'/name
                target = command_for(root,name,ledger['simv'])
                matches = []
                for proc in Path('/proc').iterdir():
                    if not proc.name.isdigit():
                        continue
                    try:
                        args = (proc/'cmdline').read_bytes().decode().rstrip('\0').split('\0')
                        if '+TESTCASE='+name not in args:
                            continue
                        require(args == target, 'Startup exact argv identity mismatch')
                        require((proc/'cwd').resolve() == root/'work', 'Startup private CWD mismatch')
                        fields = (proc/'stat').read_text().rsplit(')',1)[1].split()
                        matches.append(dict(pid=int(proc.name),generation=fields[19],
                            ticks=int(fields[11])+int(fields[12]),command=args,
                            bytes=(root/'commit_trace.csv').stat().st_size if (root/'commit_trace.csv').exists() else 0))
                    except (FileNotFoundError,ProcessLookupError):
                        continue
                require(len(matches)<=1, 'Duplicate owned simulator')
                if not matches:
                    continue
                b = matches[0]
                if name not in anchors:
                    if b['bytes']>0 and b['ticks']>0:
                        anchors[name]=b
                    continue
                a=anchors[name]
                require((a['pid'],a['generation'])==(b['pid'],b['generation']), 'Simulator restart forbidden')
                if growth(a,b):
                    accepted[name]=dict(before=a,after=b)
            if len(accepted)==2:
                save(out/'actual_simv_confirmation.json',dict(status='ADVANCING_TWO_ACTUAL_M7_SIMV',
                    samples=accepted,worker_pid=os.getpid(),timeout_s=60))
                return
            done.wait(0.5)
        raise ValueError('Both actual simulators did not confirm progress within original 60s')
    except BaseException as error:
        abort.set()
        save(out/'startup_failure.json',dict(error=repr(error),anchors=anchors,accepted=accepted))


@contextmanager
def hooks(engine, out, cases, ledger, abort, checkers):
    old_monitor, old_fail = engine._run_monitored, engine.FAIL_RE
    def monitor(command,cwd,console,timeout,cancel_event=None):
        names=[a.split('=',1)[1] for a in command if str(a).startswith('+TESTCASE=')]
        require(len(names)==1, 'Actual TESTCASE identity')
        name=names[0];case=next(c for c in cases if c['id']==name)
        root=out/'replay/tests'/name
        require(list(map(str,command))==command_for(root,name,ledger['simv']) and
                Path(cwd)==root/'work' and Path(console)==root/'console.log' and
                timeout==TIMEOUT and cancel_event is abort, 'Actual monitor private command/cancel/budget')
        outcome=old_monitor(command,cwd,console,timeout,cancel_event)
        code,elapsed,timed_out,failure=outcome
        save(root/'child_outcome.unvalidated.json',dict(schema='UNVALIDATED_MONITOR_OUTCOME_V1',
            architectural_acceptance=False,name=name,source_label=case['original_name'],
            returncode=code,elapsed_s=elapsed,timed_out=timed_out,failure_seen=failure,
            command=list(map(str,command)),cwd=str(cwd),timeout_s=timeout))
        if not numeric_gate(outcome):
            abort.set()
        return outcome
    engine._run_monitored=monitor
    engine.FAIL_RE=re.compile(old_fail.pattern+'|'+checkers[KINDS[0]].VETO.pattern,re.I)
    try:
        yield
    finally:
        engine._run_monitored,engine.FAIL_RE=old_monitor,old_fail


def execute(out,digest,dry=False):
    plan=validate(out,digest)
    ledger,repo,(parent,opts,testcase,_),_=image_gate()
    cases=plan['cases']
    checkers={k:configure.load(k) for k in KINDS}
    abort,done=threading.Event(),threading.Event()
    import ara_verify.runner as engine
    from ara_verify.trace import validate_trace
    class Runner(parent):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw);self.cancel_event=abort
        def build(self):
            return Path(ledger['simv'])
        def _run_test(self,test,image):
            try:
                require(not abort.is_set(),'Fail-stop before dispatch')
                if not dry:
                    validate(out,digest);common.resources(out,JOBS,0)
                result=super()._run_test(test,image)
                if dry:
                    return result
                save(result.artifact_dir/'runner_result.unvalidated.json',dict(asdict(result),artifact_dir=str(result.artifact_dir)))
                require(result.status=='PASS' and type(result.returncode) is int and result.returncode==0 and
                        not abort.is_set(),'Nonzero/aborted result cannot PASS')
                case=next(c for c in cases if c['id']==test.name)
                report=checkers[case['kind']].artifacts(result,case,ledger,case['spec'],validate_trace)
                save(result.artifact_dir/'strict_prefix.json',report)
                require(not abort.is_set(),'Late abort cannot PASS')
                return result
            except BaseException as error:
                abort.set()
                root=out/'replay/tests'/test.name
                if root.is_dir():
                    save(root/'first_cause.json',dict(error=repr(error),numeric_outcome_preserved=(root/'child_outcome.unvalidated.json').exists()))
                raise
    tests=[testcase(c['id'],'app','',Path(c['elf']),c['id'],TIMEOUT) for c in cases]
    if dry:
        results=Runner(options(opts,repo,out,ledger,True),tests,sys.argv).run()
        require(len(results)==2 and all(r.status=='DRY_RUN' and r.returncode is None for r in results),'Dryrun only')
        for case in cases:
            root=out/'dryrun/tests'/case['id']
            require(read(root/'command.json')==dict(command=command_for(root,case['id'],ledger['simv']),cwd=str(root/'work')),
                    'Dryrun private command identity')
            require(not (root/'commit_trace.csv').exists() and not (root/'console.log').exists(),'Dryrun executed DUT')
        validate(out,digest)
        save(out/'dryrun_gate.json',dict(status='DRYRUN_ONLY_NO_DUT',plan_sha256=digest,cases=[c['id'] for c in cases]))
        return 0
    require(read(out/'dryrun_gate.json')['plan_sha256']==digest and not (out/'replay').exists(),'Fresh once-only dryrun-bound launch')
    save(out/'launch.json',dict(owner=owner(),resources=common.resources(out,JOBS,0),plan_sha256=digest,started=time.time()))
    terminal=dict(status='NOT_ACCEPTED',plan_sha256=digest,historical_stall_closed=False,retries=0)
    thread=threading.Thread(target=startup,args=(out,cases,ledger,abort,done),daemon=True)
    with common.abort_signals(abort),hooks(engine,out,cases,ledger,abort,checkers):
        thread.start()
        try:
            results=Runner(options(opts,repo,out,ledger),tests,sys.argv).run()
            terminal['results']=[dict(asdict(r),artifact_dir=str(r.artifact_dir)) for r in results]
            common.check_stage(results,read(out/'replay/run.json'),cases,abort)
            require(read(out/'replay/summary.json')==terminal['results'],'Summary identity')
            require((out/'actual_simv_confirmation.json').exists(),'True actual startup gate')
            for case in cases:
                root=out/'replay/tests'/case['id'];child=read(root/'child_outcome.unvalidated.json')
                require(numeric_gate((child['returncode'],child['elapsed_s'],child['timed_out'],child['failure_seen'])),
                        'Durable actual child tuple')
            validate(out,digest)
            terminal.update(status=PASS,pins_unchanged=True,full2688_accepted=False,Linux_execution=False,
                evidence_pins={str(p):sha(p) for p in (out/'replay').rglob('*') if p.is_file()})
        except BaseException as error:
            abort.set();terminal['error']=repr(error)
        finally:
            done.set();thread.join(timeout=2)
            terminal['finished']=time.time();save(out/'complete.json',terminal)
    print(terminal['status'],flush=True)
    return int(terminal['status']!=PASS)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','dryrun','run'))
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--plan-sha256')
    args=parser.parse_args();out=args.out.resolve()
    require(out.parent==HERE,'Owned direct output only')
    if args.mode=='prepare':
        prepare(out)
    else:
        env=common.base.shared.environment();os.environ.clear();os.environ.update(env)
        raise SystemExit(execute(out,args.plan_sha256,args.mode=='dryrun'))
