#!/usr/bin/env python3
"""One authorized eight-single replay, existing image/runner, no retries/builds."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
from prepare_batch import HERE, ROOT, INTEGRATION, SELECTED, sha, save
sys.path.insert(0, str(INTEGRATION))
import run as integration

OUT = HERE / 'vcs_candidate03_01'
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate03/campaign/image')
UNIT = 'ara-gather-original8-candidate03.service'
NAMES = ['gather_' + s for s in SELECTED]
FAIL = re.compile(
    r'RVV_PERMUTE_(?:FAIL|CAPACITY_FAIL|DETAIL)\b|BOARD_CASE_FAIL\b|'
    r'BOARD_REPLAY_[A-Z_]*(?:FAIL|TRAP|MISMATCH)\b|\bSKIP\b|'
    r'Core Test \*\*\* FAILED \*\*\*|\bUVM_FATAL\b(?![ \t]*:[ \t]*0\b)|'
    r'\$fatal\b|\bFatal\s*:|(?:Error|Fatal)[^\n]*(?:assertion|assert)[^\n]*fail|'
    r'^\s*(?:Index\s+\d+\s+)?(?:FAIL(?:ED|URE)?|FATAL)\b', re.I | re.M)


def read(path):
    return json.loads(Path(path).read_text())


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def pins_check(pins):
    for path, digest in pins.items():
        require(sha(Path(path)) == digest, 'Input drift: ' + path)


def resources():
    live, tesla_workers = [], []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args = [s.decode(errors='replace') for s in (proc / 'cmdline').read_bytes().split(b'\0') if s]
            if not args:
                continue
            if Path(args[0]).name == 'simv':
                live.append(dict(pid=int(proc.name), argv=args, cwd=str((proc / 'cwd').resolve())))
            if Path(args[0]).name.startswith('python') and any(
                '/comparison_alias_original/' in s and s.endswith('.py') for s in args[1:]):
                tesla_workers.append(dict(pid=int(proc.name), argv=args))
        except (OSError, ProcessLookupError):
            continue
    external = [p for p in live if not any(str(OUT) in s for s in p['argv'])]
    reserved = {}
    for name, token, slots in (('nf7', '/indexed_review/', 2),
                               ('tesla_comparison', '/comparison_alias_original/', 2),
                               ('mask_alias', '/mask_alias_original/', 1)):
        observed = sum(any(token in s for s in p['argv']) for p in external)
        reserved[name] = dict(slots=slots, observed_live=observed, unoccupied=max(0, slots-observed))
    mem = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    available = int(mem['MemAvailable'].split()[0]) * 1024
    total = len(external) + sum(r['unoccupied'] for r in reserved.values()) + 2
    return dict(time=time.time(), live=live, external_simv=len(external), own_slots=2,
                reservations=reserved, total_live_reserved=total, cap=24,
                available_bytes=available, min_available_bytes=32*1024**3,
                tesla_workers=tesla_workers, passed=total <= 24 and available >= 32*1024**3)


def oracle(entry, text):
    if FAIL.search(text):
        return False
    lines = text.splitlines()
    return all(lines.count(marker) == 1 for marker in entry['pass_markers'])


def launch():
    require(not OUT.exists(), 'Output collision; no retry')
    state = subprocess.check_output(['systemctl', '--user', 'show', UNIT, '-p', 'LoadState'], text=True)
    require('LoadState=not-found' in state, 'Service collision')
    require(sha(IMAGE / 'image.json') == 'e2c32c314ca85042e49517476d36c93d0d1f8a9c8eae75d86602cef1de476cb6', 'Wrong candidate03 image')
    ledger = read(IMAGE / 'image.json')
    snapshot_path = Path(ledger['snapshot']) / 'snapshot.json'
    require(sha(snapshot_path) == ledger['snapshot_sha256'], 'Snapshot ledger drift')
    repo = integration.sealed(snapshot_path.parent)
    snapshot = read(snapshot_path)
    _, _, _, simulation_image = integration.framework(repo)
    require(simulation_image(Path(ledger['simv'])) == ledger['files'], 'Image content drift')
    programs = read(HERE / 'soc01/programs.json')
    require(programs['backend'] == 'vcs-soc' and list(programs['programs']) == NAMES, 'Wrong8 membership/backend')
    prepared = Path(programs['prepared'])
    provenance = integration.check(prepared)
    require(sha(prepared / 'provenance.json') == programs['provenance_sha256'], 'Source ledger drift')
    require(read(OUT.parent / 'checker_host.json')['status'] == 'PASS', 'Checker host tests not PASS')
    reference = read(HERE / 'reference01/reference.json')['results']
    require([r['name'] for r in reference] == NAMES and all(r['returncode'] == 0 and r['status'] == 'PASS' for r in reference), 'Missing8 reference exits')
    pins = dict(ledger['files'])
    pins.update({str(repo / n): h for n, h in snapshot['files'].items()})
    pins.update({str(prepared / n): h for n, h in provenance['files'].items()})
    pins.update({r['path']: r['sha256'] for r in programs['programs'].values()})
    for path in (Path(__file__), HERE / 'check_terminal.py', HERE / 'test_terminal.py',
                 HERE / 'checker_host.json', INTEGRATION / 'run.py', INTEGRATION / 'prepare.py',
                 HERE / 'soc01/programs.json', prepared / 'provenance.json',
                 HERE / 'inventory83.json', HERE / 'lineage83.json', HERE / 'reference01/reference.json',
                 IMAGE / 'image.json', snapshot_path, Path(ledger['simv']).parent / 'simulator.conf',
                 Path(ledger['simv']).parent / 'vcs_source_manifest.json'):
        pins[str(path)] = sha(path)
    pins_check(pins)
    gate = resources()
    require(not gate['tesla_workers'] and gate['reservations']['tesla_comparison']['observed_live'] == 0,
            'Tesla comparison still active; no concurrent launch/retry')
    OUT.mkdir()
    save(OUT / 'resource_gate.json', gate)
    if not gate['passed']:
        save(OUT / 'complete.json', dict(status='CAPACITY_BLOCKED_NO_LAUNCH', retries=0))
        print(json.dumps(gate, indent=2))
        return 2
    command = [sys.executable, '-B', str(INTEGRATION / 'run.py'), 'run', '--image', str(IMAGE),
               '--programs', str(HERE / 'soc01'), '--out', str(OUT / 'replay'),
               '--jobs', '2', '--timeout', '300', '--execute']
    for name in NAMES:
        command += ['--case', name]
    plan = dict(names=NAMES, image=str(IMAGE), programs=str(HERE / 'soc01'), pins=pins,
                jobs=2, timeout_per_case_s=300, unit=UNIT, retries=0, runner_command=command,
                scope='Eight original-source single trials only; not83 or Linux/board closure')
    save(OUT / 'plan.json', plan)
    service = ['systemd-run', '--user', '--unit=' + UNIT, '--collect',
               '--property=RuntimeMaxSec=1800', '--property=TimeoutStopSec=120',
               '--property=KillMode=control-group', '--property=Restart=no',
               '--property=WorkingDirectory=' + str(ROOT),
               '--property=StandardOutput=append:' + str(OUT / 'service.log'),
               '--property=StandardError=append:' + str(OUT / 'service.log'),
               sys.executable, '-B', str(Path(__file__).resolve()), '--worker', sha(OUT / 'plan.json')]
    save(OUT / 'service_command.json', service)
    result = subprocess.run(service, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
    save(OUT / 'launch.json', dict(returncode=result.returncode, output=result.stdout,
                                 time=time.time(), plan_sha256=sha(OUT / 'plan.json')))
    print(json.dumps(dict(output=result.stdout, returncode=result.returncode, out=str(OUT),
                         live=gate['external_simv'], total_reserved=gate['total_live_reserved'],
                         available_gib=gate['available_bytes']/1024**3), indent=2))
    return result.returncode


def worker(plan_hash):
    require(sha(OUT / 'plan.json') == plan_hash, 'Plan drift')
    plan = read(OUT / 'plan.json')
    pins_check(plan['pins'])
    (OUT / 'admission').mkdir()
    save(OUT / 'worker.json', dict(pid=os.getpid(), start=time.time(), plan_sha256=plan_hash))
    shared_framework = integration.framework
    lock = threading.Lock()

    def admitted_framework(repo):
        base, options, case, image = shared_framework(repo)
        class Admitted(base):
            def _run_test(self, test, simv):
                if not self.cancel_event.is_set():
                    with lock:
                        gate = resources()
                        save(OUT / 'admission' / (test.name + '.json'), gate)
                        require(gate['passed'], 'Per-case resource gate failed; no retry')
                return super()._run_test(test, simv)
        return Admitted, options, case, image

    integration.framework = admitted_framework
    integration.oracle_complete = oracle
    integration.framework(Path(read(IMAGE / 'image.json')['snapshot']) / 'sources')
    import ara_verify.runner as engine
    engine.FAIL_RE = re.compile(engine.FAIL_RE.pattern + '|' + FAIL.pattern, re.I | re.M)
    args = integration.parse_args(plan['runner_command'][3:])
    env = integration.environment()
    os.environ.clear()
    os.environ.update(env)
    rc = 1
    error = None
    try:
        with (OUT / 'runner.log').open('x') as log:
            saved_stdout, saved_stderr = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = log
            try:
                rc = integration.run_programs(args)
            finally:
                sys.stdout, sys.stderr = saved_stdout, saved_stderr
    except Exception as caught:
        error = repr(caught)
    save(OUT / 'worker_exit.json', dict(runner_returncode=rc, error=error,
                                      plan_sha256=plan_hash, finished=time.time(), retries=0))
    checker = subprocess.run([sys.executable, '-B', str(HERE / 'check_terminal.py'),
                              '--out', str(OUT), '--plan-sha256', plan_hash],
                             text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
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
