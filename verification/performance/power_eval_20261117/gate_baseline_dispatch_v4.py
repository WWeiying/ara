#!/usr/bin/env python3
"""Baseline scheduling successor: interoperate with sealed v3 RTL dispatchers.

Old failures and workers are untouched. Unknown dispatchers block NEW launches;
only a measured live-simulator excess, not a reservation/classification change,
can stop an already running owned GLS. Capture is not final power acceptance.
"""
import argparse
from contextlib import contextmanager
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import shlex
import shutil
import signal
import subprocess
import sys
import time
import types
import unittest

HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
BASE_SHA = 'ca79c2cd8c82f582568c7ec6553a0e43af198a501b645702319d4ff575a2b90e'
V3_SHA = '9bb3e37d9590261ab854cbdf934bbfec0c4bdb6ea56bc7e14ef43eb0bf3bd5ec'
V3_LOCK = OUT / '.power-vcs-slots-20261117.lock'
OLD_LOCK = OUT / '.power_gls_20261117_slots.lock'
SOURCES = dict(smoke=OUT / 'power_gls_20261117_baseline_q8_smoke_01',
               capture=OUT / 'power_gls_20261117_baseline_q8_capture_02')
OUTPUTS = dict(smoke=OUT / 'power_gls_20261117_baseline_q8_smoke_02',
               capture=OUT / 'power_gls_20261117_baseline_q8_capture_03')
path = HERE / 'gate_run_baseline.py'
if hashlib.sha256(path.read_bytes()).hexdigest() != BASE_SHA:
    raise ValueError('Sealed baseline adapter drift')
base = types.ModuleType('baseline_dispatch_v4_sealed_adapter')
base.__file__ = str(path)
sys.modules[base.__name__] = base
exec(compile(path.read_text(), str(path), 'exec'), base.__dict__)
g = base.g
require, sha, read, save, verify = g.require, g.sha, g.read, g.save, g.verify


def live_ids(rows, own=None):
    return {pid for pid, (_, argv) in rows.items() if pid != own and Path(argv[0]).name == 'simv'}


def v3_reservation(pid, worker, output, rows):
    require(output.parent == OUT and worker == output / 'inputs/precheck_power_v3.py', 'Unknown v3 path')
    pins = read(output / 'source-pins.json')
    require(pins.get(str(worker)) == V3_SHA == sha(worker), 'Unknown v3 worker bytes')
    for name, expected in g.KNOWN_DISPATCHERS.items():
        helper = output / 'inputs' / name
        require(pins.get(str(helper)) == expected == sha(helper), 'v3 helper drift')
    plan_path = output / 'plan.json'
    require(pins.get(str(plan_path)) == sha(plan_path), 'Unpinned v3 plan')
    plan = read(plan_path)
    require(plan['parallel'] == 1 and len(plan['cases']) == 1 and plan['max_global_simv'] == 4
            and plan['slot_lock'] == str(V3_LOCK) and plan['success_state'] == 'POWER_ELIGIBLE'
            and read(output / 'attempt.json')['pid'] == pid, 'Unknown v3 dispatch contract')
    case = plan['cases'][0]
    work = output / 'runs' / case['id']
    children = [child for child in live_ids(rows) if rows[child][0] == pid]
    require(len(children) <= 1, 'v3 launched more than its single case')
    if children:
        argv = rows[children[0]][1]
        require(argv[0] == str(Path(plan['image']) / 'sim/simv')
                and argv.count('+TESTCASE=' + case['id']) == 1
                and argv.count('+PRELOAD=' + case['elf']) == 1, 'v3 live child identity mismatch')
        return 0  # Its actual simulator remains in the common process inventory.
    if (work / 'result.json').exists():
        require(read(work / 'result.json')['state'] in ('POWER_ELIGIBLE', 'FAIL', 'TIMEOUT'), 'Unknown v3 terminal state')
        return 0
    if (work / 'status.json').exists():
        require(read(work / 'status.json')['state'] in ('ELIGIBILITY', 'PROTOCOL'), 'Unknown v3 checker stage')
        return 0  # A one-shot v3 checker cannot reenter VCS.
    if (work / 'dispatch.json').exists():
        return 1  # Popen/exec/exit publication gap, or the strict-checker handoff.
    status = read(output / 'status.json')
    require(status['state'] in ('PREPARED_POWER_ELIGIBILITY', 'WAITING_FOR_VCS_SLOT'), 'Unknown v3 launch state')
    return 0  # A waiting v3 must acquire the SAME lock before launching.


