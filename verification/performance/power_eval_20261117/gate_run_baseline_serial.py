#!/usr/bin/env python3
"""Output-directory successor of gate_run_baseline.py; original scheduler unchanged.

The external serial waiter must drain all power RTL dispatchers before launch.
This file changes only output/worker names from the sealed baseline adapter.

Only explicit execute under its independent service can run GLS. Capture also
requires a completed numerical smoke on the exact same gate image and ELF.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import types
import unittest

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
GATE = OUT / 'power_gate_build_20261117_baseline_02'
RTL = OUT / 'power_rtl_20261117_baseline_01'
CAMPAIGN = OUT / 'power_precheck_20261117_baseline_02'
RELEASE = GATE / 'releases/q8_01/release.json'
RELEASE_SHA = '841fbd5e5cb3e1bf958b37be50313a813967d68c3195348e83841949a090083d'
COMMON_SHA = 'e05b5a5b23a5ca3ade67aebd10843029b5e1012745210fb1d87678ae43f37f5d'
COMMON_TEST_SHA = '1fe0b3d78d3567ba70a017f0da0359f3850497e957a8398db660666d7ad7fd1c'
VALIDATOR_SHA = 'a02fa358e532fb2bbd07534bf02755000cebc6d63e6304489fd1a0b6382f2b3e'
Q8 = 'legacy_q8_rvv'
ELF_SHA = '21aaea915c1101d597923d6a5e2007f68ce5fb04f5786f0ed5e9309d036986e7'
STATE = 'RECONSTRUCTED_BASELINE_GATE_BUILT_NOT_SIMULATED'
SMOKE = OUT / 'power_gls_20261117_baseline_q8_smoke_03'
CAPTURE = OUT / 'power_gls_20261117_baseline_q8_capture_04'


def load(path, name):
    # No pycache writes, source rewriting, or all-on global substitutions.
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(path.read_text(), str(path), 'exec'), module.__dict__)
    return module


def common():
    path = HERE / 'gate_run.py'
    import hashlib
    if hashlib.sha256(path.read_bytes()).hexdigest() != COMMON_SHA:
        raise ValueError('Sealed common runner drift')
    return load(path, 'baseline_sealed_gate_run')


g = common()
require, sha, read, save, verify = g.require, g.sha, g.read, g.save, g.verify


def admit():
    require(sha(RELEASE) == RELEASE_SHA, 'Exact Q8 release required')
    validator = GATE / 'inputs/build_baseline_gate_v2.py'
    require(sha(validator) == VALIDATOR_SHA and
            read(GATE / 'source-pins.json').get(str(validator)) == VALIDATOR_SHA,
            'Frozen baseline validator drift')
    v = load(validator, 'baseline_real_release_validator')
    data = v.check_release(GATE, v.BaselineContext(), RELEASE, RELEASE_SHA)
    require(data['image'] == str(RTL) and data['historical_byte_identity'] == 'UNPROVEN'
            and data['aggregate_status_claimed'] is False, 'Wrong baseline admission')
    entries = [c for c in data['cases'] if c['id'] == Q8]
    require(len(entries) == 1 and entries[0]['elf']['sha256'] == ELF_SHA, 'Exact baseline RVV ELF required')
    receipt = read(GATE / 'gate-receipt.json')
    require(receipt['baseline_context'] == data['baseline_context']
            and receipt['memory']['bytes'] == 1048576 and len(receipt['memory']['instances']) == 8,
            'Gate/reconstructed RTL context mismatch')
    return data, entries[0]


def prepare(a):
    out = g.scoped_output(a.output)
    require(out in (SMOKE, CAPTURE) and not out.exists(), 'Fresh owned baseline Q8 output required')
    require((a.mode == 'smoke' and out == SMOKE) or (a.mode == 'capture' and out == CAPTURE), 'Mode/output mismatch')
    g.validate_limits(a.mode, a.first_cycle, a.last_cycle, a.max_cycles,
                      a.wall_seconds, a.max_vcd_bytes, a.slot_seconds)
    admission, entry = admit()
    case = next(c for c in read(CAMPAIGN / 'plan.json')['cases'] if c['id'] == Q8)
    require(case['elf'] == entry['elf']['path'] and case['elf_sha256'] == ELF_SHA, 'RTL ELF/checker mismatch')
    checker = case['checker']
    require('--mode' in checker and checker[checker.index('--mode') + 1] == 'rvv'
            and any(Path(s).name == 'legacy_q8.py' for s in checker), 'Unknown Q8 smoke checker')
    if a.mode == 'capture':
        require(SMOKE.is_dir() and read(SMOKE / 'plan.json')['mode'] == 'smoke', 'Prepare smoke first')
    out.mkdir()
    (out / 'inputs').mkdir()
    (out / 'run').mkdir()
    pins = {}

    def pin(p):
        pins[str(p)] = sha(p)

    for name, expected in (('gate_run.py', COMMON_SHA), ('test_gate_run.py', COMMON_TEST_SHA),
                           ('gate_run_baseline_serial.py', sha(__file__))):
        src, dest = HERE / name, out / 'inputs' / name
        require(sha(src) == expected, 'Worker/support identity drift')
        shutil.copyfile(src, dest)
        pin(src)
        pin(dest)
    private = out / 'inputs/program.elf'
    shutil.copyfile(case['elf'], private)
    require(sha(private) == ELF_SHA, 'Private ELF mismatch')
    pin(private)
    pin(Path(case['elf']))
    for p in (RELEASE, RELEASE.parent / 'release-pins.json', GATE / 'source-pins.json',
              GATE / 'gate-receipt.json', GATE / 'inputs/build_baseline_gate_v2.py',
              CAMPAIGN / 'plan.json', CAMPAIGN / 'source-pins.json', Path(case['source_pins'])):
        pin(p)
    for p, expected in admission['evidence_pins'].items():
        require(sha(p) == expected, 'Selected RTL evidence drift')
        pins[p] = expected
    for arg in checker:
        if Path(arg).is_file():
            pin(Path(arg))
    for name, src in (('gate-plan.json', GATE / 'plan.json'),
                      ('rtl-plan.json', GATE / 'inputs/rtl-plan.json')):
        dest = out / 'inputs' / name
        shutil.copyfile(src, dest)
        pin(src)
        pin(dest)
    if a.mode == 'capture':
        pin(SMOKE / 'plan.json')
        pin(SMOKE / 'source-pins.json')
    argv = [str(GATE / 'sim/simv'), '-no_save', '-l', str(out / 'run/run.vcs.log'),
            '+PRELOAD=' + str(private), '+TESTCASE=' + Q8, '+NO_FSDB', '+NO_INSTR_TRACE',
            '+GATE_MAX_CYCLES=' + str(a.max_cycles)]
    if a.mode == 'capture':
        argv += ['+GATE_VCD=' + str(out / 'run/window.vcd'), '+GATE_ROI_FIRST=' + str(a.first_cycle),
                 '+GATE_ROI_LAST=' + str(a.last_cycle), '+GATE_STOP_AFTER_CAPTURE']
    plan = dict(schema='power-baseline-gls-run-v1', mode=a.mode, case_id=Q8, image=str(GATE),
        expected_build_state=STATE, baseline_context=admission['baseline_context'],
        historical_byte_identity='UNPROVEN', configuration='reconstructed_no_qbs_c910_baseline',
        release=str(RELEASE), release_sha256=RELEASE_SHA, checker=checker if a.mode == 'smoke' else None,
        command=argv, cwd=str(out / 'run'), original_result=entry['evidence']['result.json']['path'],
        elf_map=dict(prechecked=case['elf'], gls=str(private), sha256=ELF_SHA),
        first_cycle=a.first_cycle, last_cycle=a.last_cycle, clock_period_ns=1,
        max_cycles=a.max_cycles, wall_seconds=a.wall_seconds, slot_seconds=a.slot_seconds,
        max_vcd_bytes=a.max_vcd_bytes, max_log_bytes=256 * 1024**2, max_concurrent_simulators=4,
        automatic_retry=False, image_binding_required=True, capture_is_full_task_pass=False,
        smoke_prerequisite=str(SMOKE) if a.mode == 'capture' else None,
        window_basis='Planned RTL PC80000478 steady matmul: 62619..65675, four 764-cycle loops; '
                     'gate clock offset/phase must be independently verified, not assumed from RTL.',
        progress_semantics='Shared sealed runner wall/CPU/file/ROI progress; no invented cycle heartbeat')
    save(out / 'plan.json', plan, True)
    pin(out / 'plan.json')
    save(out / 'admission.json', admission, True)
    pin(out / 'admission.json')
    save(out / 'source-pins.json', pins, True)
    verify(pins)
    save(out / 'prepare-receipt.json', dict(state='PREPARED_WAITING_FOR_GATE_IMAGE_BINDING',
        historical_byte_identity='UNPROVEN', image_bound=False, jobs_launched=0), True)
    save(out / 'status.json', dict(state='PREPARED_WAITING_FOR_GATE_IMAGE_BINDING', jobs_launched=0))


def bind_image(out):
    require(not (out / 'image-binding.json').exists(), 'Immutable image binding already exists')
    verify(read(out / 'source-pins.json'))
    plan = read(out / 'plan.json')
    admit()
    build, image = read(GATE / 'build.json'), read(GATE / 'image-pins.json')
    require(build['state'] == STATE and build['baseline_context'] == plan['baseline_context']
            and build['gate_preparation_sha256'] == sha(GATE / 'source-pins.json')
            and build['image_pins'] == image, 'Successful exact baseline gate build required')
    verify(image)
    runtime = {str(GATE / 'sim/simv')} | {str(p) for p in (GATE / 'sim/simv.daidir').rglob('*.so')}
    require(runtime <= set(image) and len(runtime) > 1, 'Incomplete loader inventory')
    binding = dict(schema='power-baseline-gls-binding-v1', state='IMAGE_BOUND_NOT_LAUNCHED',
        plan_sha256=sha(out / 'plan.json'), source_pins_sha256=sha(out / 'source-pins.json'),
        gate_build=dict(path=str(GATE / 'build.json'), sha256=sha(GATE / 'build.json')),
        gate_image_inventory=dict(path=str(GATE / 'image-pins.json'), sha256=sha(GATE / 'image-pins.json')),
        baseline_context=plan['baseline_context'], historical_byte_identity='UNPROVEN',
        simv_sha256=image[str(GATE / 'sim/simv')], runtime_image={k: image[k] for k in sorted(runtime)}, image_pins=image)
    save(out / 'image-pins.json', image, True)
    save(out / 'image-binding.json', binding, True)
    unit = out.name.replace('_', '-') + '.service'
    worker = ['/usr/bin/python3', '-B', str(out / 'inputs/gate_run_baseline_serial.py'), 'execute',
              '--output', str(out), '--plan-sha256', binding['plan_sha256'],
              '--binding-sha256', sha(out / 'image-binding.json'), '--authorize-run', '--acknowledge-reconstruction']
    launcher = ['/usr/bin/systemd-run', '--user', '--unit=' + unit, '--property=Type=exec',
        '--property=KillMode=control-group', '--property=RuntimeMaxSec=' + str(plan['wall_seconds'] + plan['slot_seconds'] + 1800),
        '--property=TimeoutStopSec=30', '--property=StandardOutput=append:' + str(out / 'service.stdout.log'),
        '--property=StandardError=append:' + str(out / 'service.stderr.log'), *worker]
    save(out / 'ready-command.json', dict(service=launcher, shell=shlex.join(launcher), unit=unit,
        worker=worker, launched=False, capture_requires_smoke_pass=plan['mode'] == 'capture'), True)
    save(out / 'status.json', dict(state='IMAGE_BOUND_NOT_LAUNCHED', jobs_launched=0))


def check_binding(out, plan_hash, binding_hash):
    require(sha(out / 'plan.json') == plan_hash and sha(out / 'image-binding.json') == binding_hash,
            'Reviewed plan/binding drift')
    verify(read(out / 'source-pins.json'))
    plan, binding = read(out / 'plan.json'), read(out / 'image-binding.json')
    require(plan['image'] == str(GATE) and plan['expected_build_state'] == STATE
            and binding['plan_sha256'] == plan_hash
            and binding['source_pins_sha256'] == sha(out / 'source-pins.json'), 'Wrong baseline binding')
    for key in ('gate_build', 'gate_image_inventory'):
        verify({binding[key]['path']: binding[key]['sha256']})
    build = read(GATE / 'build.json')
    require(build['state'] == STATE and build['baseline_context'] == binding['baseline_context'] == plan['baseline_context']
            and read(GATE / 'image-pins.json') == read(out / 'image-pins.json') == binding['image_pins'], 'Gate image drift')
    verify(binding['image_pins'])
    verify(read(GATE / 'source-pins.json'))
    runtime = {str(GATE / 'sim/simv')} | {str(p) for p in (GATE / 'sim/simv.daidir').rglob('*.so')}
    require(runtime == set(binding['runtime_image']), 'Loader set drift')
    _, entry = admit()
    require(entry['elf']['path'] == plan['elf_map']['prechecked'] and
            entry['elf']['sha256'] == plan['elf_map']['sha256'] == sha(plan['elf_map']['gls']), 'Exact ELF drift')
    return plan, binding


def smoke_pass(plan, binding):
    require(plan['smoke_prerequisite'] == str(SMOKE), 'Wrong smoke prerequisite')
    p, b = check_binding(SMOKE, sha(SMOKE / 'plan.json'), sha(SMOKE / 'image-binding.json'))
    result = read(SMOKE / 'result.json')
    require(p['mode'] == 'smoke' and p['case_id'] == Q8 and p['elf_map']['sha256'] == plan['elf_map']['sha256']
            and b['simv_sha256'] == binding['simv_sha256'] == result['simv_sha256']
            and result['state'] == 'GATE_SMOKE_PASS' and result['full_gate_task_pass'] is True
            and result['elf_sha256'] == ELF_SHA, 'Completed matching Q8 numerical smoke required')
    verify(result['checked_artifacts'])
    proof = result['numericproof']
    verify({proof['path']: proof['sha256']})
    numeric = read(proof['path'])
    require(numeric == result['numerical'] and numeric['state'] == 'PASS'
            and numeric['log_sha256'] == sha(SMOKE / 'run/run.vcs.log'), 'Smoke numeric proof drift')
    return dict(result=dict(path=str(SMOKE / 'result.json'), sha256=sha(SMOKE / 'result.json')),
                numerical=proof, same_gate_image=True, same_prechecked_elf=True)


def execute(out, a):
    require(a.authorize_run and a.acknowledge_reconstruction, 'Explicit run/reconstruction authorization required')
    require(Path(__file__).resolve() == out / 'inputs/gate_run_baseline_serial.py', 'Use frozen adapter')
    require(not (out / 'attempt.json').exists(), 'No retry or overwrite')
    unit = out.name.replace('_', '-') + '.service'
    group = Path('/proc/self/cgroup').read_text()
    owner = subprocess.check_output(['/usr/bin/systemctl', '--user', 'show', unit, '-p', 'MainPID', '--value'], text=True).strip()
    require('/' + unit in group and owner == str(os.getpid()), 'Independent service must directly own runner')
    plan, binding = check_binding(out, a.plan_sha256, a.binding_sha256)
    smoke = smoke_pass(plan, binding) if plan['mode'] == 'capture' else None
    save(out / 'attempt.json', dict(pid=os.getpid(), cgroup=group, plan_sha256=a.plan_sha256,
        binding_sha256=a.binding_sha256, smoke_prerequisite=smoke, started_ns=g.time.time_ns()), True)

    def interrupted(signum, frame):
        raise InterruptedError('Owned baseline GLS interrupted by signal ' + str(signum))

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        run = g.run_simulator(out, plan)
        report = g.final_check(out, plan, binding, run)
        check_binding(out, a.plan_sha256, a.binding_sha256)
        if smoke:
            require(smoke == smoke_pass(plan, binding), 'Smoke prerequisite changed')
        report.update(baseline_context=plan['baseline_context'], historical_byte_identity='UNPROVEN',
                      configuration=plan['configuration'], smoke_prerequisite=smoke)
    except BaseException as error:
        report = dict(state='FAIL', mode=plan['mode'], case_id=Q8, full_gate_task_pass=False,
                      historical_byte_identity='UNPROVEN', error=repr(error), artifacts_preserved=True)
    save(out / 'result.json', report, True)
    save(out / 'status.json', dict(state=report['state'], completed=True, child_pid=None))
    print(json.dumps({k: report[k] for k in ('state', 'case_id', 'full_gate_task_pass')}))
    return int(report['state'] == 'FAIL')


class HostTests(unittest.TestCase):
    def test_no_fake_identity(self):
        self.assertEqual(g.GATE.name, 'power_gate_build_20261117_all_on_01')
        self.assertEqual(GATE.name, 'power_gate_build_20261117_baseline_02')
        self.assertEqual(g.MAX_SLOTS, 4)
        self.assertEqual(g.OUT, OUT)
        self.assertEqual(g.KNOWN_DISPATCHERS['precheck_v2.py'],
                         '699bc377a22a0a6f98d976b48b511c053139df97e7377c55fbc18b3500e7646a')

    def test_planned_window(self):
        g.validate_limits('capture', 62619, 65675, 1000000, 10800, 1024**3, 7200)
        self.assertEqual(65675 - 62619, 4 * 764)
        with self.assertRaises(ValueError):
            g.validate_limits('capture', 62619, 70000, 1000000, 10800, 1024**3, 7200)

    def test_capture_requires_real_smoke(self):
        with self.assertRaises(ValueError):
            smoke_pass({'smoke_prerequisite': '/wrong'}, {})

    def test_unauthorized_execute_never_runs(self):
        a = argparse.Namespace(authorize_run=False, acknowledge_reconstruction=True)
        with self.assertRaises(ValueError):
            execute(SMOKE, a)


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('action', choices=('prepare', 'bind-image', 'check', 'execute', 'status', 'self-test'))
    p.add_argument('--output', type=Path)
    p.add_argument('--mode', choices=('smoke', 'capture'), default='smoke')
    p.add_argument('--first-cycle', type=int)
    p.add_argument('--last-cycle', type=int)
    p.add_argument('--max-cycles', type=int, default=1000000)
    p.add_argument('--wall-seconds', type=int, default=10800)
    p.add_argument('--slot-seconds', type=int, default=7200)
    p.add_argument('--max-vcd-bytes', type=int, default=1024**3)
    p.add_argument('--plan-sha256')
    p.add_argument('--binding-sha256')
    p.add_argument('--authorize-run', action='store_true')
    p.add_argument('--acknowledge-reconstruction', action='store_true')
    a = p.parse_args()
    if a.action == 'self-test':
        require(not a.authorize_run, 'Host tests do not authorize GLS')
        require(sha(HERE / 'test_gate_run.py') == COMMON_TEST_SHA, 'Shared tests drift')
        tests = load(HERE / 'test_gate_run.py', 'baseline_shared_host_tests')
        suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(HostTests),
                                   unittest.defaultTestLoader.loadTestsFromModule(tests)])
        return int(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
    require(a.output is not None, '--output required')
    out = g.scoped_output(a.output)
    require(out in (SMOKE, CAPTURE), 'Only owned baseline Q8 outputs supported')
    if a.action == 'execute':
        return execute(out, a)
    require(not a.authorize_run, 'Run authorization only applies to execute')
    if a.action == 'prepare':
        require(a.acknowledge_reconstruction, 'Reconstruction acknowledgement required')
        prepare(a)
        print(json.dumps(read(out / 'prepare-receipt.json')))
    elif a.action == 'bind-image':
        bind_image(out)
        print('BASELINE_IMAGE_BOUND_NOT_LAUNCHED')
    elif a.action == 'check':
        verify(read(out / 'source-pins.json'))
        if (out / 'image-binding.json').exists():
            check_binding(out, sha(out / 'plan.json'), sha(out / 'image-binding.json'))
        print('HOST_PIN_CHECK_PASS_NO_GLS_LAUNCHED')
    else:
        print(json.dumps(read(out / 'status.json')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
