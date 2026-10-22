#!/usr/bin/env python3
"""Sealed candidate04: one control before seven successors, no retries."""
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
import replay_candidate03 as old
from prepare_batch import HERE, ROOT, INTEGRATION, sha, save
from check_successor import NAMES

integration = old.integration
DATA = HERE / 'successor01'
OUT = DATA / 'vcs_candidate04_01'
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate04/campaign/image')
IMAGE_SHA = 'e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673'
UNIT = 'ara-gather-tuple8-candidate04.service'
old.OUT = OUT
old.IMAGE = IMAGE
old.UNIT = UNIT
read, require, pins_check, oracle = old.read, old.require, old.pins_check, old.oracle


def resources():
    gate = old.resources()
    gate['passed'] = gate['passed'] and not gate['tesla_workers'] and \
        gate['reservations']['tesla_comparison']['observed_live'] == 0
    return gate


def launch():
    require(not OUT.exists(), 'Fresh output required; no retry')
    require('LoadState=not-found' in subprocess.check_output(
        ['systemctl', '--user', 'show', UNIT, '-p', 'LoadState'], text=True), 'Service collision')
    require(sha(IMAGE / 'image.json') == IMAGE_SHA, 'Wrong candidate04 ledger')
    ledger = read(IMAGE / 'image.json')
    snapshot = Path(ledger['snapshot'])
    require(sha(snapshot / 'snapshot.json') == ledger['snapshot_sha256'], 'Snapshot drift')
    repo = integration.sealed(snapshot)
    _, _, _, simulation_image = integration.framework(repo)
    require(simulation_image(Path(ledger['simv'])) == ledger['files'], 'Image content drift')
    programs = read(DATA / 'soc01/programs.json')
    require(programs['backend'] == 'vcs-soc' and list(programs['programs']) == NAMES, 'Wrong8 membership')
    prepared = Path(programs['prepared'])
    provenance = integration.check(prepared)
    require(sha(prepared / 'provenance.json') == programs['provenance_sha256'], 'Provenance drift')
    host = read(DATA / 'host_semantics.json')
    require(host['status'] == 'PASS_8_EXACT_TUPLES' and
            [x['name'] for x in host['results']] == NAMES and
            host['generator_sha256'] == sha(HERE / 'prepare_successor.py'), 'Host semantics not PASS')
    tested = read(DATA / 'checker_host.json')
    require(tested['status'] == 'PASS' and tested['worker_sha256'] == sha(Path(__file__)) and
            tested['checker_sha256'] == sha(HERE / 'check_successor.py') and
            tested['test_sha256'] == sha(HERE / 'test_successor.py'), 'Checker tests stale/not PASS')
    reference = read(DATA / 'reference01/reference.json')
    require(reference['status'] == 'SPIKE_8_PASS_NOT_DUT' and
            [x['name'] for x in reference['results']] == NAMES and
            all(x['returncode'] == 0 and x['status'] == 'PASS' and x['full_oracle_markers']
                for x in reference['results']), 'Missing full Spike8 oracle')
    pins = read(DATA / 'baseline_pins.json')
    require(sha(DATA / 'baseline_pins.json') == provenance['baseline_pins_sha256'], 'Old pin anchor drift')
    pins.update(ledger['files'])
    pins.update({str(repo / n): h for n,h in read(snapshot / 'snapshot.json')['files'].items()})
    pins.update({str(prepared / n): h for n,h in provenance['files'].items()})
    pins.update({entry['path']:entry['sha256'] for entry in programs['programs'].values()})
    for directory in (DATA / 'reference01', DATA / 'source_diffs', DATA / 'spike01'):
        for file in directory.rglob('*'):
            if file.is_file():
                pins[str(file)] = sha(file)
    for file in (Path(__file__), HERE / 'check_successor.py', HERE / 'test_successor.py',
                 HERE / 'prepare_successor.py', HERE / 'TIMEOUT_TRIAGE.md',
                 DATA / 'baseline_pins.json', DATA / 'host_semantics.json', DATA / 'checker_host.json',
                 DATA / 'soc01/programs.json', prepared / 'provenance.json',
                 INTEGRATION / 'run.py', INTEGRATION / 'prepare.py',
                 IMAGE / 'image.json', snapshot / 'snapshot.json',
                 Path(ledger['simv']).parent / 'simulator.conf',
                 Path(ledger['simv']).parent / 'vcs_source_manifest.json'):
        pins[str(file)] = sha(file)
    pins_check(pins)
    gate = resources()
    require(gate['passed'], 'Resource/Tesla admission blocked; no launch')
    OUT.mkdir()
    save(OUT / 'resource_gate.json', gate)
    plan = dict(names=NAMES, image=str(IMAGE), image_sha256=IMAGE_SHA,
        programs=str(DATA / 'soc01'), pins=pins, jobs=2, timeout_per_case_s=300,
        retries=0, unit=UNIT, stages=[dict(name='control', cases=NAMES[:1], jobs=1),
        dict(name='remaining7', cases=NAMES[1:], jobs=2)], stop_first_failure=True,
        scope='Eight exact source-tuple successors only; not Linux ELF/parent matrices/83/board closure')
    save(OUT / 'plan.json', plan)
    service = ['systemd-run', '--user', '--unit='+UNIT, '--collect',
        '--property=RuntimeMaxSec=1800', '--property=TimeoutStopSec=120',
        '--property=KillMode=control-group', '--property=Restart=no',
        '--property=WorkingDirectory='+str(ROOT),
        '--property=StandardOutput=append:'+str(OUT / 'service.log'),
        '--property=StandardError=append:'+str(OUT / 'service.log'),
        sys.executable, '-B', str(Path(__file__).resolve()), '--worker', sha(OUT / 'plan.json')]
    save(OUT / 'service_command.json', service)
    result = subprocess.run(service, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
    save(OUT / 'launch.json', dict(returncode=result.returncode, output=result.stdout, time=time.time()))
    print(result.stdout, 'OUT='+str(OUT), 'ADMISSION='+str(gate['total_live_reserved'])+'/24',
          'MEM_GIB='+str(round(gate['available_bytes']/1024**3, 2)), flush=True)
    return result.returncode


def sample(pid, argv):
    proc = Path('/proc') / str(pid)
    stat = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
    trace = Path(next(a.split('=', 1)[1] for a in argv if a.startswith('+COMMIT_TRACE=')))
    size, cycle = 0, 0
    if trace.exists():
        with trace.open('rb') as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size-65536))
            tail = stream.read()
        tail = tail[:tail.rfind(b'\n')]
        for line in reversed(tail.splitlines()):
            first = line.split(b',', 1)[0]
            if first.isdigit():
                cycle = int(first)
                break
    return dict(pid=pid, cpu_ticks=int(stat[11])+int(stat[12]),
        executable=str((proc / 'exe').resolve()), cgroup=(proc / 'cgroup').read_text(),
        cwd=str((proc / 'cwd').resolve()), argv=argv, trace_bytes=size, last_cycle=cycle)


