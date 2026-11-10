#!/usr/bin/env python3
"""Stage3 SoC identity adapter for the immutable architectural QK firmware."""
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

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
SOFTWARE = OUT / 'resident_qk_boundary_build_20261110_01'
BUILDER_SHA = 'ad6cfb879e5ee61344a92591f2d78dd290e4a649b543e09b7f179ce88c3337b2'
BUILD_SHA = 'f660436c74629b8cc2055ea3387e362538b530f76a4884cec98dfbedda515af2'
PINS_SHA = '33a295f4a3091fbffeff8128222ca3cdac03fdc95aef9350e17ee2f1244cedec'
RUNNER_SHA = 'e28928cb09b9d3ebef94a5523efc1f4ce58283404290034f7c014631405035d6'
CHECKER_SHA = 'af6eb38b585d671c69eb3c701397ef9efccd105de6d91444e07079a933d65643'
OWN = ('qk_boundary_soc_v2.py', 'test_qk_boundary_soc_v2.py')
SIM_SECONDS, PROTOCOL_SECONDS, BOUNDARY_SECONDS, SERVICE_SECONDS = 5400, 900, 300, 7200


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The same reviewed contract used by BUILD02, not a translated receipt.
import hashlib
if hashlib.sha256((HERE / 'build_soc.py').read_bytes()).hexdigest() != BUILDER_SHA:
    raise ValueError('Unreviewed shared SoC contract')
b = load(HERE / 'build_soc.py', 'qk_v2_shared_soc_contract')


def frozen_modules():
    b.verify({SOFTWARE / 'build.json': BUILD_SHA, SOFTWARE / 'source-pins.json': PINS_SHA})
    local = SOFTWARE / 'inputs/qk_boundary'
    b.verify({local / 'run.py': RUNNER_SHA, local / 'check.py': CHECKER_SHA})
    expected = b.read(SOFTWARE / 'source-pins.json')
    members = ('cases.py', 'generate.py', 'elf.py', 'build.py', 'check.py', 'run.py')
    b.verify({local / name: expected[str(local / name)] for name in members})
    # Import isolation only: no checker function/constant/receipt is modified.
    names = tuple(Path(n).stem for n in members)
    previous, search = {n: sys.modules.get(n) for n in names}, list(sys.path)
    try:
        for name in names:
            sys.modules.pop(name, None)
        sys.path.insert(0, str(local))
        runner = load(local / 'run.py', 'qk_v2_frozen_runner')
        return runner, runner.check, runner.cases
    finally:
        sys.path[:] = search
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def collect(socdir, software=SOFTWARE):
    b.require(Path(software).resolve() == SOFTWARE, 'Only the reviewed immutable QK build01')
    socdir = b.output_path(Path(socdir))
    soc, pins = b.checked_build(socdir)
    b.verify({socdir / 'inputs/build_soc.py': BUILDER_SHA})
    old, checker, _ = frozen_modules()
    sw, vectors, contract = checker.checked_build(SOFTWARE)
    b.require(sw['elf_sha256'] == 'd7823dca2c700174223629df36a7dc65de1828ee313e7219d57a059c0b5bc7fa',
              'Wrong firmware ELF')
    pins.update(b.read(SOFTWARE / 'source-pins.json'))
    pins.update(sw['artifacts'])
    pins[str(SOFTWARE / 'build.json')] = BUILD_SHA
    b.verify(pins)
    return soc, sw, vectors, contract, pins, old


def environment(plan, out):
    # Use the accepted build's nonsecret EDA allowlist, not the user manager's
    # full environment. Remove empty/duplicate search paths (no implicit CWD).
    source = plan['environment']
    needed = ('VCS_HOME', 'VCS_ARCH_OVERRIDE', 'SNPSLMD_LICENSE_FILE')
    b.require(all(source.get(k) for k in needed), 'Missing accepted VCS runtime/license setting')
    env = {k: source[k] for k in (*needed, 'LM_LICENSE_FILE') if source.get(k)}
    directories = [str(Path(env['VCS_HOME']) / 'linux64/lib'), *source.get('LD_LIBRARY_PATH', '').split(':')]
    env['LD_LIBRARY_PATH'] = ':'.join(dict.fromkeys(p for p in directories if p))
    env.update(PATH='/usr/bin:/bin', HOME=source['HOME'], LC_ALL='C', TMPDIR='/tmp',
               PYTHONPATH=str(out / 'inputs/verification'), PYTHONDONTWRITEBYTECODE='1',
               READELF='/usr/bin/readelf')
    b.require(all(isinstance(v, str) and '\n' not in v and '\0' not in v for v in env.values()), 'Malformed environment')
    return env


