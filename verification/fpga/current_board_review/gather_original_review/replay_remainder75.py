#!/usr/bin/env python3
"""Prepare/dry-run once; reviewed fixed 75-case service, never build RTL or retry."""
import argparse
import errno
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
import replay_successor04 as sealed
import check_remainder75 as checker
from prepare_batch import HERE, ROOT, INTEGRATION, sha, save
from replay_candidate03 import read, require, pins_check, oracle, FAIL

DATA = checker.DATA
OUT = DATA / 'vcs_candidate04_01'
IMAGE, IMAGE_SHA = sealed.IMAGE, sealed.IMAGE_SHA
UNIT = 'ara-gather75-candidate04-01.service'
integration = sealed.integration
QUOTAS = {'whole1134':(6,'/whole_register_original/'), 'NF8':(8,'/nf8_strided_review/'),
          'NF7':(2,'/indexed_review/'), 'DUT38':(4,'/candidate04_regression38_03/')}


def resource_gate(live, available, tesla=False):
    external = [p for p in live if not any(str(OUT)+'/' in a for a in p['argv'])]
    observed = {name:0 for name in QUOTAS}
    unknown = []
    for p in external:
        groups = [name for name,(_,token) in QUOTAS.items() if any(token in a for a in p['argv'])]
        if len(groups) == 1:
            observed[groups[0]] += 1
        else:
            unknown.append(p)
    reservations = {name:dict(slots=slots, observed_live=observed[name],
                    charged=max(slots,observed[name])) for name,(slots,_) in QUOTAS.items()}
    own_live = len(live)-len(external)
    total = sum(r['charged'] for r in reservations.values())+len(unknown)+max(4,own_live)
    return dict(time=time.time(), live=live, reservations=reservations, unknown_external=unknown,
        own_live=own_live, own_slots=4, total_live_reserved=total, cap=24,
        available_bytes=available, min_available_bytes=32*1024**3, tesla_conflict=tesla,
        passed=total <= 24 and own_live <= 4 and available >= 32*1024**3 and not tesla)


def scan_processes(processes):
    live, tesla, unreadable = [], False, []
    for proc in processes:
        try:
            args = [s.decode(errors='replace') for s in (proc / 'cmdline').read_bytes().split(b'\0') if s]
            if not args:
                if (proc / 'comm').read_text().strip() == 'simv':
                    unreadable.append(dict(pid=int(proc.name),reason='simv has no readable argv'))
                continue
            if Path(args[0]).name == 'simv':
                live.append(dict(pid=int(proc.name), argv=args))
            if Path(args[0]).name.startswith('python') and any('/comparison_alias_original/' in a and
                    a.endswith('replay_candidate04.py') for a in args[1:]):
                tesla = True
        except OSError as error:
            if error.errno in (errno.ENOENT,errno.ESRCH):
                continue
            try:
                name = (proc / 'comm').read_text().strip()
            except OSError as comm_error:
                if comm_error.errno in (errno.ENOENT,errno.ESRCH):
                    continue
                name = 'UNKNOWN'
            if name == 'simv' or name.startswith('python') or name == 'UNKNOWN':
                unreadable.append(dict(pid=int(proc.name),comm=name,reason=repr(error)))
    return live,tesla,unreadable


def resources():
    live,tesla,unreadable = scan_processes(Path('/proc').glob('[0-9]*'))
    mem = dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    gate = resource_gate(live,int(mem['MemAvailable'].split()[0])*1024,tesla)
    gate['unreadable_potential_workers'] = unreadable
    gate['passed'] = gate['passed'] and not unreadable
    return gate


