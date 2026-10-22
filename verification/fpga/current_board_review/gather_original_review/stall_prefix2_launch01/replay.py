#!/usr/bin/env python3
"""Prepare-only by default; explicit later parent approval transfers FP1302's two slots."""
import argparse
import errno
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
LOCAL = Path(__file__).resolve().parent
HERE = LOCAL.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(LOCAL))
sys.path.insert(0, str(HERE.parent/'fp_comparison_original'))
import checker
import replay_remainder75 as helpers
import replay_restart_units as fp
import restart_dependency_gate as dependency
from prepare_batch import ROOT, INTEGRATION, sha, save
from replay_candidate03 import read, require, pins_check
from prepare_successor import symbol
from audit_accepted8 import OBJDUMP, instructions

DATA, NAMES = checker.DATA, checker.NAMES
IMAGE, IMAGE_SHA = helpers.IMAGE, helpers.IMAGE_SHA
integration = helpers.integration
UNIT = 'ara-gather-prefix2-candidate04-01.service'
OUT = LOCAL/'vcs_candidate04_01'
FP_UNIT = 'ara-fp-original-restart-candidate04-02.service'
FP_PLAN = HERE.parent/'fp_comparison_original/candidate04_restart_plan08/plan.json'
FP_RUN = HERE.parent/'fp_comparison_original/candidate04_restart_run04'
FP_TERMINAL_SHA = 'ef2eb50bdf0e4f4eb35e9af794d2fdf26cca99286623723818507265ab650747'
UNITS = dict(whole='ara-whole1134-candidate04-01.service', nf7='ara-indexed-nf7-candidate02-06.service',
    nf8='ara-nf8-full192-candidate04-01.service', prefix5='ara-arithmetic-prefix5-candidate04-01.service',
    fp=FP_UNIT, gather=UNIT)
QUOTAS = dict(whole=6, nf7=2, nf8=8, prefix5=2, gather=2)


def contract(plan):
    require(plan['names'] == NAMES and plan['image'] == str(IMAGE) and plan['image_sha256'] == IMAGE_SHA and
            plan['programs'] == str(DATA/'soc01') and plan['unit'] == UNIT and plan['output'] == str(OUT), 'Execution identity differs')
    require(plan['jobs'] == 2 and plan['timeout_per_case_s'] == 9000 and plan['service_runtime_max_s'] == 9600 and
            plan['retries'] == 0 and plan['stop_first_failure'] and plan['requires_parent_review'] and
            plan['units'] == UNITS and plan['quotas_after_transfer'] == QUOTAS, 'Budget/transfer contract differs')
    require(plan['original_stopped_tuple'] is None and not plan['exact11_failure_reproduction'] and
            not plan['full_parent_closure'] and not plan['original_linux_elf_replay'], 'Unsupported coverage claim')
    proof = read(DATA/'source_elf_proof.json')['results']
    programs = read(DATA/'soc01/programs.json')['programs']
    require([s['name'] for s in plan['cases']] == NAMES, 'Not exact two source keys')
    for case, original in zip(plan['cases'], proof):
        require(case['operation'] in (1,20) and case['soc_routine'] == original['soc_routine'] and
                case['elf_sha256'] == programs[case['name']]['sha256'] and
                case['source_sha256'] == original['source_sha256'] and
                case['original_linux_elf_sha256'] == original['original_linux_elf_sha256'] and
                case['expected_calls'] == 98 and case['expected_fullcap'] == 50176 and
                case['expected_guards'] == 196, 'Source/ELF/oracle scope drift')
        elf = Path(programs[case['name']]['path'])
        for field, sym in (('input_address','input'), ('index_address','indices16' if case['operation']==20 else 'indices'),
                           ('output_address','output'), ('predicate_address','predicate')):
            require(case[field] == symbol(elf,sym,OBJDUMP)[0], 'Wrong SoC symbol '+field)
        store, = [r for r in instructions(elf,'replay_exit') if r['text'].startswith('sd\t')]
        require(case['exit_store_address']==0xd0000000 and case['exit_store_pc']==store['pc'], 'Wrong SoC CTRL exit store')