def output_path(path):
    return b.output_path(Path(path), 'stage3_qk_boundary_v2_')


def selection(out, socdir, soc, sw, old):
    env = environment(b.read(socdir / 'plan.json'), out)
    python = str(Path(sys.executable).resolve())
    commands = old.recipes(out, soc, sw, SOFTWARE)
    b.require(all(command[0] == python for name, command in commands.items() if name != 'simulation'),
              'Unexpected checker interpreter')
    b.require(commands['simulation'][0] == soc['simv'] and
              '+PRELOAD=' + sw['elf'] in commands['simulation'], 'Wrong executable/program')
    return dict(schema='resident-qk-boundary-soc-v2', soc_build=str(socdir), software_build=str(SOFTWARE),
        soc_receipt_sha256=b.sha(socdir / 'build.json'), software_receipt_sha256=BUILD_SHA,
        firmware_pins_sha256=PINS_SHA, numerical_checker_sha256=CHECKER_SHA,
        configuration=soc['configuration'], image_contract=soc['image_contract'], cpu_overlay=soc['cpu_overlay'],
        image_pins=soc['image_pins'], commands=commands, environment=env, python=python,
        sim_seconds=SIM_SECONDS, protocol_seconds=PROTOCOL_SECONDS, boundary_seconds=BOUNDARY_SECONDS,
        service_seconds=SERVICE_SECONDS, direct_attempts=35, successful_qk=24, rejected_qk=12,
        qk_requests=34, accelerator_exceptions=10, cpu_only_off_rejections=2,
        identity_adapter_only=True, numerical_and_protocol_checkers_unchanged=True,
        protocol_note='Legacy AKV-column classification is not QK semantic acceptance', automatic_retry=False)