def prepare_plan():
    destination = DATA / 'plan.json'
    require(not destination.exists(), 'Plan already sealed; do not overwrite')
    ready = read(DATA / 'prepared_ready.json')
    require(ready['status'] == 'PREPARED_75_HOST_SPIKE_PASS_NOT_DUT' and not ready['vcs_started'], '75 not prepared')
    require(ready['baseline_pins_sha256'] == sha(DATA / 'baseline_pins.json') and
            ready['reference_sha256'] == sha(DATA / 'reference75/reference.json'), 'Prepared ready anchors drift')
    tested = read(DATA / 'preseal_host.json')
    require(tested['status'] == 'PASS' and tested['worker_sha256'] == sha(Path(__file__)) and
            tested['checker_sha256'] == sha(HERE / 'check_remainder75.py') and
            tested['test_sha256'] == sha(HERE / 'test_remainder75.py'), 'Preseal regression stale/not PASS')
    pins = dict(read(DATA / 'baseline_pins.json'))
    pins_check(pins)
    require(sha(IMAGE / 'image.json') == IMAGE_SHA, 'Wrong candidate04 image ledger')
    image = read(IMAGE / 'image.json')
    snapshot = Path(image['snapshot'])
    require(sha(snapshot / 'snapshot.json') == image['snapshot_sha256'], 'Snapshot identity drift')
    repo = integration.sealed(snapshot)
    _,_,_,image_files = integration.framework(repo)
    require(image_files(Path(image['simv'])) == image['files'], 'Image content drift')
    provenance = integration.check(DATA / 'prepared75')
    programs = read(DATA / 'soc75/programs.json')
    require(programs['backend'] == 'vcs-soc' and programs['provenance_sha256'] == sha(DATA / 'prepared75/provenance.json'), 'Wrong SoC programs/provenance')
    cases = provenance['cases']
    names = [c['id'] for c in cases]
    reference = read(DATA / 'reference75/reference.json')
    require(reference['status'] == 'SPIKE_75_FULLORACLE_PASS_NOT_DUT' and
            [r['name'] for r in reference['results']] == names and
            all(r['status'] == 'PASS' and r['returncode'] == 0 and r['full_oracle_markers'] and
                r['spike_target_hits'] == 1 for r in reference['results']), 'Missing full Spike75 reference')
    pins.update(image['files'])
    pins.update({str(repo / n):h for n,h in read(snapshot / 'snapshot.json')['files'].items()})
    for path in DATA.rglob('*'):
        if path.is_file():
            pins[str(path)] = sha(path)
    for file in (Path(__file__), HERE / 'check_remainder75.py', HERE / 'test_remainder75.py',
                 HERE / 'prepare_remainder75.py', HERE / 'check_terminal.py', HERE / 'replay_successor04.py',
                 HERE / 'check_successor.py', HERE / 'replay_candidate03.py', INTEGRATION / 'run.py',
                 INTEGRATION / 'prepare.py', IMAGE / 'image.json', snapshot / 'snapshot.json',
                 Path(image['simv']).parent / 'simulator.conf', Path(image['simv']).parent / 'vcs_source_manifest.json'):
        pins[str(file)] = sha(file)
    pins.update({p['path']:p['sha256'] for p in programs['programs'].values()})
    accepted = read(HERE / 'acceptance_audit01/audit.json')
    plan = dict(names=names, remaining_source_names=[c['original_case']['name'] for c in cases],
        remaining_source_keys=[[c['original_case']['sew'], c['original_case']['lmul'], c['original_case']['selected_trial']['op']] for c in cases],
        accepted_source_names=[r['original_case']['name'] for r in accepted['results']],
        image=str(IMAGE), image_sha256=IMAGE_SHA, programs=str(DATA / 'soc75'), pins=pins,
        jobs=4, timeout_per_case_s=300, retries=0, stop_first_failure=True, skip_accepted_execution=True,
        parent_closure=False, original_linux_elf_replay=False, unit=UNIT,
        stages=[dict(name='first12',cases=names[:12],jobs=4), dict(name='remaining63',cases=names[12:],jobs=4)],
        service_runtime_max_s=6300, requires_parent_review=True,
        scope='Accepted8 independent plus remaining75 exact numerical-source singles; not full parents/Linux/11 stalls')
    checker.validate_plan(plan)
    pins_check(pins)
    save(destination, plan)
    print('PLAN_PREPARED_NOT_LAUNCHED',sha(destination),destination,flush=True)


def checked_plan():
    plan = read(DATA / 'plan.json')
    checker.validate_plan(plan)
    require(plan['unit'] == UNIT and plan['image'] == str(IMAGE) and plan['image_sha256'] == IMAGE_SHA and
            plan['programs'] == str(DATA / 'soc75'), 'Execution identity drift')
    pins_check(plan['pins'])
    return plan, sha(DATA / 'plan.json')


def dry_run():
    plan, digest = checked_plan()
    folder = DATA / 'dryrun75'
    require(not folder.exists(), 'Fresh dry-run only; no overwrite')
    rc = integration.run_programs(SimpleNamespace(image=IMAGE,programs=Path(plan['programs']),
        out=folder,case=plan['names'],jobs=4,timeout=300,execute=False))
    summary, run = read(folder / 'summary.json'), read(folder / 'run.json')
    require(rc == 0 and [r['name'] for r in summary] == plan['names'] and
            all(r['status'] == 'DRY_RUN' for r in summary) and run['status_counts'] == {'DRY_RUN':75},
            'Dry-run membership/status differs')
    pins_check(plan['pins'])
    save(DATA / 'dryrun_gate.json',dict(status='PASS_75_DRY_RUN_NOT_DUT',plan_sha256=digest,
        cases=75,jobs=4,timeout_per_case_s=300,no_dut_launched=True))
    print('PASS_75_DRY_RUN_NOT_DUT',digest,flush=True)