def capacity(rows, own=None):
    filtered = dict(rows)
    handoff, errors = 0, []
    for pid, (_, argv) in rows.items():
        workers = [Path(a) for a in argv if Path(a).name == 'precheck_power_v3.py']
        if 'execute' not in argv or not workers:
            continue
        try:
            require(len(workers) == 1 and argv.count('--output') == 1, 'Ambiguous v3 dispatcher')
            output = Path(argv[argv.index('--output') + 1])
            handoff += v3_reservation(pid, workers[0], output, rows)
            del filtered[pid]  # Only the verified parent is removed, never its VCS child.
        except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
            errors.append(repr(error))
    reserved = g.reserved_slots(filtered, own_child=own) + handoff
    return dict(actual_other_simv=len(live_ids(rows, own)), reserved_other_slots=reserved,
                launch_allowed=not errors and reserved < 4, scheduler_errors=errors)


def running_capacity_ok(snapshot):
    return snapshot['actual_other_simv'] + 1 <= 4


@contextmanager
def slot_lock():
    # Fixed ordering interoperates with both already sealed launcher families.
    with OLD_LOCK.open('a') as old, V3_LOCK.open('a') as canonical:
        fcntl.flock(old, fcntl.LOCK_EX)
        fcntl.flock(canonical, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(canonical, fcntl.LOCK_UN)
            fcntl.flock(old, fcntl.LOCK_UN)


def run_simulator(out, plan):
    work = out / 'run'
    console, vcd = work / 'console.log', work / 'window.vcd'
    require(not console.exists() and not vcd.exists(), 'Fresh run artifacts required')
    waiting, proc = time.monotonic(), None
    while proc is None:
        with slot_lock():
            snapshot = capacity(g.process_snapshot())
            if snapshot['launch_allowed']:
                verify(read(out / 'source-pins.json'))
                verify(read(out / 'image-pins.json'))
                started_ns = time.time_ns()
                def limits():
                    limit = max(plan['max_vcd_bytes'], plan['max_log_bytes'])
                    resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))
                with console.open('x') as stream:
                    proc = subprocess.Popen(plan['command'], cwd=work,
                        env=dict(read(out / 'inputs/rtl-plan.json')['environment'], PYTHONDONTWRITEBYTECODE='1'),
                        stdout=stream, stderr=subprocess.STDOUT, start_new_session=True, preexec_fn=limits)
                save(out / 'dispatch.json', dict(pid=proc.pid, owner_pid=os.getpid(),
                    command=plan['command'], started_ns=started_ns, capacity=snapshot), True)
        if proc is None:
            require(time.monotonic() - waiting < plan['slot_seconds'], 'Finite slot wait expired')
            save(out / 'status.json', dict(state='WAITING_FOR_SHARED_SIMULATOR_SLOT', pid=os.getpid(), **snapshot))
            time.sleep(5)
    started, last_status = time.monotonic(), 0
    try:
        while proc.poll() is None:
            elapsed = time.monotonic() - started
            require(elapsed < plan['wall_seconds'], 'Finite GLS wall watchdog expired')
            require(not vcd.exists() or vcd.stat().st_size <= plan['max_vcd_bytes'], 'VCD byte budget exceeded')
            require(all(not p.exists() or p.stat().st_size <= plan['max_log_bytes']
                        for p in (console, work / 'run.vcs.log')), 'Log byte budget exceeded')
            snapshot = capacity(g.process_snapshot(), own=proc.pid)
            require(running_capacity_ok(snapshot), 'REAL_SIMV_OVERSUBSCRIPTION: stopping only owned GLS')
            if elapsed - last_status >= 15 or last_status == 0:
                status = dict(state='GLS_RUNNING', child_pid=proc.pid, owner_pid=os.getpid(),
                    elapsed_seconds=elapsed, child_cpu_seconds=g.cpu_seconds(proc.pid),
                    vcd_bytes=vcd.stat().st_size if vcd.exists() else 0,
                    **snapshot, **g.last_progress(console))
                save(out / 'status.json', status)
                with (out / 'progress.jsonl').open('a') as stream:
                    stream.write(json.dumps(status) + '\n')
                last_status = elapsed
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        return dict(returncode=proc.returncode, started_ns=started_ns, finished_ns=time.time_ns(),
                    elapsed_seconds=time.monotonic() - started, slot_wait_seconds=started - waiting,
                    **g.last_progress(console))
    finally:
        g.stop_process(proc)


