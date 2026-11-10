#!/usr/bin/env python3
"""Pair immutable PV Build02 with a reviewed stage-3 image; never relax checkers."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('stage3_boundary_build_contract', HERE/'build_soc.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
ROOT, OUT = b.ROOT, b.OUT
BOUNDARY = ROOT/'verification/performance/resident_rvv/soc_boundary'
BUILD = OUT/'resident_pv_soc_boundary_build_20261109_02'
FAILED = OUT/'resident_pv_soc_boundary_vcs_20261109_01'
ELF_SHA = '6f5ac1eee0cd9a69a19ae02df55dc900dc490efd8af008e6d780a6dd156f30d5'
ANCHORS = {
    BUILD/'build.json': '7a6ba64e77c7fa4d6ce52602d992484d83c8b844d631dfd4cd9f2d8c41fb751c',
    BUILD/'source-pins.json': '0251754fc49780a6279264ab9afec926728b8e4a6e3fd8f2b6af55c77c7baf4b',
    FAILED/'source-pins.json': '37a54491741127d5fd73eeb65c041606cc23e8d103a22d4beb74095afe600bfc',
    FAILED/'result.json': 'a6388d89233192eceffe5ebaf08171efc89a8ea1a86f5b1e4704898217439749',
}
OWN = ('run_boundary.py', 'test_run_boundary.py', 'build_soc.py')
# Only modules actually imported by the reused checkers, not historical RTL,
# documentation, unrelated Python tools, or old simulator source inventories.
LEGACY = (
    'verification/performance/chain_profile/build_soc.py',
    'verification/performance/chain_profile/run_case.py',
    'verification/performance/akv_pair_eval/integration/build.py',
    'verification/performance/akv_pair_eval/integration/check.py',
    'verification/performance/resident_rvv/soc_eval/experiment.py',
    'verification/performance/resident_rvv/soc_eval/run_smoke.py',
    'verification/performance/resident_rvv/soc_boundary/run.py',
    'verification/performance/resident_rvv/soc_boundary/cases.py',
    'verification/performance/resident_rvv/soc_boundary/generate.py',
    'verification/performance/resident_rvv/soc_boundary/check.py',
    'verification/performance/resident_rvv/soc_boundary/check_vcs.py',
    'verification/performance/resident_rvv/soc_boundary/test_check_vcs.py',
    'verification/performance/resident_rvv/soc_boundary/test_boundary.py',
    'verification/ara_verify/__init__.py', 'verification/ara_verify/catalog.py',
    'verification/ara_verify/model.py', 'verification/ara_verify/artifacts.py',
    'verification/ara_verify/contract.py', 'verification/ara_verify/uvm_dut.py',
    'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
)


def legacy_inventory():
    b.verify({FAILED/'source-pins.json': ANCHORS[FAILED/'source-pins.json']})
    old = b.read(FAILED/'source-pins.json')
    pins = {str(ROOT/p): old[str(ROOT/p)] for p in LEGACY}
    b.verify(pins)
    return pins


def legacy():
    pins = legacy_inventory()
    # The sealed runner imports "build_soc" by basename. Isolate that import
    # from this successor's same-named module without modifying either checker.
    previous, search = sys.modules.get('build_soc'), list(sys.path)
    chain = ROOT/'verification/performance/chain_profile/build_soc.py'
    sys.modules['build_soc'] = b.load(chain, 'boundary_sealed_chain', pins[str(chain)])
    try:
        runner = b.load(BOUNDARY/'run.py', 'stage3_sealed_boundary', pins[str(BOUNDARY/'run.py')])
        checker = b.load(BOUNDARY/'check_vcs.py', 'stage3_sealed_vcs', pins[str(BOUNDARY/'check_vcs.py')])
    finally:
        sys.path[:] = search
        if previous is None:
            sys.modules.pop('build_soc', None)
        else:
            sys.modules['build_soc'] = previous
    return runner, checker, pins


def software():
    b.verify(ANCHORS)
    receipt = b.read(BUILD/'build.json')
    b.require(all(receipt.get(k) == v for k, v in dict(
        state='BOUNDARY_SOFTWARE_BUILT_NOT_EXECUTED', execution='NOT_RUN', eda_started=False,
        hardware_acceptance=False, post_pins_match=True, pv_scenarios=21, compat_postludes=1,
        successful_pv=21, rejected_pv=12, source_pins_sha256=ANCHORS[BUILD/'source-pins.json'],
        elf=str(BUILD/'resident_pv_boundary.elf'), elf_sha256=ELF_SHA).items()),
        'Not the immutable original boundary firmware')
    b.require(b.sha(receipt['elf']) == ELF_SHA, 'Original ELF drift')
    b.exact_files(BUILD, receipt['artifacts'], exclude=('build.json',))
    _, checker, checkpins = legacy()
    contract = checker.elf_contract(Path(receipt['elf']).read_bytes())
    b.require(contract['fault_pc'] == receipt['fault_pc'], 'Original symbol/PC drift')
    vectors = b.read(BUILD/'vectors/vectors.json')
    pins = {str(p): h for p, h in ANCHORS.items()} | receipt['artifacts'] | checkpins
    # Original build.json and source-pins.json remain unmodified evidence.
    # Their inherited live hardware paths are not inputs to this new pairing.
    return receipt, vectors, contract, pins


def collect(socdir):
    socdir = b.output_path(socdir)
    soc, pins = b.checked_build(socdir)
    sw, vectors, contract, extra = software()
    pins.update(extra)
    b.require(b.sha(HERE/'build_soc.py') == b.sha(socdir/'inputs/build_soc.py'),
              'Use the same reviewed build contract as the compiled image')
    for path in (Path(sys.executable).resolve(), Path('/usr/bin/bash').resolve(),
                 Path('/usr/bin/readelf').resolve(), Path('/usr/bin/systemctl').resolve(),
                 Path('/usr/bin/systemd-run').resolve()):
        pins[str(path)] = b.sha(path)
    b.verify(pins)
    return soc, sw, vectors, contract, pins


def output_path(path):
    return b.output_path(path, 'stage3_pv_boundary_')


def selection(out, socdir, soc, sw, env, python):
    old, _, _ = legacy()
    commands = old.recipes(out, soc, sw, python)
    commands['boundary'] = [python, '-B', str(out/'inputs/run_boundary.py'),
                            'check', '--output', str(out)]
    return dict(schema='stage3-original-pv-boundary-v1', soc_build=str(socdir),
        soc_receipt_sha256=b.sha(socdir/'build.json'), original_build=str(BUILD),
        original_build_sha256=ANCHORS[BUILD/'build.json'], elf_sha256=ELF_SHA,
        historical_failure=str(FAILED), historical_failure_unchanged=True,
        configuration=soc['configuration'], image_contract=soc['image_contract'],
        image_pins=soc['image_pins'], cpu_overlay=soc['cpu_overlay'],
        commands=commands, environment=env, python=python, sim_seconds=5400,
        protocol_seconds=900, boundary_seconds=300, service_seconds=7200,
        pv_scenarios=21, pv_attempts=33, compat_postludes=1, automatic_retry=False,
        identity_adapter_only=True, numerical_and_protocol_checkers_unchanged=True)


def prepare(out, socdir):
    out, socdir = output_path(out), b.output_path(socdir)
    b.require(not out.exists(), 'Preserve every prior attempt')
    soc, sw, _, _, pins = collect(socdir)
    old, _, _ = legacy()
    out.mkdir()
    (out/'inputs').mkdir()
    (out/'work').mkdir()
    for name in OWN:
        shutil.copyfile(HERE/name, out/'inputs'/name)
    env = old.smoke.environment()
    plan = selection(out, socdir, soc, sw, env, str(Path(sys.executable).resolve()))
    b.save(out/'selection.json', plan)
    pins.update(b.files(out/'inputs'))
    pins[str(out/'selection.json')] = b.sha(out/'selection.json')
    b.verify(pins)
    b.save(out/'source-pins.json', pins)
    b.save(out/'prepared.json', dict(state='PREPARED_BOUNDARY_NOT_EXECUTED',
                                   source_pins_sha256=b.sha(out/'source-pins.json')))
    verify_prepared(out)
    return plan


def verify_prepared(out):
    out = output_path(out)
    pins, plan = b.read(out/'source-pins.json'), b.read(out/'selection.json')
    b.require(b.read(out/'prepared.json') == dict(state='PREPARED_BOUNDARY_NOT_EXECUTED',
        source_pins_sha256=b.sha(out/'source-pins.json')), 'Prepared boundary receipt drift')
    b.verify(pins)
    socdir = b.output_path(plan['soc_build'])
    soc, sw, vectors, contract, mandatory = collect(socdir)
    b.require(plan == selection(out, socdir, soc, sw, plan['environment'], plan['python']),
              'Boundary pairing/commands drift')
    b.require(plan['python'] == str(Path(sys.executable).resolve()), 'Unexpected Python interpreter')
    frozen = b.files(out/'inputs')
    b.require(set(frozen) == {str(out/'inputs'/n) for n in OWN}, 'Extra/missing runner input')
    mandatory.update(frozen)
    mandatory[str(out/'selection.json')] = b.sha(out/'selection.json')
    b.require(all(pins.get(p) == h for p, h in mandatory.items()), 'Missing boundary input pin')
    return plan, pins, soc, sw, vectors, contract


def check(out):
    _, pins, _, sw, vectors, contract = verify_prepared(out)
    _, checker, _ = legacy()
    log, vector, commit = (out/'work'/n for n in ('run.vcs.log', 'vector_trace.csv', 'commit.csv'))
    evidence = {str(p): b.sha(p) for p in (log, vector, commit, Path(sw['elf']),
        BUILD/'build.json', BUILD/'source-pins.json', BUILD/'vectors/vectors.json',
        BOUNDARY/'check.py', BOUNDARY/'check_vcs.py', BOUNDARY/'test_check_vcs.py')}
    text = log.read_text()
    numerical = checker.old.check_log(text, vectors, contract['fault_pc'])
    work, architecture = checker.check_work(vector, commit, text, vectors, contract)
    b.verify(pins | evidence)
    return dict(schema='resident-pv-soc-boundary-vcs-v1', numerical=numerical, work=work,
        trap_architecture=architecture, evidence_sha256=evidence, protocol_checked=False,
        identity_adapter='stage3-original-pv-boundary-v1')


def service_unit(out):
    return 'stage3-boundary-'+out.name+'.service'


def service_command(out, review):
    plan, *_ = verify_prepared(out)
    b.require(review == b.sha(out/'source-pins.json'), 'Parent review hash mismatch')
    b.require(not (out/'attempt.json').exists() and not (out/'result.json').exists(), 'Already attempted')
    return ['/usr/bin/systemd-run', '--user', '--unit='+service_unit(out),
        '--property=WorkingDirectory='+str(out/'work'), '--property=RuntimeMaxSec=7200',
        '--property=KillMode=control-group', '--property=TimeoutStopSec=20',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        plan['python'], '-B', '-u', str(out/'inputs/run_boundary.py'), 'run',
        '--output', str(out), '--review-sha256', review]


def run(out, review):
    out = output_path(out)
    b.require(Path(__file__).resolve() == out/'inputs/run_boundary.py', 'Execute frozen runner')
    ownership = b.claim_attempt(out, review, service_unit(out), terminal='result.json')
    base, _ = b.helpers()
    status = dict(state='PREFLIGHT', child_pid=None, **ownership)
    result = dict(state='FAIL', numerical_checked=False, independent_protocol_checked=False,
        performance_measured=False, deployment_approved=False, automatic_retry=False,
        historical_failure=str(FAILED), identity_adapter_only=True)
    try:
        b.require(not any((out/'work').iterdir()), 'Preserve stale work; no retry')
        plan, pins, soc, sw, vectors, _ = verify_prepared(out)
        old, _, _ = legacy()
        os.environ.clear()
        os.environ.update(plan['environment'])
        # Includes all eleven unchanged strict scoped tests. The twelfth tests
        # the obsolete CLI's live-hardware identity gate, replaced by our adapter.
        base.execute([plan['python'], '-B', str(out/'inputs/test_run_boundary.py')],
                     out/'inputs', out/'host-tests.log', 120, status, out/'status.json', 'HOST_TESTS')
        commands = plan['commands']
        base.execute(commands['image_contract'], out/'work', out/'image-contract.log',
                     180, status, out/'status.json', 'IMAGE_CONTRACT')
        verify_prepared(out)
        base.execute(commands['simulation'], out/'work', out/'work/console.log',
                     5400, status, out/'status.json', 'RUNNING')
        work = out/'work'
        log, vector, commit = (work/n for n in ('run.vcs.log', 'vector_trace.csv', 'commit.csv'))
        text = log.read_text()
        b.require(text.count('Core Test *** SUCCESS ***') == 1, 'Missing/duplicate successful EOC')
        base.execute(commands['protocol'], work, work/'protocol.log',
                     900, status, out/'status.json', 'PROTOCOL_CHECK')
        proof = b.read(work/'uvm_result.json')
        old.smoke.check_protocol(proof, soc, sw, log, vector)
        base.execute(commands['boundary'], work, work/'boundary.log',
                     300, status, out/'status.json', 'BOUNDARY_CHECK')
        numeric = b.read(work/'boundary.log')
        b.require(numeric['schema'] == 'resident-pv-soc-boundary-vcs-v1' and
                  numeric['numerical']['numerical_checked'] is True and
                  numeric['protocol_checked'] is False, 'Boundary supplement scope drift')
        expected = dict(successful_pv_retirements=21, faulting_pv_retirements=0,
            real_csr_trap_groups=12, pv_arch_start=31, fs_vs_off_without_arch_start=2,
            actual_fill_retirements=22, actual_release_retirements=22)
        b.require(all(numeric['trap_architecture'][k] == v for k, v in expected.items()),
                  'Actual RVFI/handler convention drift')
        evidence = numeric['evidence_sha256']
        b.require(all(evidence.get(str(p)) == b.sha(p) for p in (log, vector, commit, Path(sw['elf']),
            BUILD/'build.json', BUILD/'source-pins.json', BUILD/'vectors/vectors.json',
            BOUNDARY/'check.py', BOUNDARY/'check_vcs.py', BOUNDARY/'test_check_vcs.py')),
            'Boundary evidence mismatch')
        negative = old.scoped_illegals(text, commit, vectors, sw, proof)
        verify_prepared(out)
        b.require(b.sha(out/'source-pins.json') == review, 'Reviewed inventory drift')
        result.update(state='PASS', numerical_checked=True, independent_protocol_checked=True,
            boundary=numeric, negative_scope=negative, post_pins_match=True, post_image_match=True,
            source_pins_sha256=review, image_pins=soc['image_pins'], elf_sha256=ELF_SHA,
            pv_scenarios=21, pv_attempts=33, compat_postludes=1)
    except BaseException as exc:
        result['error'] = repr(exc)
    result['artifacts'] = b.files(out, exclude=('status.json', 'service.stdout.log', 'service.stderr.log'))
    b.save(out/'result.json', result)
    status.update(state=result['state'], child_pid=None)
    base.save(out/'status.json', status)
    print(json.dumps(dict(state=result['state'], output=str(out))), flush=True)
    return int(result['state'] != 'PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('prepare', 'preflight', 'service-command', 'run', 'check'):
        p = sub.add_parser(action, allow_abbrev=False)
        p.add_argument('--output', type=Path, required=True)
        if action == 'prepare':
            p.add_argument('--soc-build', type=Path, required=True)
        if action in ('service-command', 'run'):
            p.add_argument('--review-sha256', required=True)
    a = parser.parse_args()
    out = output_path(a.output)
    if a.action == 'prepare':
        prepare(out, a.soc_build)
        print('PREPARED_BOUNDARY_NOT_EXECUTED '+b.sha(out/'source-pins.json'))
    elif a.action == 'preflight':
        verify_prepared(out)
        print('PREFLIGHT_PASS_NOT_EXECUTED')
    elif a.action == 'service-command':
        print(shlex.join(service_command(out, a.review_sha256)))
    elif a.action == 'check':
        print(json.dumps(check(out), indent=2))
    else:
        return run(out, a.review_sha256)
    return 0


if __name__ == '__main__':
    def interrupted(sig, _frame):
        raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    sys.exit(main())