def confirm_startup(stage):
    destination = OUT / stage['name'] / 'actual_simv_confirmation.json'
    try:
        prefix = str(OUT / stage['name'])+'/'
        simv = read(IMAGE / 'image.json')['simv']
        deadline = time.monotonic()+30
        processes = []
        while time.monotonic() < deadline:
            processes = []
            for proc in Path('/proc').glob('[0-9]*'):
                try:
                    args = [s.decode() for s in (proc / 'cmdline').read_bytes().split(b'\0') if s]
                    if args and args[0] == simv and any(prefix in s for s in args):
                        processes.append((int(proc.name), args))
                except (OSError, UnicodeError):
                    continue
            if len(processes) == stage['jobs']:
                break
            time.sleep(0.5)
        require(len(processes) == stage['jobs'], 'Real simv startup count not confirmed')
        before = [sample(pid, args) for pid,args in processes]
        time.sleep(3)
        after = [sample(pid, args) for pid,args in processes]
        require(all(b['cpu_ticks'] > a['cpu_ticks'] and b['trace_bytes'] > a['trace_bytes'] and
                    b['last_cycle'] > a['last_cycle'] and UNIT in b['cgroup'] and
                    UNIT in a['cgroup'] and b['executable'] == simv
                    for a,b in zip(before,after)), 'Real simv advancement not confirmed')
        save(destination, dict(status='ADVANCING_'+str(stage['jobs'])+'_SIMV',
             samples=[before,after], completion_polling=False, finished=time.time()))
    except Exception as error:
        save(destination, dict(status='NOT_CONFIRMED', reason=str(error), finished=time.time()))