def prepare(mode):
    source, out = SOURCES[mode], OUTPUTS[mode]
    require(not out.exists(), 'Fresh scheduling successor required')
    pins = read(source / 'source-pins.json')
    verify(pins)
    original = read(source / 'plan.json')
    _, binding = base.check_binding(source, sha(source / 'plan.json'), sha(source / 'image-binding.json'))
    out.mkdir()
    (out / 'inputs').mkdir()
    (out / 'run').mkdir()
    new_pins = {}
    for name, expected in pins.items():
        path = Path(name)
        if path.is_relative_to(source):
            if path == source / 'plan.json':
                continue
            dest = out / path.relative_to(source)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
            require(sha(dest) == expected, 'Frozen input copy mismatch')
            new_pins[str(dest)] = expected
        else:
            new_pins[name] = expected
    worker = out / 'inputs/gate_baseline_dispatch_v4.py'
    shutil.copyfile(__file__, worker)
    new_pins[str(worker)] = sha(worker)
    new_pins[str(Path(__file__).resolve())] = sha(__file__)
    for path in (source / 'plan.json', source / 'source-pins.json', source / 'result.json'):
        new_pins[str(path)] = sha(path)
    plan = copy.deepcopy(original)
    plan['command'] = [arg.replace(str(source), str(out)) for arg in original['command']]
    plan['cwd'] = str(out / 'run')
    plan['elf_map']['gls'] = str(out / 'inputs/program.elf')
    plan.update(scheduler='dual-lock-v3-interop-v4', capture_requires_smoke_pass=False,
                power_release_requires_smoke_pass=True, smoke_prerequisite_phase='FINAL_POWER_PUBLICATION_ONLY',
                smoke_prerequisite=str(OUTPUTS['smoke']) if mode == 'capture' else None,
                predecessor=dict(path=str(source), failure_preserved=True))
    save(out / 'plan.json', plan, True)
    new_pins[str(out / 'plan.json')] = sha(out / 'plan.json')
    save(out / 'source-pins.json', new_pins, True)
    binding = copy.deepcopy(binding)
    binding.update(plan_sha256=sha(out / 'plan.json'), source_pins_sha256=sha(out / 'source-pins.json'))
    save(out / 'image-pins.json', binding['image_pins'], True)
    save(out / 'image-binding.json', binding, True)
    verify(new_pins)
    unit = out.name.replace('_', '-') + '.service'
    command = ['/usr/bin/python3', '-B', str(worker), 'execute', '--mode', mode,
        '--plan-sha256', binding['plan_sha256'], '--binding-sha256', sha(out / 'image-binding.json'),
        '--authorize-run', '--acknowledge-reconstruction']
    service = ['/usr/bin/systemd-run', '--user', '--unit=' + unit, '--property=Type=exec',
        '--property=KillMode=control-group', '--property=RuntimeMaxSec=' + str(plan['wall_seconds'] + plan['slot_seconds'] + 1800),
        '--property=TimeoutStopSec=30', '--property=StandardOutput=append:' + str(out / 'service.stdout.log'),
        '--property=StandardError=append:' + str(out / 'service.stderr.log'), *command]
    save(out / 'ready-command.json', dict(service=service, shell=shlex.join(service), unit=unit, launched=False), True)
    save(out / 'status.json', dict(state='IMAGE_BOUND_NOT_LAUNCHED', jobs_launched=0))
    print(json.dumps(dict(state='IMAGE_BOUND_NOT_LAUNCHED', output=str(out))))


