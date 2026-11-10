#!/usr/bin/env python3
"""One reviewed SDK functional run on the accepted stage3 image; no rebuild."""
import argparse
import hashlib
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
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
SHARED = ROOT/'verification/performance/resident_rvv/qk_shared'
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
SOFTWARE = OUT/'stage3_attention_sdk_build_20261110_02'
BUILDER_SHA = 'ad6cfb879e5ee61344a92591f2d78dd290e4a649b543e09b7f179ce88c3337b2'
BUILD_SHA = 'ac91488d3ea3836121973fa2ecf54c5ef34a7798b1b510dbb2941d8bdedabd81'
FW_PINS_SHA = '1d63af8545837bb63e0475ac489eeddbdfb8576a56b22a9ef2da3f9b4840f099'
ELF_SHA = 'd8c413799646ddf3286347d0c18a76eaaadce27a2840fc3bf4f46f3d7d1de17c'
CHECKER = {
    'check.py': '56b6cbd8d240a320cdfa8454565ecd78224a7488e813df2f9a5c6431ce450979',
    'fixture.py': 'c4c47d5c7933750a69bf2d8bff8ad1c08eb2e679fd9d2f6bf1503d15ee14ec9f',
}
OWN = ('run.py', 'test_run.py')
SIM_SECONDS, SDK_SECONDS, PROTOCOL_SECONDS, SERVICE_SECONDS = 5400, 300, 900, 7200
LEGACY = (
    'verification/performance/chain_profile/build_soc.py',
    'verification/performance/chain_profile/run_case.py',
    'verification/performance/resident_rvv/soc_eval/run_smoke.py',
    'verification/performance/resident_rvv/soc_eval/experiment.py',
    'verification/performance/akv_pair_eval/integration/build.py',
    'verification/performance/akv_pair_eval/integration/check.py',
    'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contract = HERE/'build_soc.py' if (HERE/'build_soc.py').exists() else SHARED/'build_soc.py'
if hashlib.sha256(contract.read_bytes()).hexdigest() != BUILDER_SHA:
    raise ValueError('Unreviewed stage3 SoC contract')
b = load(contract, 'sdk_run_stage3_contract')


def checker(local=None):
    local = SOFTWARE/'inputs/fixture' if local is None else Path(local)
    b.verify({local/name: digest for name, digest in CHECKER.items()})
    previous, search = sys.modules.get('fixture'), list(sys.path)
    try:
        sys.modules.pop('fixture', None)
        sys.path.insert(0, str(local))
        c = load(local/'check.py', 'sdk_run_frozen_checker')
        b.require(Path(c.__file__).resolve() == (local/'check.py').resolve() and
                  Path(c.f.__file__).resolve() == (local/'fixture.py').resolve() and
                  b.sha(c.f.__file__) == CHECKER['fixture.py'], 'Wrong fixture import')
        return c
    finally:
        sys.path[:] = search
        if previous is None:
            sys.modules.pop('fixture', None)
        else:
            sys.modules['fixture'] = previous


def legacy():
    previous, search = sys.modules.get('build_soc'), list(sys.path)
    sys.modules['build_soc'] = load(ROOT/LEGACY[0], 'sdk_run_sealed_chain')
    try:
        return load(ROOT/LEGACY[2], 'sdk_run_sealed_smoke')
    finally:
        sys.path[:] = search
        if previous is None:
            sys.modules.pop('build_soc', None)
        else:
            sys.modules['build_soc'] = previous


def collect(socdir):
    socdir = b.output_path(socdir)
    soc, pins = b.checked_build(socdir)
    b.verify({socdir/'inputs/build_soc.py': BUILDER_SHA,
              SOFTWARE/'build.json': BUILD_SHA, SOFTWARE/'source-pins.json': FW_PINS_SHA})
    sw = checker().build_receipt(SOFTWARE)
    b.require(sw['elf'] == str(SOFTWARE/'attention_sdk.elf') and sw['elf_sha256'] == ELF_SHA and
              sw['host_tests'] == 18 and
              [v['expected_fcsr'] for v in sw['fixture']['results']] == [3, 11, 3] and
              sw['fixture']['results'][2]['expf_samples'] ==
                  [dict(input=0, output=0x3f800000, fflags=0)]*6 and
              set(sw['fixture']['counter_semantics']) == {'PV_PREP', 'PV'},
              'Wrong firmware/counter/expf contract')
    old = legacy()
    extra = b.read(SOFTWARE/'source-pins.json') | sw['artifacts']
    extra[str(SOFTWARE/'build.json')] = BUILD_SHA
    extra.update(old.checker_inventory())
    extra.update({str(ROOT/p): b.sha(ROOT/p) for p in LEGACY})
    extra.update({str(old.e.contract.PRIMARY/p): digest for p, digest in old.e.contract.SEALED.items()})
    for tool in (sys.executable, '/usr/bin/bash', '/usr/bin/readelf', '/usr/bin/ldd',
                 '/usr/bin/systemctl', '/usr/bin/systemd-run'):
        path = Path(tool).resolve()
        extra[str(path)] = b.sha(path)
    old.e.merge(pins, extra)
    b.verify(pins)
    return soc, sw, pins, old


def environment(socdir, out):
    source = b.read(socdir/'plan.json')['environment']
    needed = ('VCS_HOME', 'VCS_ARCH_OVERRIDE', 'SNPSLMD_LICENSE_FILE')
    b.require(all(source.get(k) for k in needed), 'Missing accepted VCS environment')
    env = {k: source[k] for k in (*needed, 'LM_LICENSE_FILE') if source.get(k)}
    paths = [str(Path(env['VCS_HOME'])/'linux64/lib'), *source.get('LD_LIBRARY_PATH', '').split(':')]
    env['LD_LIBRARY_PATH'] = ':'.join(dict.fromkeys(p for p in paths if p))
    env.update(PATH='/usr/bin:/bin', HOME=source['HOME'], LC_ALL='C', TMPDIR='/tmp',
               PYTHONPATH=str(out/'inputs/verification'), PYTHONDONTWRITEBYTECODE='1',
               READELF='/usr/bin/readelf')
    b.require(all(isinstance(v, str) and '\n' not in v and '\0' not in v for v in env.values()),
              'Malformed execution environment')
    return env


def recipes(out, soc, sw, python, old):
    commands = old.recipes(out, soc, sw, python)
    sim = commands['simulation']
    sim[sim.index('+TESTCASE=resident_pv_soc_smoke')] = '+TESTCASE=resident_attention_sdk'
    sim.append('+RESIDENT_QK_PERF')
    commands['sdk'] = [python, '-B', str(out/'inputs/checker/check.py'),
        '--build', str(SOFTWARE), '--log', str(out/'work/run.vcs.log'),
        '--vector', str(out/'work/vector_trace.csv'), '--commit', str(out/'work/commit.csv')]
    return commands


def selection(out, socdir, soc, sw, old):
    python = str(Path(sys.executable).resolve())
    return dict(schema='stage3-sdk-functional-run-v1', soc_build=str(socdir), software_build=str(SOFTWARE),
        soc_receipt_sha256=b.sha(socdir/'build.json'), software_receipt_sha256=BUILD_SHA,
        firmware_pins_sha256=FW_PINS_SHA, elf_sha256=ELF_SHA,
        configuration=soc['configuration'], image_contract=soc['image_contract'],
        cpu_overlay=soc['cpu_overlay'], image_pins=soc['image_pins'],
        checker_sha256=CHECKER, python=python, environment=environment(socdir, out),
        commands=recipes(out, soc, sw, python, old), sim_seconds=SIM_SECONDS,
        sdk_seconds=SDK_SECONDS, protocol_seconds=PROTOCOL_SECONDS, service_seconds=SERVICE_SECONDS,
        scope=sw['scope'], automatic_retry=False, fsdb=False, performance_baseline=False)


def output_path(path):
    return b.output_path(Path(path), 'stage3_attention_sdk_vcs_')


def service_unit(out):
    return 'stage3-attention-sdk-'+out.name+'.service'


def service_argv(out, s, review):
    return ['/usr/bin/systemd-run', '--user', '--unit='+service_unit(out),
        '--property=WorkingDirectory='+str(out/'work'), '--property=RuntimeMaxSec='+str(SERVICE_SECONDS),
        '--property=KillMode=control-group', '--property=TimeoutStopSec=20',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        *['--setenv='+k+'='+v for k, v in sorted(s['environment'].items())],
        s['python'], '-B', '-u', str(out/'inputs/run.py'), 'run', '--output', str(out),
        '--parent-reviewed', '--review-sha256', review]


def host_command(out, name, argv, env, seconds):
    with (out/(name+'.log')).open('x') as stream:
        proc = subprocess.run(argv, cwd=out, env=env, stdout=stream,
                              stderr=subprocess.STDOUT, timeout=seconds)
    b.save(out/(name+'.command.json'), dict(argv=argv, cwd=str(out), timeout_seconds=seconds,
                                         returncode=proc.returncode))
    b.require(proc.returncode == 0, 'Preparation failed: '+name)
    return (out/(name+'.log')).read_text()


PREP_FILES = ('selection.json', 'launch-receipt.json', 'runner-inventory.json',
              'host-tests.log', 'host-tests.command.json', 'image-contract.log',
              'image-contract.command.json', 'runtime-link.log', 'runtime-link.command.json')


def prepare(out, socdir):
    b.require(HERE == SHARED/'full_call_sdk', 'Prepare with the original reviewed runner')
    out, socdir = output_path(out), b.output_path(Path(socdir))
    b.require(not out.exists(), 'Preserve every prior output/attempt')
    soc, sw, pins, old = collect(socdir)
    out.mkdir()
    (out/'inputs/checker').mkdir(parents=True)
    (out/'work').mkdir()
    report = dict(state='FAIL', execution='NOT_RUN', simulation_started=False, automatic_retry=False)
    try:
        for name in OWN:
            shutil.copyfile(HERE/name, out/'inputs'/name)
            pins[str(HERE/name)] = b.sha(HERE/name)
        shutil.copyfile(socdir/'inputs/build_soc.py', out/'inputs/build_soc.py')
        for name in CHECKER:
            shutil.copyfile(SOFTWARE/'inputs/fixture'/name, out/'inputs/checker'/name)
        for original, digest in old.checker_inventory().items():
            src = Path(original)
            dest = out/'inputs/verification'/src.relative_to(ROOT/'verification')
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            b.verify({dest: digest})
        checker(out/'inputs/checker')
        inventory = b.files(out/'inputs')
        b.save(out/'runner-inventory.json', inventory)
        s = selection(out, socdir, soc, sw, old)
        b.save(out/'selection.json', s)
        b.save(out/'launch-receipt.json', dict(environment=s['environment'], execution='NOT_RUN',
            service_command=service_argv(out, s, '{SOURCE_PINS_SHA256}')))
        host_command(out, 'host-tests', [s['python'], '-B', str(out/'inputs/test_run.py'), '-v'],
                     s['environment'], 120)
        host_command(out, 'image-contract', s['commands']['image_contract'], s['environment'], 180)
        linked = host_command(out, 'runtime-link', ['/usr/bin/ldd', soc['simv']], s['environment'], 30)
        b.require('not found' not in linked, 'Unresolved simulator library')
        libraries = re.findall(r'(?:=>\s+|^\s*)(/[^\s()]+)', linked, re.M)
        b.require(libraries, 'Missing runtime loader evidence')
        pins.update({str(Path(p).resolve()): b.sha(Path(p).resolve()) for p in libraries})
        pins.update(inventory)
        pins.update({str(out/name): b.sha(out/name) for name in PREP_FILES})
        b.verify(pins)
        b.save(out/'source-pins.json', pins)
        report.update(state='PREPARED_NOT_EXECUTED', host_tests_passed=True,
                      source_pins_sha256=b.sha(out/'source-pins.json'))
        b.save(out/'prepared.json', report)
        verify_prepared(out)
    except BaseException as exc:
        report.update(state='FAIL', error=repr(exc))
    b.save(out/'prepare-report.json', report)
    b.require(report['state'] == 'PREPARED_NOT_EXECUTED', 'Preparation failed; retained '+str(out))
    return report


def verify_prepared(out):
    out = output_path(out)
    s, pins, prepared = (b.read(out/name) for name in ('selection.json', 'source-pins.json', 'prepared.json'))
    b.require(prepared == dict(state='PREPARED_NOT_EXECUTED', execution='NOT_RUN', simulation_started=False,
        automatic_retry=False, host_tests_passed=True, source_pins_sha256=b.sha(out/'source-pins.json')),
        'Prepared receipt drift')
    b.verify(pins)
    b.exact_files(out/'inputs', b.read(out/'runner-inventory.json'))
    checker(out/'inputs/checker')
    socdir = Path(s['soc_build'])
    soc, sw, required, old = collect(socdir)
    original = SHARED/'full_call_sdk'
    expected = {str(out/'inputs'/name): b.sha(original/name) for name in OWN}
    expected[str(out/'inputs/build_soc.py')] = BUILDER_SHA
    expected.update({str(out/'inputs/checker'/name): digest for name, digest in CHECKER.items()})
    expected.update({str(out/'inputs/verification'/Path(p).relative_to(ROOT/'verification')): digest
                     for p, digest in old.checker_inventory().items()})
    b.require(b.read(out/'runner-inventory.json') == expected, 'Frozen runner/checker inventory drift')
    required.update(expected)
    required.update({str(original/name): b.sha(original/name) for name in OWN})
    required.update({str(out/name): b.sha(out/name) for name in PREP_FILES})
    b.require(all(pins.get(p) == digest for p, digest in required.items()), 'Missing mandatory pin')
    b.require(s == selection(out, socdir, soc, sw, old), 'Selection/configuration/recipe drift')
    b.require(b.read(out/'launch-receipt.json') == dict(environment=s['environment'], execution='NOT_RUN',
        service_command=service_argv(out, s, '{SOURCE_PINS_SHA256}')), 'Launch recipe drift')
    return s, pins, soc, sw, old


def service_command(out, review):
    s, *_ = verify_prepared(out)
    b.require(review == b.sha(out/'source-pins.json') and
              not any((out/name).exists() for name in ('attempt.json', 'owner.json', 'result.json')) and
              not any((out/'work').iterdir()), 'Review mismatch or already attempted')
    return service_argv(out, s, review)


def checked_sdk(result, sw):
    b.require(result.get('protocol_checked') is False and result.get('performance_acceptance') is False and
        result.get('scope') == sw['scope'] and result['numerical']['calls'] == 3 and
        result['numerical']['output_values'] == 1088 and result['numerical']['bitexact'] is True and
        result['numerical']['fflags'] == [3, 11, 3] and result['numerical']['performance_baseline'] is False and
        result['legacy_work']['commands'] == 247 and result['legacy_work']['per_call'] == [237, 4, 6] and
        len(result['resident_work']) == len(result['vector_work']) == 22 and
        result['actual_entries'] == dict(akv_decode_execute=6, akv_experimental_attention_execute_v2_native=4),
        'Incomplete/incorrect frozen SDK checker result')


def checked_protocol(proof, soc, sw, log, vector, old):
    old.check_protocol(proof, soc, sw, log, vector)
    b.require(all(proof.get('contract_counts', {}).get(k) == 0 for k in
                  ('exceptions', 'protocol_errors', 'outstanding')),
              'SDK functional gate requires zero exceptions/protocol errors/outstanding')


STEPS = (('image_contract', 'image-contract', 180), ('simulation', 'console', SIM_SECONDS),
         ('sdk', 'sdk', SDK_SECONDS), ('protocol', 'protocol', PROTOCOL_SECONDS))


def execution_receipts(out, s):
    for command, name, seconds in STEPS:
        b.require(b.read(out/'work'/(name+'.command.json')) == dict(argv=s['commands'][command],
            cwd=str(out/'work'), timeout_seconds=seconds), 'Executed recipe differs: '+command)
    owner = b.read(out/'owner.json')
    b.require(owner['unit'] == service_unit(out) and b.read(out/'attempt.json') ==
        dict(review_sha256=b.sha(out/'source-pins.json'), **owner), 'Attempt/ownership identity mismatch')
    b.direct_owner(owner['cgroup'], owner['unit'], owner['main_pid'], owner['owner_pid'])


def run(out, review, parent_reviewed):
    out = output_path(out)
    b.require(parent_reviewed and Path(__file__).resolve() == out/'inputs/run.py',
              'Parent-reviewed frozen worker required')
    owner = b.claim_attempt(out, review, service_unit(out), terminal='result.json')
    report = dict(state='FAIL', numerical_checked=False, independent_protocol_checked=False,
        actual_sdk_entries_checked=False, work_checked=False, automatic_retry=False,
        performance_measured=False, performance_acceptance=False, deployment_approved=False, whole_model=False)
    status = dict(state='PREFLIGHT', child_pid=None, **owner)
    try:
        b.require(not any((out/'work').iterdir()), 'Stale work; never retry')
        s, pins, soc, sw, old = verify_prepared(out)
        os.environ.clear()
        os.environ.update(s['environment'])
        base, _ = b.helpers(Path(s['soc_build'])/'inputs')
        start = time.monotonic()
        log, vector, commit = (out/'work'/name for name in ('run.vcs.log', 'vector_trace.csv', 'commit.csv'))
        for command, name, seconds in STEPS:
            base.execute(s['commands'][command], out/'work', out/'work'/(name+'.log'),
                         seconds, status, out/'status.json', command.upper())
            if command == 'simulation':
                old.successful_log(log.read_text())
                io_pins = {str(p): b.sha(p) for p in (Path(sw['elf']), log, vector, commit)}
            if command in ('sdk', 'protocol'):
                b.verify(io_pins)
        result = b.read(out/'work/sdk.log')
        checked_sdk(result, sw)
        checked_protocol(b.read(out/'work/uvm_result.json'), soc, sw, log, vector, old)
        execution_receipts(out, s)
        verify_prepared(out)
        b.require(b.sha(out/'source-pins.json') == review, 'Reviewed pins changed')
        report.update(state='PASS', numerical_checked=True, independent_protocol_checked=True,
            actual_sdk_entries_checked=True, work_checked=True, post_pins_match=True, post_image_match=True,
            source_pins_sha256=review, image_pins=soc['image_pins'], elf_sha256=sw['elf_sha256'],
            scope=sw['scope'], checked=result, execution_wall_seconds=time.monotonic()-start,
            checker_io_sha256=io_pins | {str(out/'work/sdk.log'): b.sha(out/'work/sdk.log')})
    except BaseException as exc:
        report['error'] = repr(exc)
    report['artifacts'] = b.files(out, exclude=('status.json', 'service.stdout.log', 'service.stderr.log'))
    b.save(out/'result.json', report)
    status.update(state=report['state'], child_pid=None)
    base, _ = b.helpers()
    base.save(out/'status.json', status)
    print(json.dumps(dict(state=report['state'], output=str(out))), flush=True)
    return int(report['state'] != 'PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='action', required=True)
    for name in ('prepare', 'preflight', 'service-command', 'run'):
        p = sub.add_parser(name, allow_abbrev=False)
        p.add_argument('--output', type=Path, required=True)
        if name == 'prepare': p.add_argument('--soc-build', type=Path, required=True)
        if name in ('service-command', 'run'): p.add_argument('--review-sha256', required=True)
        if name == 'run': p.add_argument('--parent-reviewed', action='store_true')
    args = parser.parse_args()
    out = output_path(args.output)
    if args.action == 'prepare': print(json.dumps(prepare(out, args.soc_build), indent=2))
    elif args.action == 'preflight':
        verify_prepared(out)
        print('PREFLIGHT_PASS_NOT_EXECUTED')
    elif args.action == 'service-command': print(shlex.join(service_command(out, args.review_sha256)))
    else: return run(out, args.review_sha256, args.parent_reviewed)
    return 0


if __name__ == '__main__':
    def interrupted(sig, _frame):
        raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGTERM, signal.SIGINT): signal.signal(sig, interrupted)
    raise SystemExit(main())