def launch(review_hash):
    require(not OUT.exists(), 'Fresh independent output only; no retry')
    plan,digest = checked_plan()
    require(sha(DATA / 'review_ready.json') == review_hash, 'Parent review must bind exact ready SHA')
    ready = read(DATA / 'review_ready.json')
    require(ready['status'] == 'READY_75_STRICT_PLAN_HOST_DRYRUN_NOT_DUT' and ready['plan_sha256'] == digest and
            ready['host_gate_sha256'] == sha(DATA / 'host_gate.json') and
            ready['dryrun_gate_sha256'] == sha(DATA / 'dryrun_gate.json'), 'Ready evidence drift')
    host = read(DATA / 'host_gate.json')
    require(host['status'] == 'PASS' and host['plan_sha256'] == digest and
            host['worker_sha256'] == sha(Path(__file__)) and host['checker_sha256'] == sha(HERE / 'check_remainder75.py') and
            host['test_sha256'] == sha(HERE / 'test_remainder75.py'), 'Host gates stale/not PASS')
    dry = read(DATA / 'dryrun_gate.json')
    require(dry['status'] == 'PASS_75_DRY_RUN_NOT_DUT' and dry['plan_sha256'] == digest and
            dry['cases'] == 75 and dry['jobs'] == 4 and dry['timeout_per_case_s'] == 300 and
            dry['no_dut_launched'], 'Dry-run plan/status differs')
    require('LoadState=not-found' in subprocess.check_output(['systemctl','--user','show',UNIT,'-p','LoadState'],text=True), 'Unit collision')
    gate = resources()
    require(gate['passed'], 'Actual resources/Tesla admission blocked; no launch')
    OUT.mkdir()
    shutil.copyfile(DATA / 'plan.json',OUT / 'plan.json')
    save(OUT / 'resource_gate.json',gate)
    save(OUT / 'parent_review.json',dict(review_ready_sha256=review_hash,plan_sha256=digest))
    service = ['systemd-run','--user','--unit='+UNIT,'--collect','--property=RuntimeMaxSec=6300',
        '--property=TimeoutStopSec=120','--property=KillMode=control-group','--property=Restart=no',
        '--property=WorkingDirectory='+str(ROOT),'--property=StandardOutput=append:'+str(OUT / 'service.log'),
        '--property=StandardError=append:'+str(OUT / 'service.log'),sys.executable,'-B',str(Path(__file__).resolve()),'--worker',digest]
    save(OUT / 'service_command.json',service)
    result = subprocess.run(service,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30)
    save(OUT / 'launch.json',dict(returncode=result.returncode,output=result.stdout,plan_sha256=digest,time=time.time()))
    print(result.stdout,'OUT='+str(OUT),'UNIT='+UNIT,flush=True)
    return result.returncode


def sample(pid,args):
    proc = Path('/proc') / str(pid)
    before = (proc / 'stat').read_text().rsplit(')',1)[1].split()
    result = sealed.sample(pid,args)
    result['argv'] = [s.decode() for s in (proc / 'cmdline').read_bytes().split(b'\0') if s]
    result['executable'] = os.readlink(proc / 'exe')
    after = (proc / 'stat').read_text().rsplit(')',1)[1].split()
    if before[19] != after[19]:
        raise ProcessLookupError(errno.ESRCH,'PID generation changed during sampling')
    result['start_ticks'] = int(after[19])
    return result


