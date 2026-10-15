#!/usr/bin/env python3
"""Continue only seven never-started cases; immutable accepted control is inherited."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
import replay_successor04 as sealed
import check_continuation as checker
from prepare_batch import HERE, ROOT, INTEGRATION, sha, save

DATA, IMAGE, IMAGE_SHA = sealed.DATA, sealed.IMAGE, sealed.IMAGE_SHA
OUT = DATA / 'vcs_candidate04_remaining7_01'
UNIT = 'ara-gather-tuple7-candidate04-cont01.service'
NAMES = checker.NAMES
integration = sealed.integration
read, require, pins_check, oracle = sealed.read, sealed.require, sealed.pins_check, sealed.oracle
sealed.old.OUT = OUT
sealed.old.UNIT = UNIT


def progress_checks(before, after, simv, cgroup):
    return [dict(same_pid=a['pid'] == b['pid'], cpu_growing=b['cpu_ticks'] > a['cpu_ticks'],
        trace_growing=b['trace_bytes'] > a['trace_bytes'], cycle_growing=b['last_cycle'] > a['last_cycle'],
        correct_executable=a['executable'] == b['executable'] == str(Path(simv).resolve()),
        correct_cgroup=a['cgroup'] == b['cgroup'] == cgroup,
        same_command=a['argv'] == b['argv'], same_cwd=a['cwd'] == b['cwd'])
        for a,b in zip(before,after)]


def confirm_startup(done):
    destination = OUT / 'remaining7/actual_simv_confirmation.json'
    samples, checks, discovery, cgroup = [], [], [], None
    try:
        prefix = str(OUT / 'remaining7')+'/'
        simv = read(IMAGE / 'image.json')['simv']
        cgroup = Path('/proc/self/cgroup').read_text()
        deadline = time.monotonic()+60
        processes = []
        # Bounded startup discovery waits for actual retirement data, not merely
        # the VCS loader PID; it never polls long-run completion.
        while time.monotonic() < deadline:
            processes = []
            for proc in Path('/proc').glob('[0-9]*'):
                try:
                    args = [s.decode() for s in (proc / 'cmdline').read_bytes().split(b'\0') if s]
                    if args and args[0] == simv and any(prefix in arg for arg in args):
                        processes.append((int(proc.name), args))
                except (OSError, UnicodeError):
                    continue
            if len(processes) == 2:
                try:
                    before = [sealed.sample(pid,args) for pid,args in processes]
                    discovery.append(before)
                    if all(x['last_cycle'] > 0 and x['trace_bytes'] > 0 and
                           x['executable'] == str(Path(simv).resolve()) and
                           x['cgroup'] == cgroup for x in before):
                        samples.append(before)
                        break
                except OSError as error:
                    discovery.append(dict(process_race=str(error)))
            if done.is_set():
                raise ValueError('Stage finished before two simultaneous workers could be confirmed')
            time.sleep(0.5)
        require(len(samples) == 1, 'Two ready real simv workers not observed in startup window')
        time.sleep(3)
        after = [sealed.sample(pid,args) for pid,args in processes]
        samples.append(after)
        checks = progress_checks(samples[0], samples[1], simv, cgroup)
        require(len(checks) == 2 and all(all(x.values()) for x in checks), 'Real simv growth/identity check failed')
        record = dict(status='ADVANCING_2_SIMV', samples=samples, checks=checks,
                      raw_samples_retained=True, discovery=discovery, worker_cgroup=cgroup,
                      completion_polling=False, startup_bound_s=60, finished=time.time())
    except Exception as error:
        record = dict(status='NOT_CONFIRMED', reason=str(error), samples=samples, checks=checks,
                      discovery=discovery, raw_samples_retained=True, worker_cgroup=cgroup,
                      finished=time.time())
    save(destination, record)


def launch():
    require(not OUT.exists(), 'Fresh continuation output required; no retry')
    require('LoadState=not-found' in subprocess.check_output(
        ['systemctl', '--user', 'show', UNIT, '-p', 'LoadState'], text=True), 'Unit collision')
    inherited = checker.inherited_control()
    origin = checker.CONTROL
    old_plan = read(origin / 'plan.json')
    require(read(origin / 'complete.json')['status'] == 'NOT_ACCEPTED' and
            read(origin / 'worker_exit.json')['error'] == "ValueError('Startup confirmation missing')",
            'Not the authorized startup-gate-only continuation')
    require(not (origin / 'remaining7').exists(), 'Remaining seven already started; refuse retry')
    require(sha(IMAGE / 'image.json') == IMAGE_SHA and old_plan['image_sha256'] == IMAGE_SHA,
            'M4 image ledger changed')
    programs = read(DATA / 'soc01/programs.json')
    require(list(programs['programs']) == NAMES and programs['backend'] == 'vcs-soc', 'Program membership drift')
    prepared = Path(programs['prepared'])
    integration.check(prepared)
    require(sha(prepared / 'provenance.json') == programs['provenance_sha256'], 'Prepared drift')
    pins = dict(old_plan['pins'])
    pins_check(pins)
    tested = read(DATA / 'continuation_host.json')
    require(tested['status'] == 'PASS' and tested['worker_sha256'] == sha(Path(__file__)) and
            tested['checker_sha256'] == sha(HERE / 'check_continuation.py') and
            tested['test_sha256'] == sha(HERE / 'test_continuation.py'), 'Continuation tests stale/not PASS')
    for path in origin.rglob('*'):
        if path.is_file():
            pins[str(path)] = sha(path)
    for path in (Path(__file__), HERE / 'check_continuation.py', HERE / 'test_continuation.py',
                 DATA / 'continuation_host.json', HERE / 'CONTINUATION.md'):
        pins[str(path)] = sha(path)
    pins_check(pins)
    gate = sealed.resources()
    require(gate['passed'], 'Resource/Tesla admission blocked; no launch')
    OUT.mkdir()
    save(OUT / 'resource_gate.json', gate)
    save(OUT / 'inherited_control.json', inherited)
    plan = dict(old_plan, pins=pins, unit=UNIT, control_source=str(origin),
        control_plan_sha256=checker.CONTROL_HASH, run_names=NAMES[1:], skip_control_execution=True,
        retries=0, stop_first_failure=True,
        scope='Inherited raw-accepted control plus seven never-started source tuples; not control retry/parent/Linux/board closure')
    save(OUT / 'plan.json', plan)
    service = ['systemd-run', '--user', '--unit='+UNIT, '--collect',
        '--property=RuntimeMaxSec=1500', '--property=TimeoutStopSec=120',
        '--property=KillMode=control-group', '--property=Restart=no',
        '--property=WorkingDirectory='+str(ROOT),
        '--property=StandardOutput=append:'+str(OUT / 'service.log'),
        '--property=StandardError=append:'+str(OUT / 'service.log'),
        sys.executable, '-B', str(Path(__file__).resolve()), '--worker', sha(OUT / 'plan.json')]
    save(OUT / 'service_command.json', service)
    result = subprocess.run(service, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
    save(OUT / 'launch.json', dict(returncode=result.returncode, output=result.stdout, time=time.time()))
    print(result.stdout, 'OUT='+str(OUT), 'INHERITED_CONTROL=PASS_NO_RERUN',
          'ADMISSION='+str(gate['total_live_reserved'])+'/24',
          'MEM_GIB='+str(round(gate['available_bytes']/1024**3, 2)), flush=True)
    return result.returncode


def worker(plan_hash):
    require(sha(OUT / 'plan.json') == plan_hash, 'Plan drift')
    plan = read(OUT / 'plan.json')
    pins_check(plan['pins'])
    checker.inherited_control()
    require(plan['run_names'] == NAMES[1:] and plan['skip_control_execution'], 'Refuse control execution')
    (OUT / 'admission').mkdir()
    folder = OUT / 'remaining7'
    folder.mkdir()
    save(OUT / 'worker.json', dict(pid=os.getpid(), started=time.time(), inherited_control=True,
                                  cgroup=Path('/proc/self/cgroup').read_text(),
                                  plan_sha256=plan_hash))
    framework = integration.framework
    lock = threading.Lock()
    def admitted(repo):
        base, options, case, image = framework(repo)
        class Runner(base):
            def _run_test(self, test, simv):
                require(test.name in NAMES[1:], 'Refuse control retry')
                if not self.cancel_event.is_set():
                    with lock:
                        gate = sealed.resources()
                        save(OUT / 'admission' / (test.name+'.json'), gate)
                        require(gate['passed'], 'Per-case resource/Tesla admission blocked')
                return super()._run_test(test, simv)
        return Runner, options, case, image
    integration.framework = admitted
    integration.oracle_complete = oracle
    integration.framework(Path(read(IMAGE / 'image.json')['snapshot']) / 'sources')
    import ara_verify.runner as engine
    engine.FAIL_RE = re.compile(engine.FAIL_RE.pattern+'|'+sealed.old.FAIL.pattern, re.I | re.M)
    env = integration.environment()
    os.environ.clear()
    os.environ.update(env)
    command = [sys.executable, '-B', str(INTEGRATION / 'run.py'), 'run', '--image', str(IMAGE),
        '--programs', plan['programs'], '--out', str(folder / 'replay'), '--jobs', '2',
        '--timeout', '300', '--execute']
    for name in NAMES[1:]:
        command += ['--case', name]
    save(folder / 'runner_command.json', command)
    done = threading.Event()
    observer = threading.Thread(target=confirm_startup, args=(done,))
    observer.start()
    rc, error = 1, None
    try:
        with (folder / 'runner.log').open('x') as log:
            stdout, stderr = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = log
            try:
                rc = integration.run_programs(SimpleNamespace(image=IMAGE, programs=Path(plan['programs']),
                    out=folder / 'replay', case=NAMES[1:], jobs=2, timeout=300, execute=True))
            finally:
                sys.stdout, sys.stderr = stdout, stderr
        pins_check(plan['pins'])
    except Exception as caught:
        rc, error = 1, repr(caught)
    finally:
        done.set()
        observer.join()
    save(OUT / 'worker_exit.json', dict(runner_returncode=rc, error=error,
        plan_sha256=plan_hash, finished=time.time(), retries=0, control_rerun=False))
    result = subprocess.run([sys.executable, '-B', str(HERE / 'check_continuation.py'),
        '--out', str(OUT), '--plan-sha256', plan_hash], stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, timeout=120)
    (OUT / 'checker.log').write_text(result.stdout)
    print(result.stdout, flush=True)
    return result.returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--launch', action='store_true')
    mode.add_argument('--worker')
    args = parser.parse_args()
    raise SystemExit(worker(args.worker) if args.worker else launch())