def resource_math(live, available, tesla=False):
    counts = {n:0 for n in UNITS}
    unknown = []
    for process in live:
        parts = {s for line in process['cgroup'].splitlines() for s in line.split('/')}
        owners = [n for n,unit in UNITS.items() if unit in parts]
        require(len(owners) <= 1, 'Ambiguous cgroup ownership')
        if owners:
            counts[owners[0]] += 1
        else:
            unknown.append(process)
    total = sum(max(q,counts[n]) for n,q in QUOTAS.items())+len(unknown)
    require(counts['fp'] == 0, 'WAIT: FP1302 simv still owns its slots')
    require(counts['gather'] <= 2 and total <= 24 and available >= 32*1024**3 and not tesla,
            'Resource/Tesla admission failed')
    return dict(counts=counts, unknown=unknown, quotas=QUOTAS, fp_slots_after_transfer=0,
        own_reserved=2, total_live_plus_reserved=total, cap=24, mem_available_bytes=available,
        slot_transfer='FP1302:2 -> GatherPrefix2:2; not additional slots')


def resources():
    _, tesla, unreadable = helpers.scan_processes(Path('/proc').glob('[0-9]*'))
    require(not unreadable, 'Potential simulator/worker unreadable: '+repr(unreadable))
    live = fp.scan_simv()  # comm OR argv0; permission/query failures propagate, exit races alone ignored.
    available = int(next(s.split()[1] for s in Path('/proc/meminfo').read_text().splitlines()
                         if s.startswith('MemAvailable:')))*1024
    return dict(time=time.time(), **resource_math(live,available,tesla))


def approval(review, digest, ready_hash):
    require(review.get('parent_authorized') is True and review.get('plan_sha256') == digest and
            review.get('review_ready_sha256') == ready_hash and review.get('image_sha256') == IMAGE_SHA and
            review.get('jobs') == 2 and review.get('units') == UNITS and
            review.get('fp1302_two_slots_released_to_gather') is True and
            review.get('parent_coordination_before_start') is True, 'WAIT: explicit coordinated slot transfer/approval missing')
    item = review['fp_terminal']
    require(item['path'] == str(FP_RUN/'complete.json') and sha(Path(item['path'])) == item['sha256'], 'WAIT: exact FP1302 terminal hash missing')
    terminal = read(item['path'])
    require(terminal.get('finished',0) > 0 and terminal.get('plan_sha256') == sha(FP_PLAN) and
            terminal.get('status') in ('PASS_2_ORIGINAL_PREFIXES_260_CALLS_M4','NOT_PASS'), 'WAIT: FP1302 not terminal')
    return terminal


def fresh_admission(review, digest, ready_hash):
    terminal = approval(review,digest,ready_hash)
    # One fresh check, never a wait loop. A terminal FAIL only frees scheduling slots, not arithmetic acceptance.
    state = dependency.query_unit(FP_UNIT)
    empty = dependency.absence([FP_UNIT])
    return dict(fp_terminal_sha256=review['fp_terminal']['sha256'], fp_status=terminal['status'],
        fp_service=state, fp_absence=empty, resources=resources())


def checked_plan():
    plan = read(LOCAL/'plan.json')
    contract(plan)
    pins_check(plan['pins'])
    fp.module_gate(plan['pins'])
    return plan, sha(LOCAL/'plan.json')


