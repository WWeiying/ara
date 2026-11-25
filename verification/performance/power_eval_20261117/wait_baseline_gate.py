#!/usr/bin/env python3
"""Drain existing RTL dispatchers, then use the unchanged gate runner serially."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time
import unittest

OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
WORK = OUT / 'power_gls_20261117_baseline_q8_serial_wait_01'
UNIT = 'power-gls-20261117-baseline-q8-serial-wait-01.service'
KNOWN = [OUT / name for name in ('power_precheck_20261117_baseline_02',
         'power_precheck_20261117_m4_compact_native_v3_01', 'power_precheck_20261117_m4_compact_rvv_v3_01')]
TERMINAL = {'PASS', 'FAIL', 'TIMEOUT', 'INCOMPLETE', 'POWER_ELIGIBLE'}
PREFIX = 'power_gls_20261117_baseline_q8_'


def read(p):
    return json.loads(Path(p).read_text())


def save(name, data):
    path = WORK / name
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    tmp.replace(path)


def verify():
    for name, expected in read(WORK / 'source-pins.json').items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise ValueError('Frozen wait input drift: ' + name)


def dispatchers(proc=Path('/proc')):
    found = []
    for p in proc.iterdir():
        if not p.name.isdigit():
            continue
        try:
            argv = [x.decode() for x in (p / 'cmdline').read_bytes().split(b'\0') if x]
        except (OSError, UnicodeError):
            continue
        if 'execute' in argv and any(Path(a).name.startswith('precheck') and a.endswith('.py') for a in argv):
            if any(str(OUT / 'power_precheck_20261117_') in a for a in argv):
                found.append(dict(pid=int(p.name), command=argv))
        elif any(Path(a).name == 'after_compile.py' for a in argv) and any(str(OUT) in a for a in argv):
            found.append(dict(pid=int(p.name), command=argv))
    return found


def terminal_states():
    states = {}
    for directory in KNOWN:
        p = directory / 'result.json'
        states[str(directory)] = read(p).get('state') if p.exists() else None
    return states


def drained(states, live):
    return not live and all(state in TERMINAL for state in states.values())


def command(argv, label, timeout):
    verify()
    with (WORK / (label + '.log')).open('x') as stream:
        subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=timeout)


def prepare():
    if WORK.exists():
        raise ValueError('Fresh wait-chain output required')
    here = Path(__file__).resolve().parent
    expected = {
        'gate_run.py': 'e05b5a5b23a5ca3ade67aebd10843029b5e1012745210fb1d87678ae43f37f5d',
        'test_gate_run.py': '1fe0b3d78d3567ba70a017f0da0359f3850497e957a8398db660666d7ad7fd1c',
        'gate_run_baseline.py': 'ca79c2cd8c82f582568c7ec6553a0e43af198a501b645702319d4ff575a2b90e',
    }
    for name, digest in expected.items():
        if hashlib.sha256((here / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Sealed predecessor drift: ' + name)
    WORK.mkdir()
    (WORK / 'inputs').mkdir()
    for name in ('wait_baseline_gate.py', 'gate_run_baseline_serial.py', 'gate_run.py', 'test_gate_run.py'):
        shutil.copyfile(here / name, WORK / 'inputs' / name)
    shutil.copyfile(here / 'gate_run_baseline.py', WORK / 'inputs/gate_run_baseline_predecessor.py')
    (WORK / 'inputs/output-name-successor.diff').write_text(''.join(difflib.unified_diff(
        (here / 'gate_run_baseline.py').read_text().splitlines(True),
        (here / 'gate_run_baseline_serial.py').read_text().splitlines(True),
        fromfile='gate_run_baseline.py', tofile='gate_run_baseline_serial.py')))
    pins = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (WORK / 'inputs').iterdir() if p.is_file()}
    save('source-pins.json', pins)
    service = ['/usr/bin/systemd-run', '--user', '--unit=' + UNIT, '--property=Type=exec',
        '--property=KillMode=control-group', '--property=RuntimeMaxSec=64800',
        '--property=TimeoutStopSec=45', '--property=StandardOutput=append:' + str(WORK / 'service.stdout.log'),
        '--property=StandardError=append:' + str(WORK / 'service.stderr.log'),
        '/usr/bin/python3', '-B', str(WORK / 'inputs/wait_baseline_gate.py'), 'run']
    save('ready-command.json', dict(service=service, launched=False, unit=UNIT))
    save('status.json', dict(state='PREPARED_WAIT_FOR_RTL_DRAIN', jobs_launched=0,
                             known_tasks=list(map(str, KNOWN))))
    verify()
    print(json.dumps(dict(output=str(WORK), unit=UNIT, state='PREPARED_WAIT_FOR_RTL_DRAIN')))


def run():
    if Path(__file__).resolve() != WORK / 'inputs/wait_baseline_gate.py' or (WORK / 'attempt.json').exists():
        raise ValueError('Frozen one-shot waiter required')
    owner = subprocess.check_output(['systemctl', '--user', 'show', UNIT, '-p', 'MainPID', '--value'], text=True).strip()
    if owner != str(os.getpid()) or '/' + UNIT not in Path('/proc/self/cgroup').read_text():
        raise ValueError('Direct independent service ownership required')
    verify()
    save('attempt.json', dict(pid=os.getpid(), started=time.time()))
    active_unit = None
    def interrupted(signum, frame):
        raise InterruptedError('Wait chain interrupted: ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        deadline = time.monotonic() + 21600
        while True:
            live, states = dispatchers(), terminal_states()
            save('status.json', dict(state='WAITING_FOR_RTL_TERMINATION_AND_DISPATCHER_EXIT',
                pid=os.getpid(), dispatchers=live, terminal_states=states, jobs_launched=0))
            if drained(states, live):
                break
            if time.monotonic() >= deadline:
                raise TimeoutError('Finite six-hour RTL drain wait expired')
            time.sleep(30)
        worker = WORK / 'inputs/gate_run_baseline_serial.py'
        for mode, suffix in (('smoke', 'smoke_03'), ('capture', 'capture_04')):
            if dispatchers():
                raise ValueError('A new RTL dispatcher appeared; preserve evidence and do not launch GLS')
            directory = OUT / (PREFIX + suffix)
            argv = ['/usr/bin/python3', '-B', str(worker), 'prepare', '--output', str(directory),
                    '--mode', mode, '--acknowledge-reconstruction']
            if mode == 'capture':
                argv += ['--first-cycle', '62619', '--last-cycle', '65675']
            save('status.json', dict(state='PREPARING_' + mode.upper(), output=str(directory)))
            command(argv, 'prepare-' + mode, 900)
            frozen = directory / 'inputs/gate_run_baseline_serial.py'
            command(['/usr/bin/python3', '-B', str(frozen), 'bind-image', '--output', str(directory)],
                    'bind-' + mode, 900)
            if dispatchers():
                raise ValueError('RTL dispatcher reappeared before service launch')
            ready = read(directory / 'ready-command.json')
            active_unit = ready['unit']
            save('status.json', dict(state='EXECUTING_' + mode.upper(), output=str(directory), unit=active_unit))
            # systemd waits for the independent service; it directly owns its
            # frozen worker/VCS. Do not poll a multi-hour simulation here.
            service = list(ready['service'])
            service.insert(1, '--wait')
            command(service, 'service-' + mode, 21600)
            result = read(directory / 'result.json')
            expected = 'GATE_SMOKE_PASS' if mode == 'smoke' else 'CAPTURE_COMPLETE_NOT_TASK_PASS'
            if result['state'] != expected or (mode == 'smoke' and result['full_gate_task_pass'] is not True):
                raise ValueError('Serial ' + mode + ' acceptance failed')
            active_unit = None
        save('result.json', dict(state='SMOKE_AND_CAPTURE_COMPLETE_NOT_POWER_ACCEPTANCE',
             original_failures_modified=False, historical_byte_identity='UNPROVEN', power_acceptance=False))
        save('status.json', dict(state='COMPLETE'))
        return 0
    except BaseException as error:
        if active_unit:
            subprocess.run(['systemctl', '--user', 'stop', active_unit], check=False)
        save('result.json', dict(state='FAIL', error=repr(error), artifacts_preserved=True))
        save('status.json', dict(state='FAIL'))
        return 1


class HostTests(unittest.TestCase):
    def test_drain_gate(self):
        self.assertFalse(drained({'a': None}, []))
        self.assertFalse(drained({'a': 'PASS'}, [{'pid': 1}]))
        self.assertFalse(drained({'a': 'RUNNING'}, []))
        self.assertTrue(drained({'a': 'FAIL', 'b': 'POWER_ELIGIBLE'}, []))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'run', 'self-test'))
    args = parser.parse_args()
    if args.action == 'self-test':
        sys.exit(int(not unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(HostTests)).wasSuccessful()))
    if args.action == 'prepare':
        prepare()
        sys.exit(0)
    sys.exit(run())