def confirm_startup(stage, done, cancel=None):
    samples, discovery, record = [], [], None
    cgroup = Path('/proc/self/cgroup').read_text()
    simv = read(IMAGE / 'image.json')['simv']
    prefix = str(OUT / stage['name'])+'/'
    deadline = time.monotonic()+60
    plan,worker = read(OUT / 'plan.json'),read(OUT / 'worker.json')
    def observed(before,after):
        return dict(status='ADVANCING_4_SIMV',samples=[before,after],raw_samples_retained=True,
            discovery=discovery,worker_cgroup=cgroup,completion_polling=False,startup_bound_s=60)
    try:
        while time.monotonic() < deadline and not done.is_set():
            processes = []
            for proc in Path('/proc').glob('[0-9]*'):
                try:
                    args = [s.decode() for s in (proc / 'cmdline').read_bytes().split(b'\0') if s]
                    if args and args[0] == simv and any(prefix in s for s in args):
                        processes.append((int(proc.name),args))
                except (OSError,UnicodeError):
                    continue
            if len(processes) == 4:
                try:
                    before = [sample(pid,args) for pid,args in sorted(processes)]
                    discovery.append(before)
                    checker.verify_identity(OUT,plan,stage,observed(before,before),worker)
                    if all(s['last_cycle'] > 0 and s['trace_bytes'] > 0 for s in before):
                        samples = [before,before]
                        while time.monotonic() < deadline and not done.is_set():
                            time.sleep(min(0.5,max(0,deadline-time.monotonic())))
                            after = [sample(pid,args) for pid,args in sorted(processes)]
                            samples = [before,after]
                            discovery.append(after)
                            if any(a['start_ticks'] != b['start_ticks'] for a,b in zip(before,after)):
                                raise ProcessLookupError(errno.ESRCH,'Observed worker PID generation change')
                            record = observed(before,after)
                            checker.verify_identity(OUT,plan,stage,record,worker)
                            if all(b['cpu_ticks'] > a['cpu_ticks'] and b['trace_bytes'] > a['trace_bytes'] and
                                   b['last_cycle'] > a['last_cycle'] for a,b in zip(before,after)):
                                checker.verify_progress(OUT,plan,stage,record,worker)
                                break
                        else:
                            raise ValueError('No raw growth before startup budget/terminal boundary')
                        break
                except OSError as error:
                    if error.errno not in (errno.ENOENT,errno.ESRCH):
                        raise ValueError('Unreadable own simv sample: '+repr(error)) from error
                    discovery.append(dict(process_race=str(error)))
            time.sleep(0.5)
        else:
            raise ValueError('Four real advancing simv not observed in bounded startup window')
    except Exception as error:
        record = dict(status='NOT_CONFIRMED',reason=str(error),samples=samples,raw_samples_retained=True,
            discovery=discovery,worker_cgroup=cgroup,completion_polling=False,startup_bound_s=60)
    save(OUT / stage['name'] / 'actual_simv_confirmation.json',record)
    if record['status'] != 'ADVANCING_4_SIMV' and cancel is not None:
        cancel()


def run_stages(plan, runner, gate):
    for stage in plan['stages']:
        rc = runner(stage)
        if rc:
            return rc
        gate(stage)
    return 0