def prepare():
    require(not (LOCAL/'plan.json').exists(), 'Fresh plan only; no sealed overwrite')
    ready = read(DATA/'prepared_ready.json')
    require(sha(DATA/'prepared_ready.json') == 'a6eb525b0f3461f7d5711e101e596d1d77bbe998ef26ae5be177acd0f956177e' and
            ready['status'] == 'PREPARED_TWO_CHILD_PREFIXES_HOST_SPIKE_PASS_NOT_DUT', 'Wrong prepared two prefixes')
    audit = HERE/'stall_prefix2_audit01/audit.json'
    require(sha(audit) == 'ce33455e35cb3a05ff9b31f76b2e6ef650172ede3b730bc9703e07227984684e' and
            read(audit)['negative_tests_passed'] == 9, 'Independent original-source audit missing')
    require(sha(FP_RUN/'complete.json') == FP_TERMINAL_SHA and
            read(FP_RUN/'complete.json')['status'] == 'PASS_2_ORIGINAL_PREFIXES_260_CALLS_M4', 'Accepted FP1302 terminal drift')
    tested = subprocess.run([sys.executable,'-B',str(LOCAL/'test_plan.py')],text=True,
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
    (LOCAL/'preseal_host.log').write_text(tested.stdout)
    require(tested.returncode==0 and re.search(r'Ran 17 tests',tested.stdout) and
            tested.stdout.rstrip().endswith('OK'), 'Preseal negative tests failed; no plan')
    pins = {**read(DATA/'baseline_pins.json'), **read(DATA/'prepared_pins.json')}
    pins_check(pins)
    require(sha(IMAGE/'image.json') == IMAGE_SHA, 'Wrong frozen M4')
    image = read(IMAGE/'image.json')
    snapshot = Path(image['snapshot'])
    repo = integration.sealed(snapshot)
    _,_,_,image_files = integration.framework(repo)
    require(image_files(Path(image['simv'])) == image['files'], 'Frozen image drift')
    integration.check(DATA/'prepared')
    programs = read(DATA/'soc01/programs.json')['programs']
    references = read(DATA/'reference/reference.json')['results']
    cases = []
    for proof, ref, op in zip(read(DATA/'source_elf_proof.json')['results'], references, (1,20)):
        name = proof['name']
        elf = Path(programs[name]['path'])
        case = dict(name=name, operation=op, soc_routine=proof['soc_routine'],
            source_sha256=proof['source_sha256'], original_linux_elf_sha256=proof['original_linux_elf_sha256'],
            elf_sha256=programs[name]['sha256'], expected_calls=98, expected_fullcap=50176, expected_guards=196,
            spike_retired_to_exit=ref['firmware_retired_to_htif_store'])
        for field,sym in (('input_address','input'), ('index_address','indices16' if op==20 else 'indices'),
                          ('output_address','output'), ('predicate_address','predicate')):
            case[field] = symbol(elf,sym,OBJDUMP)[0]
        store, = [r for r in instructions(elf,'replay_exit') if r['text'].startswith('sd\t')]
        case.update(exit_store_address=0xd0000000,exit_store_pc=store['pc'])
        cases.append(case)
    pins.update(image['files'])
    pins.update({str(repo/n):h for n,h in read(snapshot/'snapshot.json')['files'].items()})
    pins.update(fp.local_modules())
    for path in (DATA/'prepared_ready.json', DATA/'baseline_pins.json', DATA/'prepared_pins.json', audit,
                 FP_PLAN, FP_RUN/'complete.json', FP_RUN.parent/'TERMINAL08.md', LOCAL/'preseal_host.log',
                 IMAGE/'image.json', snapshot/'snapshot.json', Path(image['simv']).parent/'simulator.conf',
                 Path(image['simv']).parent/'vcs_source_manifest.json', OBJDUMP, LOCAL/'checker.py', LOCAL/'test_plan.py', LOCAL/'README.md'):
        pins[str(path)] = sha(path)
    plan = dict(names=NAMES, cases=cases, image=str(IMAGE), image_sha256=IMAGE_SHA, programs=str(DATA/'soc01'),
        unit=UNIT, output=str(OUT), jobs=2, timeout_per_case_s=9000, service_runtime_max_s=9600,
        retries=0, stop_first_failure=True, requires_parent_review=True, units=UNITS, quotas_after_transfer=QUOTAS,
        original_stopped_tuple=None, exact11_failure_reproduction=False, full_parent_closure=False,
        original_linux_elf_replay=False, prepare_only=True, pins=pins,
        compiler_limitation='Archived Buildroot GCC14.3.0 vs existing Xuantie GCC14.1.1: full Linux ELF not byte-identical; authentic C hash and all13 asm encodings proven',
        startup_window_s=60, startup_sampling_only=True, required_fp_terminal=str(FP_RUN/'complete.json'))
    contract(plan)
    pins_check(pins)
    save(LOCAL/'plan.json', plan)
    save(LOCAL/'host_gate.json',dict(status='PASS',tests=17,plan_sha256=sha(LOCAL/'plan.json'),
        worker_sha256=sha(Path(__file__)),checker_sha256=sha(LOCAL/'checker.py'),test_sha256=sha(LOCAL/'test_plan.py'),
        log_sha256=sha(LOCAL/'preseal_host.log'),no_dut_launched=True))
    save(LOCAL/'review.template.json', dict(parent_authorized=False, parent_coordination_before_start=False,
        fp1302_two_slots_released_to_gather=False, plan_sha256=sha(LOCAL/'plan.json'),
        review_ready_sha256='PARENT_PIN_READY_SHA', image_sha256=IMAGE_SHA, jobs=2, units=UNITS,
        fp_terminal=dict(path=str(FP_RUN/'complete.json'),sha256=FP_TERMINAL_SHA)))
    print('PLAN_PREPARED_NO_DUT',sha(LOCAL/'plan.json'),flush=True)


def dryrun():
    plan,digest = checked_plan()
    require(not (LOCAL/'dryrun').exists(), 'Fresh dryrun only')
    rc = integration.run_programs(SimpleNamespace(image=IMAGE, programs=Path(plan['programs']), out=LOCAL/'dryrun',
        case=NAMES, jobs=2, timeout=9000, execute=False))
    run, rows = read(LOCAL/'dryrun/run.json'), read(LOCAL/'dryrun/summary.json')
    require(rc == 0 and [r['name'] for r in rows] == NAMES and all(r['status']=='DRY_RUN' for r in rows) and
            run['status_counts'] == {'DRY_RUN':2} and run['jobs']==2 and run['timeout_s']==9000, 'Dryrun differs')
    pins_check(plan['pins'])
    save(LOCAL/'dryrun_gate.json',dict(status='PASS_TWO_DRYRUN_NO_DUT',plan_sha256=digest,
        run_sha256=sha(LOCAL/'dryrun/run.json'), summary_sha256=sha(LOCAL/'dryrun/summary.json'), no_dut_launched=True))
    save(LOCAL/'review_ready.json',dict(status='READY_TWO_PREFIX_PLAN_NO_DUT',plan_sha256=digest,
        host_gate_sha256=sha(LOCAL/'host_gate.json'),dryrun_gate_sha256=sha(LOCAL/'dryrun_gate.json'),
        prepared_ready_sha256=sha(DATA/'prepared_ready.json'),fp_terminal_sha256=FP_TERMINAL_SHA,
        jobs=2,timeout_per_case_s=9000,service_runtime_max_s=9600,no_dut_launched=True,
        explicit_later_parent_review_required=True,pin_count=len(plan['pins'])))
    print('READY_TWO_PREFIX_PLAN_NO_DUT',sha(LOCAL/'review_ready.json'),'PLAN='+digest,flush=True)


def confirmation(done, cancel):
    plan, _ = checked_plan()
    worker = read(OUT/'worker.json')
    simv = read(IMAGE/'image.json')['simv']
    deadline = time.monotonic()+60
    discovery, record = [], None
    try:
        while time.monotonic() < deadline and not done.is_set():
            live,_,unreadable = helpers.scan_processes(Path('/proc').glob('[0-9]*'))
            require(not unreadable, 'Unreadable potential startup simv')
            own = [p for p in live if any(str(OUT)+'/' in a for a in p['argv'])]
            require(all(p['argv'][0]==simv for p in own) and len(own)<=2, 'Fatal own startup identity mismatch')
            if len(own)==2:
                try:
                    processes = sorted(own,key=lambda p:p['pid'])
                    before = [helpers.sample(p['pid'],p['argv']) for p in processes]
                    observed = dict(status='ADVANCING_TWO_SIMV',samples=[before,before],worker_cgroup=worker['cgroup'])
                    checker.identity(observed,plan,OUT,worker)
                    discovery.append(before)
                    while time.monotonic()<deadline and not done.is_set():
                        done.wait(min(.5,max(0,deadline-time.monotonic())))
                        after = [helpers.sample(p['pid'],p['argv']) for p in processes]
                        if any(a['start_ticks']!=b['start_ticks'] for a,b in zip(before,after)):
                            raise ProcessLookupError(errno.ESRCH,'PID generation changed')
                        observed['samples'] = [before,after]
                        checker.identity(observed,plan,OUT,worker)
                        discovery.append(after)
                        if grows(before,after):
                            checker.progress(observed,plan,OUT,worker)
                            record = observed
                            break
                    if record:
                        break
                except OSError as error:
                    if error.errno not in (errno.ENOENT,errno.ESRCH):
                        raise
                    discovery.append(dict(process_race=repr(error)))
            done.wait(min(.5,max(0,deadline-time.monotonic())))
        require(record is not None, 'No two advancing real simv within original60s startup window')
    except Exception as error:
        record = dict(status='NOT_CONFIRMED',reason=repr(error),samples=[],worker_cgroup=worker['cgroup'])
        cancel()
    record.update(discovery=discovery,startup_bound_s=60,completion_polling=False)
    save(OUT/'actual_simv_confirmation.json',record)


def grows(before, after):
    return all(b['cpu_ticks']>a['cpu_ticks'] and b['trace_bytes']>a['trace_bytes']>0 and
               b['last_cycle']>a['last_cycle']>0 for a,b in zip(before,after))


def publish(abort, record, eligible):
    require(threading.current_thread() is threading.main_thread() and len(threading.enumerate())==1, 'Unjoined workers at publication')
    good, bad = OUT/'complete.pass.tmp', OUT/'complete.notpass.tmp'
    save(good,dict(record,status='PASS_TWO_AUTHENTIC_98CALL_CHILD_PREFIXES_M4',aborted=False))
    save(bad,dict(record,status='NOT_ACCEPTED',aborted=abort.is_set()))
    previous = signal.pthread_sigmask(signal.SIG_BLOCK,fp.SIGNALS)
    try:
        with abort.lock:
            require(abort.terminal is None and not (OUT/'complete.json').exists(), 'Terminal publication is single-use')
            passed = eligible and not abort.is_set() and not (signal.sigpending() & fp.SIGNALS)
            os.replace(good if passed else bad,OUT/'complete.json')
            abort.terminal = passed
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK,previous)
        good.unlink(missing_ok=True)
        bad.unlink(missing_ok=True)
    return passed