def runtime_libraries(out, s):
    argv = ['/usr/bin/ldd', s['commands']['simulation'][0]]
    proc = subprocess.run(argv, cwd=out / 'work', env=s['environment'], text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
    b.save(out / 'runtime-link.command.json', dict(argv=argv, environment=s['environment'], returncode=proc.returncode))
    (out / 'runtime-link.log').write_text(proc.stdout)
    b.require(proc.returncode == 0 and 'not found' not in proc.stdout, 'Unresolved VCS runtime library')
    paths = re.findall(r'(?:=>\s+|^\s*)(/[^\s()]+)', proc.stdout, re.M)
    b.require(paths, 'No dynamic-library evidence')
    pins = {str(Path(p).resolve()): b.sha(Path(p).resolve()) for p in paths}
    pins[str(Path('/usr/bin/ldd').resolve())] = b.sha(Path('/usr/bin/ldd').resolve())
    return pins


def service_unit(out):
    return 'resident-qk-boundary-v2-' + out.name + '.service'


def verify_firmware_copy(out, sw):
    original, copy = SOFTWARE / 'inputs/qk_boundary', out / 'inputs/qk_boundary'
    expected = {str(copy / Path(p).relative_to(original)): h for p, h in sw['artifacts'].items()
                if Path(p).is_relative_to(original)}
    b.require(len(expected) == 10, 'Unexpected original firmware helper inventory')
    b.exact_files(copy, expected)


def service_argv(out, s, review):
    return ['/usr/bin/systemd-run', '--user', '--unit=' + service_unit(out),
        '--property=WorkingDirectory=' + str(out / 'work'), '--property=RuntimeMaxSec=' + str(SERVICE_SECONDS),
        '--property=KillMode=control-group', '--property=TimeoutStopSec=20',
        '--property=StandardOutput=append:' + str(out / 'service.stdout.log'),
        '--property=StandardError=append:' + str(out / 'service.stderr.log'),
        *['--setenv=' + k + '=' + v for k, v in sorted(s['environment'].items())],
        s['python'], '-B', '-u', str(out / 'inputs/qk_boundary_soc_v2.py'), 'run',
        '--output', str(out), '--parent-reviewed', '--review-sha256', review]


def prepare(out, socdir, software=SOFTWARE):
    out = output_path(out)
    b.require(not out.exists(), 'Preserve every prior attempt')
    soc, sw, _, _, pins, old = collect(socdir, software)
    out.mkdir(); (out / 'inputs').mkdir(); (out / 'work').mkdir()
    report = dict(state='FAIL', execution='NOT_RUN', simulation_started=False, automatic_retry=False)
    try:
        for name in OWN:
            src = HERE / name
            shutil.copyfile(src, out / 'inputs' / name)
            pins[str(src)] = b.sha(src)
        shutil.copyfile(socdir / 'inputs/build_soc.py', out / 'inputs/build_soc.py')
        shutil.copytree(SOFTWARE / 'inputs/qk_boundary', out / 'inputs/qk_boundary')
        verify_firmware_copy(out, sw)
        for src in (ROOT / 'verification/ara_verify').rglob('*.py'):
            dest = out / 'inputs/verification' / src.relative_to(ROOT / 'verification')
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            pins[str(src)] = b.sha(src)
        s = selection(out, socdir, soc, sw, old)
        b.save(out / 'selection.json', s)
        b.save(out / 'launch-receipt.json', dict(environment=s['environment'],
            environment_scope='Nonsecret allowlist only; worker clears other inherited variables before children',
            service_command=service_argv(out, s, '{SOURCE_PINS_SHA256}'), execution='NOT_RUN'))
        pins.update(runtime_libraries(out, s))  # Loader inspection only, never simv/main.
        for path in (Path(s['python']), Path('/usr/bin/readelf'), Path('/usr/bin/systemctl'), Path('/usr/bin/systemd-run')):
            pins[str(path.resolve())] = b.sha(path.resolve())
        for name in ('host-tests', 'firmware-tests'):
            argv = [s['python'], '-B', str(out / 'inputs/test_qk_boundary_soc_v2.py')] if name == 'host-tests' else [
                s['python'], '-B', str(out / 'inputs/qk_boundary/test_boundary.py'), '--build', str(SOFTWARE)]
            with (out / (name + '.log')).open('x') as stream:
                subprocess.run(argv, cwd=out / 'inputs', env=s['environment'], stdout=stream,
                               stderr=subprocess.STDOUT, check=True, timeout=120)
            b.save(out / (name + '.command.json'), argv)
        inventory = b.files(out / 'inputs')
        b.save(out / 'runner-inventory.json', inventory)
        pins.update(inventory)
        for name in ('selection.json', 'launch-receipt.json', 'runtime-link.command.json', 'runtime-link.log',
                     'host-tests.log', 'host-tests.command.json', 'firmware-tests.log', 'firmware-tests.command.json',
                     'runner-inventory.json'):
            pins[str(out / name)] = b.sha(out / name)
        b.verify(pins)
        b.save(out / 'source-pins.json', pins)
        report.update(state='PREPARED_NOT_EXECUTED', source_pins_sha256=b.sha(out / 'source-pins.json'),
                      frozen_worker=str(out / 'inputs/qk_boundary_soc_v2.py'))
        b.save(out / 'prepared.json', report)
        verify_prepared(out)
    except BaseException as exc:
        report.update(state='FAIL', error=repr(exc))
    b.save(out / 'prepare-report.json', report)
    b.require(report['state'] == 'PREPARED_NOT_EXECUTED', 'Preparation failed; retained ' + str(out))
    return report


def verify_prepared(out):
    out = output_path(out)
    s, pins = b.read(out / 'selection.json'), b.read(out / 'source-pins.json')
    prepared = b.read(out / 'prepared.json')
    b.require(prepared['state'] == 'PREPARED_NOT_EXECUTED' and not prepared['simulation_started'] and
              prepared['source_pins_sha256'] == b.sha(out / 'source-pins.json'), 'Prepared receipt drift')
    b.verify(pins)
    b.exact_files(out / 'inputs', b.read(out / 'runner-inventory.json'))
    soc, sw, vectors, contract, mandatory, old = collect(Path(s['soc_build']))
    verify_firmware_copy(out, sw)
    b.require(all(pins.get(p) == h for p, h in mandatory.items()), 'Missing mandatory SoC/software identity')
    b.require(s == selection(out, Path(s['soc_build']), soc, sw, old), 'Selection/environment/command drift')
    receipt = b.read(out / 'launch-receipt.json')
    b.require(receipt['environment'] == s['environment'] and
              receipt['service_command'] == service_argv(out, s, '{SOURCE_PINS_SHA256}'), 'Launch environment drift')
    for name in ('selection.json', 'launch-receipt.json', 'runner-inventory.json', 'host-tests.log', 'firmware-tests.log',
                 'runtime-link.log', 'runtime-link.command.json', 'host-tests.command.json', 'firmware-tests.command.json'):
        b.require(pins.get(str(out / name)) == b.sha(out / name), 'Unpinned preparation evidence')
    return s, pins, soc, sw, vectors, contract, old


def service_command(out, review):
    s, *_ = verify_prepared(out)
    b.require(review == b.sha(out / 'source-pins.json') and not (out / 'attempt.json').exists(), 'Review mismatch/already attempted')
    return service_argv(out, s, review)


def execute(out, review):
    b.require(Path(__file__).resolve() == out / 'inputs/qk_boundary_soc_v2.py', 'Execute frozen successor only')
    b.require(review == b.sha(out / 'source-pins.json'), 'Explicit reviewed inventory required')
    b.require(not any((out / 'work').iterdir()), 'No repeat execution')
    b.claim_attempt(out, review, service_unit(out), terminal='report.json')
    report = dict(state='FAIL', automatic_retry=False, performance_measured=False, deployment_approved=False,
                  numerical_checked=False, independent_protocol_checked=False, identity_adapter_only=True)
    status = dict(state='PREFLIGHT', child_pid=None, owner_pid=os.getpid())
    try:
        s, pins, soc, sw, vectors, _, old = verify_prepared(out)
        os.environ.clear(); os.environ.update(s['environment'])
        base, _ = b.helpers(Path(s['soc_build']) / 'inputs')
        for name, seconds in (('simulation', SIM_SECONDS), ('protocol', PROTOCOL_SECONDS), ('boundary', BOUNDARY_SECONDS)):
            base.execute(s['commands'][name], out / 'work', out / 'work' / (name + '.log'),
                         seconds, status, out / 'status.json', name.upper())
            if name == 'simulation':
                text = (out / 'work/run.vcs.log').read_text()
                b.require(text.count('Core Test *** SUCCESS ***') == 1 and not old.re_failure(text), 'Unsuccessful/ambiguous EOC')
        work = out / 'work'
        log, vector, commit = work / 'run.vcs.log', work / 'vector_trace.csv', work / 'commit.csv'
        proof, checked = b.read(work / 'uvm_result.json'), b.read(work / 'boundary.log')
        image = {p: h for p, h in soc['image_pins'].items() if p == soc['simv'] or p.endswith('.so')}
        b.require(any(p.endswith('.so') for p in image) and proof.get('status') == 'PASS' and proof.get('issues') == [] and
            proof.get('elf_sha256') == sw['elf_sha256'] and proof.get('simv_sha256') == b.sha(soc['simv']) and
            proof.get('sim_image_sha256') == image and proof.get('log_sha256') == b.sha(log) and
            proof.get('vector_trace_sha256') == b.sha(vector), 'Independent protocol evidence identity')
        sys.path.insert(0, str(out / 'inputs/verification'))
        from ara_verify import uvm_dut
        negative = old.scoped_exceptions(text, vectors, proof, uvm_dut)
        b.require(checked['schema'] == old.cases.SCHEMA and checked['numerical_checked'] and
                  checked['architecture_checked'] and checked['protocol_checked'] is False, 'Frozen checker scope mismatch')
        for p in (log, vector, commit, SOFTWARE / 'build.json', SOFTWARE / 'source-pins.json'):
            b.require(checked['evidence_sha256'].get(str(p)) == b.sha(p), 'Numerical/architectural evidence mismatch')
        verify_prepared(out)
        b.require(b.sha(out / 'source-pins.json') == review, 'Reviewed inventory drift')
        report.update(state='PASS', numerical_checked=True, architecture_checked=True,
            independent_protocol_checked=True, post_pins_match=True, post_image_match=True,
            negative=negative, work=checked['work'])
    except BaseException as exc:
        report['error'] = repr(exc)
    report['source_pins_sha256'] = b.sha(out / 'source-pins.json')
    report['artifacts'] = b.files(out / 'work')
    b.save(out / 'report.json', report)
    return int(report['state'] != 'PASS')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('action', choices=('prepare', 'service-command', 'run'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--soc-build', type=Path)
    p.add_argument('--software-build', type=Path, default=SOFTWARE)
    p.add_argument('--parent-reviewed', action='store_true')
    p.add_argument('--review-sha256')
    a = p.parse_args()
    if a.action == 'prepare':
        b.require(a.soc_build is not None, 'Explicit --soc-build required')
        print(json.dumps(prepare(a.output, a.soc_build, a.software_build), sort_keys=True))
    elif a.action == 'service-command':
        print(shlex.join(service_command(a.output, a.review_sha256)))
    else:
        b.require(a.parent_reviewed and a.review_sha256, 'Explicit parent review required')
        def interrupted(sig, _frame):
            raise InterruptedError('Signal ' + str(sig))
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, interrupted)
        raise SystemExit(execute(a.output, a.review_sha256))