def execute(a):
    out = OUTPUTS[a.mode]
    require(a.authorize_run and a.acknowledge_reconstruction, 'Explicit run/reconstruction authorization required')
    require(Path(__file__).resolve() == out / 'inputs/gate_baseline_dispatch_v4.py', 'Use frozen worker')
    require(not (out / 'attempt.json').exists(), 'No retry or overwrite')
    unit = out.name.replace('_', '-') + '.service'
    group = Path('/proc/self/cgroup').read_text()
    owner = subprocess.check_output(['/usr/bin/systemctl', '--user', 'show', unit, '-p', 'MainPID', '--value'], text=True).strip()
    require('/' + unit in group and owner == str(os.getpid()), 'Direct independent service ownership required')
    plan, binding = base.check_binding(out, a.plan_sha256, a.binding_sha256)
    save(out / 'attempt.json', dict(pid=os.getpid(), cgroup=group, started_ns=time.time_ns(),
        plan_sha256=a.plan_sha256, binding_sha256=a.binding_sha256), True)
    def interrupted(signum, frame):
        raise InterruptedError('Owned GLS interrupted: ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        run = run_simulator(out, plan)
        report = g.final_check(out, plan, binding, run)
        base.check_binding(out, a.plan_sha256, a.binding_sha256)
        report.update(baseline_context=plan['baseline_context'], historical_byte_identity='UNPROVEN',
                      configuration=plan['configuration'], power_release_requires_smoke_pass=True,
                      matching_smoke=str(OUTPUTS['smoke']), power_acceptance=False,
                      power_publishable=False, scheduler='dual-lock-v3-interop-v4')
    except BaseException as error:
        report = dict(state='FAIL', mode=a.mode, case_id=base.Q8, full_gate_task_pass=False,
                      power_publishable=False, error=repr(error), artifacts_preserved=True)
    save(out / 'result.json', report, True)
    save(out / 'status.json', dict(state=report['state'], completed=True, child_pid=None))
    print(json.dumps({k: report[k] for k in ('state', 'case_id', 'full_gate_task_pass')}))
    return int(report['state'] == 'FAIL')


class HostTests(unittest.TestCase):
    def test_verified_live_v3_does_not_masquerade_as_full(self):
        from unittest.mock import patch
        worker = OUT / 'power_precheck_20261117_m4_compact_native_v3_01/inputs/precheck_power_v3.py'
        rows = {10: (1, ['python3', str(worker), 'execute', '--output', str(worker.parent.parent)]),
                11: (10, ['/x/simv']), 12: (1, ['/x/simv']), 13: (1, ['/x/simv'])}
        with patch(__name__ + '.v3_reservation', return_value=0):
            snap = capacity(rows)
        self.assertEqual(snap['reserved_other_slots'], 3)
        self.assertTrue(snap['launch_allowed'])
        self.assertTrue(running_capacity_ok(snap))

    def test_unknown_blocks_launch_not_running_gls(self):
        rows = {1: (0, ['python3', '/x/inputs/precheck_unknown.py', 'execute', '--output', '/x']),
                2: (0, ['/x/simv']), 3: (0, ['/x/simv']), 4: (0, ['/x/simv'])}
        snap = capacity(rows)
        self.assertFalse(snap['launch_allowed'])
        self.assertTrue(running_capacity_ok(snap))
        self.assertFalse(running_capacity_ok(dict(actual_other_simv=4)))

    def test_real_v3_identity(self):
        rows = g.process_snapshot()
        for pid, (_, argv) in rows.items():
            worker = [Path(a) for a in argv if Path(a).name == 'precheck_power_v3.py']
            if 'execute' in argv and worker:
                self.assertIn(v3_reservation(pid, worker[0], Path(argv[argv.index('--output') + 1]), rows), (0, 1))
        self.assertEqual(g.MAX_SLOTS, 4)
        self.assertEqual(g.GATE.name, 'power_gate_build_20261117_all_on_01')


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('action', choices=('prepare', 'execute', 'self-test'))
    p.add_argument('--mode', choices=('smoke', 'capture'), default='smoke')
    p.add_argument('--plan-sha256')
    p.add_argument('--binding-sha256')
    p.add_argument('--authorize-run', action='store_true')
    p.add_argument('--acknowledge-reconstruction', action='store_true')
    a = p.parse_args()
    if a.action == 'execute':
        return execute(a)
    require(not a.authorize_run, 'Authorization only applies to execute')
    if a.action == 'self-test':
        return int(not unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(HostTests)).wasSuccessful())
    prepare(a.mode)
    return 0


if __name__ == '__main__':
    sys.exit(main())