def worker(digest):
    plan, expected = checked_plan()
    require(digest == expected == sha(OUT/'plan.json') and not (OUT/'worker.json').exists(), 'Worker plan/retry drift')
    review = read(OUT/'parent_review.json')
    require(sha(OUT/'parent_review.json') == read(OUT/'authorization.json')['review_sha256'] and
            sha(LOCAL/'review_ready.json') == read(OUT/'authorization.json')['ready_sha256'], 'Approval hash drift')
    cgroup = Path('/proc/self/cgroup').read_text()
    require(UNIT in {s for line in cgroup.splitlines() for s in line.split('/')}, 'Worker outside authorized cgroup')
    save(OUT/'worker.json',dict(pid=os.getpid(),cgroup=cgroup,started=time.time(),plan_sha256=digest))
    abort = fp.AbortLatch()
    rc, error, results = 1, None, []
    with abort.signals():
        done = threading.Event()
        observer = None
        try:
            save(OUT/'worker_admission.json',fresh_admission(review,digest,sha(LOCAL/'review_ready.json')))
            (OUT/'admission').mkdir()
            image = read(IMAGE/'image.json')
            framework = integration.framework
            programs = read(Path(plan['programs'])/'programs.json')['programs']
            specs = {s['name']:s for s in plan['cases']}
            lock = threading.Lock()
            def admitted(repo):
                parent,options,test,image_files = framework(repo)
                from ara_verify.trace import validate_trace
                class Runner(parent):
                    def __init__(self,*a,**kw):
                        super().__init__(*a,**kw)
                        self.cancel_event = abort

                    def _run_test(self,test,simv):
                        try:
                            require(test.name in NAMES, 'Unknown/accepted-single execution denied')
                            if not abort.is_set():
                                with lock:
                                    save(OUT/'admission'/(test.name+'.json'),resources())
                            result = super()._run_test(test,simv)
                            if result.status == 'PASS':
                                try:
                                    checked = checker.check_case(dict(name=result.name,status=result.status,returncode=result.returncode,
                                        reason=result.reason,artifact_dir=str(result.artifact_dir)),result.artifact_dir,
                                        programs[test.name],image,specs[test.name],checker.source.prep.model(specs[test.name]['operation']),validate_trace)
                                    save(result.artifact_dir/'independent_case_gate.json',checked)
                                except Exception as caught:
                                    result.status,result.reason = 'FAIL','Independent gate: '+repr(caught)
                            if result.status != 'PASS':
                                abort.set()
                            return abort.accept(result)
                        except BaseException:
                            abort.set()
                            raise
                return Runner,options,test,image_files
            integration.framework = admitted
            integration.oracle_complete = lambda entry,text: not checker.VETO.search(text) and all(
                text.splitlines().count(m)==1 for m in entry['pass_markers'])
            integration.framework(Path(image['snapshot'])/'sources')
            import ara_verify.runner as engine
            from ara_verify.trace import validate_trace
            engine.FAIL_RE = re.compile(engine.FAIL_RE.pattern+'|'+checker.VETO.pattern,re.I|re.M)
            fp.module_gate(plan['pins'])
            os.environ.update(integration.environment())
            observer = threading.Thread(target=confirmation,args=(done,abort.set))
            observer.start()
            with (OUT/'runner.log').open('x') as stream:
                stdout,stderr = sys.stdout,sys.stderr
                sys.stdout = sys.stderr = stream
                try:
                    rc = integration.run_programs(SimpleNamespace(image=IMAGE, programs=Path(plan['programs']),
                        out=OUT/'replay',case=NAMES,jobs=2,timeout=9000,execute=True))
                finally:
                    sys.stdout,sys.stderr = stdout,stderr
            done.set()
            observer.join()
            save(OUT/'worker_exit.json',dict(runner_returncode=rc,error=None,plan_sha256=digest,
                aborted=abort.is_set(),retries=0,finished=time.time()))
            results = checker.terminal(OUT,plan,digest,validate_trace)
        except BaseException as caught:
            error = f'{type(caught).__name__}: {caught}'
            abort.set()
        finally:
            done.set()
            if observer:
                observer.join()
        save(OUT/'worker_exit.json',dict(runner_returncode=rc,error=error,plan_sha256=digest,
            aborted=abort.is_set(),retries=0,finished=time.time()))
        record = dict(plan_sha256=digest,results=results,error=error,retries=0,finished=time.time(),
            original_stopped_tuple=None,exact11_failure_reproduction=False,full_parent_closure=False,original_linux_elf_replay=False)
        return int(not publish(abort,record,rc==0 and error is None and len(results)==2))