def worker(digest):
    require(not (OUT / 'worker.json').exists(), 'Worker already attempted; no retry')
    plan, expected = checked_plan()
    require(digest == expected == sha(OUT / 'plan.json'), 'Worker plan drift')
    review = read(OUT / 'parent_review.json')
    require(review['plan_sha256'] == digest and
            review['review_ready_sha256'] == sha(DATA / 'review_ready.json') and
            UNIT in Path('/proc/self/cgroup').read_text(), 'Worker lacks reviewed service/cgroup authorization')
    save(OUT / 'worker.json',dict(pid=os.getpid(),cgroup=Path('/proc/self/cgroup').read_text(),
        started=time.time(),plan_sha256=digest))
    (OUT / 'admission').mkdir()
    programs = read(DATA / 'soc75/programs.json')['programs']
    cases = {c['id']:c for c in read(DATA / 'prepared75/provenance.json')['cases']}
    host = {c['name']:c for c in read(DATA / 'host_semantics.json')['results']}
    refs = {c['name']:c for c in read(DATA / 'reference75/reference.json')['results']}
    image = read(IMAGE / 'image.json')
    framework = integration.framework
    lock = threading.Lock()
    active_runner = []
    def admitted(repo):
        base,options,test,image_files = framework(repo)
        from ara_verify.trace import validate_trace
        class Runner(base):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs)
                active_runner[:] = [self]

            def _run_test(self,test,simv):
                try:
                    require(test.name in plan['names'], 'Refuse accepted8/unknown execution')
                    if not self.cancel_event.is_set():
                        with lock:
                            gate = resources()
                            save(OUT / 'admission' / (test.name+'.json'),gate)
                            require(gate['passed'],'Per-case resource gate blocked')
                    result = super()._run_test(test,simv)
                    if result.status == 'PASS':
                        raw = dict(name=result.name,status=result.status,returncode=result.returncode,
                            reason=result.reason,elapsed_s=result.elapsed_s,artifact_dir=str(result.artifact_dir))
                        try:
                            checked = checker.check_case(raw,result.artifact_dir,programs[test.name],image,
                                cases[test.name],host[test.name],refs[test.name],validate_trace)
                            save(result.artifact_dir / 'independent_case_gate.json',checked)
                        except Exception as error:
                            result.status,result.reason = 'FAIL','Independent raw gate: '+repr(error)
                    if result.status != 'PASS':
                        self.cancel_event.set()
                    return result
                except Exception:
                    self.cancel_event.set()
                    raise
        return Runner,options,test,image_files
    integration.framework = admitted
    integration.oracle_complete = oracle
    integration.framework(Path(image['snapshot']) / 'sources')
    import ara_verify.runner as engine
    engine.FAIL_RE = re.compile(engine.FAIL_RE.pattern+'|'+FAIL.pattern,re.I|re.M)
    env = integration.environment()
    os.environ.clear()
    os.environ.update(env)
    def runner(stage):
        pins_check(plan['pins'])
        folder = OUT / stage['name']
        folder.mkdir()
        command = [sys.executable,'-B',str(INTEGRATION / 'run.py'),'run','--image',str(IMAGE),
            '--programs',plan['programs'],'--out',str(folder / 'replay'),'--jobs','4','--timeout','300','--execute']
        for name in stage['cases']:
            command += ['--case',name]
        save(folder / 'runner_command.json',command)
        done = threading.Event()
        def cancel_stage():
            for current in active_runner:
                if current.output_root == folder / 'replay':
                    current.cancel_event.set()
        observer = threading.Thread(target=confirm_startup,args=(stage,done,cancel_stage))
        observer.start()
        rc,error = 1,None
        try:
            with (folder / 'runner.log').open('x') as stream:
                stdout,stderr = sys.stdout,sys.stderr
                sys.stdout = sys.stderr = stream
                try:
                    rc = integration.run_programs(SimpleNamespace(image=IMAGE,programs=Path(plan['programs']),
                        out=folder / 'replay',case=stage['cases'],jobs=4,timeout=300,execute=True))
                finally:
                    sys.stdout,sys.stderr = stdout,stderr
        except Exception as caught:
            error = repr(caught)
        finally:
            done.set()
            observer.join()
        save(folder / 'runner_exit.json',dict(returncode=rc,error=error,plan_sha256=digest,finished=time.time()))
        return rc or int(error is not None)
    def gate(stage):
        results = checker.validate_stage(OUT,digest,stage['name'])
        save(OUT / stage['name'] / 'independent_gate.json',dict(status='PASS_'+stage['name'].upper(),
            results=results,plan_sha256=digest,finished=time.time()))
        print(stage['name'],'PASS_FULLORACLE',len(results),flush=True)
    rc,error = 1,None
    try:
        rc = run_stages(plan,runner,gate)
    except Exception as caught:
        error = repr(caught)
    save(OUT / 'worker_exit.json',dict(runner_returncode=rc,error=error,plan_sha256=digest,
        retries=0,accepted8_rerun=False,finished=time.time()))
    result = subprocess.run([sys.executable,'-B',str(HERE / 'check_remainder75.py'),'--out',str(OUT),
        '--plan-sha256',digest],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
    (OUT / 'checker.log').write_text(result.stdout)
    print(result.stdout,flush=True)
    return result.returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare-plan',action='store_true')
    mode.add_argument('--dry-run',action='store_true')
    mode.add_argument('--launch',action='store_true')
    mode.add_argument('--worker')
    parser.add_argument('--parent-review-sha256')
    args = parser.parse_args()
    if args.prepare_plan:
        prepare_plan()
    elif args.dry_run:
        dry_run()
    elif args.launch:
        require(args.parent_review_sha256, 'Launch requires explicit parent review SHA')
        raise SystemExit(launch(args.parent_review_sha256))
    else:
        try:
            rc = worker(args.worker)
        except Exception as error:
            if OUT.exists() and not (OUT / 'worker_exit.json').exists() and not (OUT / 'complete.json').exists():
                save(OUT / 'worker_exit.json',dict(runner_returncode=1,error=repr(error),
                    plan_sha256=args.worker,retries=0,accepted8_rerun=False,finished=time.time()))
                save(OUT / 'complete.json',dict(status='NOT_ACCEPTED',reason=repr(error),
                    plan_sha256=args.worker,retries=0,finished=time.time()))
            print('WORKER_NOT_ACCEPTED',repr(error),flush=True)
            rc = 1
        raise SystemExit(rc)
