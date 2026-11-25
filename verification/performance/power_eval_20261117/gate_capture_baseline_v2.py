#!/usr/bin/env python3
"""Independent capture successor: smoke gates publication, not VCD collection.

The sealed baseline runner, its smoke, and capture_01 are preserved. Only an
authorized independent service may execute this bounded capture. No compilation,
conversion, numerical tolerance changes, or final power acceptance occurs here.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import types
import unittest

HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
SOURCE = OUT / 'power_gls_20261117_baseline_q8_capture_01'
DEFAULT = OUT / 'power_gls_20261117_baseline_q8_capture_02'
BASE_SHA = 'ca79c2cd8c82f582568c7ec6553a0e43af198a501b645702319d4ff575a2b90e'
SOURCE_PLAN_SHA = '12f3af6e607d89d29508ff24aa31c15d3466224f6068d5a454eceee133bb6c11'
base_path = HERE / 'gate_run_baseline.py'
if hashlib.sha256(base_path.read_bytes()).hexdigest() != BASE_SHA:
    raise ValueError('Sealed baseline adapter drift')
base = types.ModuleType('capture_v2_sealed_baseline_adapter')
base.__file__ = str(base_path)
sys.modules[base.__name__] = base
exec(compile(base_path.read_text(), str(base_path), 'exec'), base.__dict__)
g = base.g
require, sha, read, save, verify = g.require, g.sha, g.read, g.save, g.verify


def successor_plan(original):
    require(original['mode'] == 'capture' and original['case_id'] == base.Q8
            and original['image'] == str(base.GATE) and original['elf_map']['sha256'] == base.ELF_SHA,
            'Exact baseline Q8 capture predecessor required')
    plan = copy.deepcopy(original)
    plan['command'] = [arg.replace(str(SOURCE), str(DEFAULT)) for arg in original['command']]
    plan['cwd'] = str(DEFAULT / 'run')
    plan['elf_map']['gls'] = str(DEFAULT / 'inputs/program.elf')
    plan.update(schema='power-baseline-capture-successor-v2', capture_requires_smoke_pass=False,
                power_release_requires_smoke_pass=True, smoke_prerequisite_phase='FINAL_POWER_PUBLICATION_ONLY',
                predecessor_plan=dict(path=str(SOURCE / 'plan.json'), sha256=SOURCE_PLAN_SHA),
                capture_is_full_task_pass=False, power_acceptance=False)
    g.validate_limits('capture', plan['first_cycle'], plan['last_cycle'], plan['max_cycles'],
                      plan['wall_seconds'], plan['max_vcd_bytes'], plan['slot_seconds'])
    require((plan['first_cycle'], plan['last_cycle']) == (62619, 65675), 'Reviewed 3056-cycle window required')
    return plan


def prepare():
    require(not DEFAULT.exists(), 'Fresh successor output required')
    require(sha(SOURCE / 'plan.json') == SOURCE_PLAN_SHA, 'Predecessor plan drift')
    source_pins = read(SOURCE / 'source-pins.json')
    verify(source_pins)
    _, binding = base.check_binding(SOURCE, SOURCE_PLAN_SHA, sha(SOURCE / 'image-binding.json'))
    plan = successor_plan(read(SOURCE / 'plan.json'))
    DEFAULT.mkdir()
    (DEFAULT / 'inputs').mkdir()
    (DEFAULT / 'run').mkdir()
    pins = {}
    for name, expected in source_pins.items():
        path = Path(name)
        if path.is_relative_to(SOURCE):
            if path == SOURCE / 'plan.json':
                continue
            dest = DEFAULT / path.relative_to(SOURCE)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
            require(sha(dest) == expected, 'Predecessor copy drift')
            pins[str(dest)] = expected
        else:
            pins[name] = expected
    worker = DEFAULT / 'inputs/gate_capture_baseline_v2.py'
    shutil.copyfile(__file__, worker)
    pins[str(worker)] = sha(worker)
    pins[str(Path(__file__).resolve())] = sha(__file__)
    for path in (SOURCE / 'plan.json', SOURCE / 'source-pins.json', SOURCE / 'image-binding.json'):
        pins[str(path)] = sha(path)
    save(DEFAULT / 'plan.json', plan, True)
    pins[str(DEFAULT / 'plan.json')] = sha(DEFAULT / 'plan.json')
    save(DEFAULT / 'policy-successor.json', dict(
        predecessor=str(SOURCE), original_records_modified=False,
        change='Collect bounded VCD before smoke completion; matching smoke PASS still gates final power release',
        historical_byte_identity='UNPROVEN', numeric_tolerances_changed=False,
        first_cycle=62619, last_cycle=65675, cycles=3056,
        clock_offset='Verify gate clock phase against supplied RTL PC80000478 loop boundaries'), True)
    pins[str(DEFAULT / 'policy-successor.json')] = sha(DEFAULT / 'policy-successor.json')
    save(DEFAULT / 'source-pins.json', pins, True)
    new_binding = copy.deepcopy(binding)
    new_binding.update(schema='power-baseline-capture-binding-v2',
        plan_sha256=sha(DEFAULT / 'plan.json'), source_pins_sha256=sha(DEFAULT / 'source-pins.json'))
    save(DEFAULT / 'image-pins.json', binding['image_pins'], True)
    save(DEFAULT / 'image-binding.json', new_binding, True)
    verify(pins)
    unit = DEFAULT.name.replace('_', '-') + '.service'
    worker_command = ['/usr/bin/python3', '-B', str(worker), 'execute', '--output', str(DEFAULT),
        '--plan-sha256', new_binding['plan_sha256'], '--binding-sha256', sha(DEFAULT / 'image-binding.json'),
        '--authorize-run', '--acknowledge-reconstruction', '--allow-capture-before-smoke']
    command = ['/usr/bin/systemd-run', '--user', '--unit=' + unit, '--property=Type=exec',
        '--property=KillMode=control-group',
        '--property=RuntimeMaxSec=' + str(plan['wall_seconds'] + plan['slot_seconds'] + 1800),
        '--property=TimeoutStopSec=30',
        '--property=StandardOutput=append:' + str(DEFAULT / 'service.stdout.log'),
        '--property=StandardError=append:' + str(DEFAULT / 'service.stderr.log'), *worker_command]
    save(DEFAULT / 'ready-command.json', dict(service=command, shell=shlex.join(command), unit=unit,
        launched=False, capture_requires_smoke_pass=False, power_release_requires_smoke_pass=True), True)
    save(DEFAULT / 'status.json', dict(state='IMAGE_BOUND_NOT_LAUNCHED', jobs_launched=0))
    print(json.dumps(dict(state='IMAGE_BOUND_NOT_LAUNCHED', output=str(DEFAULT),
                         capture_requires_smoke_pass=False, power_release_requires_smoke_pass=True)))


def execute(a):
    require(a.authorize_run and a.acknowledge_reconstruction and a.allow_capture_before_smoke,
            'Explicit capture/reconstruction/policy authorization required')
    require(Path(__file__).resolve() == DEFAULT / 'inputs/gate_capture_baseline_v2.py', 'Use frozen successor')
    require(not (DEFAULT / 'attempt.json').exists(), 'No automatic retry')
    unit = DEFAULT.name.replace('_', '-') + '.service'
    group = Path('/proc/self/cgroup').read_text()
    owner = subprocess.check_output(['/usr/bin/systemctl', '--user', 'show', unit, '-p', 'MainPID', '--value'], text=True).strip()
    require('/' + unit in group and owner == str(os.getpid()), 'Independent service must directly own capture')
    plan, binding = base.check_binding(DEFAULT, a.plan_sha256, a.binding_sha256)
    require(plan['capture_requires_smoke_pass'] is False and plan['power_release_requires_smoke_pass'] is True,
            'Wrong successor policy')
    save(DEFAULT / 'attempt.json', dict(pid=os.getpid(), cgroup=group, started_ns=g.time.time_ns(),
        plan_sha256=a.plan_sha256, binding_sha256=a.binding_sha256, capture_before_smoke_authorized=True), True)

    def interrupted(signum, frame):
        raise InterruptedError('Owned baseline capture interrupted: ' + str(signum))

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        run = g.run_simulator(DEFAULT, plan)
        report = g.final_check(DEFAULT, plan, binding, run)
        base.check_binding(DEFAULT, a.plan_sha256, a.binding_sha256)
        require(report['state'] == 'CAPTURE_COMPLETE_NOT_TASK_PASS' and not report['full_gate_task_pass'],
                'Capture cannot assert task PASS')
        report.update(baseline_context=plan['baseline_context'], historical_byte_identity='UNPROVEN',
                      configuration=plan['configuration'], power_release_requires_smoke_pass=True,
                      matching_smoke=str(base.SMOKE), power_publishable=False,
                      publication_scope='Activity only; final power release requires independent matching gate smoke PASS')
    except BaseException as error:
        report = dict(state='FAIL', mode='capture', case_id=base.Q8, full_gate_task_pass=False,
                      power_publishable=False, error=repr(error), artifacts_preserved=True)
    save(DEFAULT / 'result.json', report, True)
    save(DEFAULT / 'status.json', dict(state=report['state'], completed=True, child_pid=None))
    print(json.dumps({k: report[k] for k in ('state', 'case_id', 'full_gate_task_pass')}))
    return int(report['state'] == 'FAIL')


class HostTests(unittest.TestCase):
    def test_policy_identity_and_window(self):
        original = read(SOURCE / 'plan.json')
        before = copy.deepcopy(original)
        plan = successor_plan(original)
        self.assertEqual(original, before)
        self.assertEqual(plan['image'], str(base.GATE))
        self.assertEqual(plan['elf_map']['sha256'], base.ELF_SHA)
        self.assertEqual(plan['last_cycle'] - plan['first_cycle'], 3056)
        self.assertFalse(plan['capture_requires_smoke_pass'])
        self.assertTrue(plan['power_release_requires_smoke_pass'])
        self.assertEqual(g.MAX_SLOTS, 4)
        self.assertEqual(g.GATE.name, 'power_gate_build_20261117_all_on_01')

    def test_authorization_and_bad_window(self):
        with self.assertRaises(ValueError):
            execute(argparse.Namespace(authorize_run=False, acknowledge_reconstruction=True,
                                       allow_capture_before_smoke=True))
        bad = read(SOURCE / 'plan.json')
        bad['last_cycle'] += 1
        with self.assertRaises(ValueError):
            successor_plan(bad)


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('action', choices=('prepare', 'check', 'execute', 'self-test'))
    p.add_argument('--output', type=Path, default=DEFAULT)
    p.add_argument('--plan-sha256')
    p.add_argument('--binding-sha256')
    p.add_argument('--authorize-run', action='store_true')
    p.add_argument('--acknowledge-reconstruction', action='store_true')
    p.add_argument('--allow-capture-before-smoke', action='store_true')
    a = p.parse_args()
    require(a.output.resolve() == DEFAULT, 'Only owned capture_02 output supported')
    if a.action == 'execute':
        return execute(a)
    require(not a.authorize_run, 'Authorization only applies to execute')
    if a.action == 'self-test':
        return int(not unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(HostTests)).wasSuccessful())
    if a.action == 'prepare':
        prepare()
    else:
        base.check_binding(DEFAULT, sha(DEFAULT / 'plan.json'), sha(DEFAULT / 'image-binding.json'))
        print('HOST_PIN_CHECK_PASS_NO_CAPTURE_LAUNCHED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