def launch(review_path, review_hash, ready_hash, authorized):
    require(authorized and ready_hash == sha(LOCAL/'review_ready.json') and review_hash == sha(review_path), 'Explicit later authorization hashes required')
    plan,digest = checked_plan()
    ready = read(LOCAL/'review_ready.json')
    require(ready['status']=='READY_TWO_PREFIX_PLAN_NO_DUT' and ready['plan_sha256']==digest and
            ready['host_gate_sha256']==sha(LOCAL/'host_gate.json') and ready['dryrun_gate_sha256']==sha(LOCAL/'dryrun_gate.json'), 'Ready gates drift')
    host,dry = read(LOCAL/'host_gate.json'),read(LOCAL/'dryrun_gate.json')
    require(host['status']=='PASS' and host['tests']==17 and host['plan_sha256']==digest and
            host['worker_sha256']==sha(Path(__file__)) and host['checker_sha256']==sha(LOCAL/'checker.py') and
            host['test_sha256']==sha(LOCAL/'test_plan.py') and host['no_dut_launched'], 'Host regression not bound/PASS')
    require(dry['status']=='PASS_TWO_DRYRUN_NO_DUT' and dry['plan_sha256']==digest and dry['no_dut_launched'] and
            dry['run_sha256']==sha(LOCAL/'dryrun/run.json') and dry['summary_sha256']==sha(LOCAL/'dryrun/summary.json'), 'Dryrun evidence drift')
    require(not OUT.exists(), 'Fresh output only; no retry')
    admission = fresh_admission(read(review_path),digest,ready_hash)
    state = dependency.query_unit(UNIT)
    require(state['properties']['LoadState']=='not-found', 'Own service collision')
    dependency.absence([UNIT])
    OUT.mkdir()
    shutil.copyfile(LOCAL/'plan.json',OUT/'plan.json')
    shutil.copyfile(review_path,OUT/'parent_review.json')
    save(OUT/'authorization.json',dict(ready_sha256=ready_hash,review_sha256=review_hash,plan_sha256=digest))
    save(OUT/'launch_admission.json',admission)
    command = ['systemd-run','--user','--unit='+UNIT,'--collect','--property=RuntimeMaxSec=9600',
        '--property=TimeoutStopSec=120','--property=KillMode=control-group','--property=Restart=no',
        '--property=WorkingDirectory='+str(ROOT),'--property=StandardOutput=append:'+str(OUT/'service.log'),
        '--property=StandardError=append:'+str(OUT/'service.log'),sys.executable,'-B',str(Path(__file__).resolve()),'worker','--plan-sha256',digest]
    save(OUT/'service_command.json',command)
    result = subprocess.run(command,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30,env=dependency.bus_environment())
    save(OUT/'launch.json',dict(returncode=result.returncode,output=result.stdout,time=time.time(),plan_sha256=digest))
    print(result.stdout,'UNIT='+UNIT,'OUT='+str(OUT),flush=True)
    return result.returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','dryrun','launch','worker'))
    parser.add_argument('--authorize-run',action='store_true')
    parser.add_argument('--review',type=Path)
    parser.add_argument('--review-sha256')
    parser.add_argument('--ready-sha256')
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    require(sys.flags.optimize==0, 'Python -O prohibited')
    if args.mode=='prepare':
        prepare()
    elif args.mode=='dryrun':
        dryrun()
    elif args.mode=='launch':
        require(args.review is not None, 'Parent review required')
        raise SystemExit(launch(args.review,args.review_sha256,args.ready_sha256,args.authorize_run))
    else:
        try:
            rc = worker(args.plan_sha256)
        except BaseException as error:
            if OUT.exists() and not (OUT/'complete.json').exists():
                save(OUT/'worker_exit.json',dict(runner_returncode=1,error=repr(error),plan_sha256=args.plan_sha256,
                    aborted=True,retries=0,finished=time.time()))
                save(OUT/'complete.json',dict(status='NOT_ACCEPTED',reason=repr(error),plan_sha256=args.plan_sha256,
                    aborted=True,retries=0,finished=time.time()))
            print('WORKER_NOT_ACCEPTED',repr(error),flush=True)
            rc = 1
        raise SystemExit(rc)