def worker(plan_hash):
    require(sha(OUT / 'plan.json') == plan_hash, 'Plan drift')
    plan = read(OUT / 'plan.json')
    pins_check(plan['pins'])
    (OUT / 'admission').mkdir()
    save(OUT / 'worker.json', dict(pid=os.getpid(), started=time.time(), plan_sha256=plan_hash))
    framework = integration.framework
    lock = threading.Lock()
    def admitted(repo):
        base, options, case, image = framework(repo)
        class Runner(base):
            def _run_test(self, test, simv):
                if not self.cancel_event.is_set():
                    with lock:
                        gate = resources()
                        save(OUT / 'admission' / (test.name+'.json'), gate)
                        require(gate['passed'], 'Per-case resource/Tesla admission blocked')
                return super()._run_test(test, simv)
        return Runner, options, case, image
    integration.framework = admitted
    integration.oracle_complete = oracle
    integration.framework(Path(read(IMAGE / 'image.json')['snapshot']) / 'sources')
    import ara_verify.runner as engine
    engine.FAIL_RE = re.compile(engine.FAIL_RE.pattern+'|'+old.FAIL.pattern, re.I | re.M)
    env = integration.environment()
    os.environ.clear()
    os.environ.update(env)
    rc, error = 1, None
    try:
        for stage in plan['stages']:
            pins_check(plan['pins'])
            folder = OUT / stage['name']
            folder.mkdir()
            command = [sys.executable, '-B', str(INTEGRATION / 'run.py'), 'run',
                '--image', str(IMAGE), '--programs', plan['programs'], '--out', str(folder / 'replay'),
                '--jobs', str(stage['jobs']), '--timeout', '300', '--execute']
            for name in stage['cases']:
                command += ['--case', name]
            save(folder / 'runner_command.json', command)
            confirmation = threading.Thread(target=confirm_startup, args=(stage,))
            confirmation.start()
            with (folder / 'runner.log').open('x') as stream:
                stdout, stderr = sys.stdout, sys.stderr
                sys.stdout = sys.stderr = stream
                try:
                    rc = integration.run_programs(SimpleNamespace(image=IMAGE, programs=Path(plan['programs']),
                        out=folder / 'replay', case=stage['cases'], jobs=stage['jobs'], timeout=300, execute=True))
                finally:
                    sys.stdout, sys.stderr = stdout, stderr
            confirmation.join()
            checker = subprocess.run([sys.executable, '-B', str(HERE / 'check_successor.py'),
                '--out', str(OUT), '--plan-sha256', plan_hash, '--stage', stage['name']],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
            (folder / 'checker.log').write_text(checker.stdout)
            print(stage['name'], 'runner_rc='+str(rc), checker.stdout, flush=True)
            if rc or checker.returncode:
                rc = rc or checker.returncode
                break
            require(read(folder / 'actual_simv_confirmation.json')['status'] ==
                    'ADVANCING_'+str(stage['jobs'])+'_SIMV', 'Startup confirmation missing')
    except Exception as caught:
        rc, error = 1, repr(caught)
    save(OUT / 'worker_exit.json', dict(runner_returncode=rc, error=error,
        plan_sha256=plan_hash, finished=time.time(), retries=0))
    checker = subprocess.run([sys.executable, '-B', str(HERE / 'check_successor.py'),
        '--out', str(OUT), '--plan-sha256', plan_hash], stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, timeout=120)
    (OUT / 'checker.log').write_text(checker.stdout)
    print(checker.stdout, flush=True)
    return checker.returncode


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--launch', action='store_true')
    mode.add_argument('--worker')
    args = parser.parse_args()
    raise SystemExit(worker(args.worker) if args.worker else launch())
