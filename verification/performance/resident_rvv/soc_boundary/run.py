#!/usr/bin/env python3
"""One frozen boundary ELF, direct systemd owner, prepare without simulation."""
import argparse
import csv
from datetime import datetime, timezone
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
ROOT = Path('/home/wangwy/openproject/ara_dsa')
HERE = ROOT/'verification/performance/resident_rvv/soc_boundary'
SMOKE = HERE.parent/'soc_eval/run_smoke.py'
SMOKE_SHA = '5cad3e1cf352e3b0c465bc6844de3c190203983c8cc02f48180f8c21bf58173c'
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
BUILD = OUT/'resident_pv_soc_boundary_build_20261109_02'
SOC = OUT/'resident_pv_soc_build_20261109_03'
BUILD_SHA = '7a6ba64e77c7fa4d6ce52602d992484d83c8b844d631dfd4cd9f2d8c41fb751c'
BUILD_PINS_SHA = '0251754fc49780a6279264ab9afec926728b8e4a6e3fd8f2b6af55c77c7baf4b'
ELF_SHA = '6f5ac1eee0cd9a69a19ae02df55dc900dc490efd8af008e6d780a6dd156f30d5'
OWN = ('run.py', 'test_run.py', 'RUN.md')
SCOPED_CHECKER = HERE/'check_vcs.py'
SCOPED_TEST = HERE/'test_check_vcs.py'
CHECKER_SHA = '6a30948ddf58b08f3a9233b589d88dfee029bcd973facc2e2ee5ac2a3e3fef9e'
CHECKER_TEST_SHA = '9f46cfaedc95e426e8ec3744723f1477442706dcd5ce09680a8bf9a3b6e77b0d'
SIM_SECONDS, PROTOCOL_SECONDS, SERVICE_SECONDS = 5400, 900, 7200
BOUNDARY_SECONDS = 300


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Check the reused owner/image/execution helper before importing executable code.
import hashlib
if hashlib.sha256(SMOKE.read_bytes()).hexdigest() != SMOKE_SHA:
    raise ValueError('Sealed smoke runner drift')
smoke = load(SMOKE, 'boundary_frozen_smoke_runner')
e = smoke.e
require, sha, save, execute = e.require, smoke.sha, e.save, smoke.execute
sys.path.insert(0, str(HERE))
for name, digest in {'cases.py': 'd0fbd2d09179a99ce4fe0d8272f14b7e212d878a1b9a12a1608a1591074c375d',
                     'check.py': '095711476870d724f54639627ea535f934a6fac27c319c54e37387bc3d4a8fd0',
                     'generate.py': '71a0b3682e592cbe7c4c0db296c50e81303382bf95f948a01011c5a8db3c8a74'}.items():
    require(sha(HERE/name) == digest, 'Sealed boundary helper drift: '+name)
import cases
sys.path.insert(0, str(ROOT/'verification'))
from ara_verify import uvm_dut


def verify_software(build, soc):
    build = Path(build).resolve()
    require(build == BUILD and sha(build/'build.json') == BUILD_SHA and
            sha(build/'source-pins.json') == BUILD_PINS_SHA, 'Only reviewed boundary build02 is allowed')
    m = json.loads((build/'build.json').read_text())
    require(m['state'] == 'BOUNDARY_SOFTWARE_BUILT_NOT_EXECUTED' and m['execution'] == 'NOT_RUN'
            and m['eda_started'] is False and m['hardware_acceptance'] is False and m['post_pins_match'] is True,
            'No successful boundary software freeze')
    require((m['pv_scenarios'], m['compat_postludes'], m['successful_pv'], m['rejected_pv']) == (21, 1, 21, 12)
            and m['soc_build'] == str(SOC) and m['configuration'] == soc['configuration']
            and m['image_pins'] == soc['image_pins'], 'Wrong boundary/image pairing')
    require(m['source_pins_sha256'] == BUILD_PINS_SHA and m['elf'] == str(build/'resident_pv_boundary.elf')
            and m['elf_sha256'] == ELF_SHA == sha(m['elf']), 'Boundary ELF identity drift')
    pins = json.loads((build/'source-pins.json').read_text())
    e.contract.verify(pins)
    members = [p for p in build.rglob('*') if p.is_file() and p.name != 'build.json']
    require(all(not p.is_symlink() for p in build.rglob('*')) and
            {str(p): sha(p) for p in members} == m['artifacts'], 'Boundary artifact inventory drift')
    e.merge(pins, m['artifacts'])
    e.merge(pins, {str(build/'build.json'): BUILD_SHA})
    return m, pins


def collect(socdir=SOC, build=BUILD):
    require(bool(CHECKER_SHA) and SCOPED_CHECKER.is_file() and sha(SCOPED_CHECKER) == CHECKER_SHA,
            'LAUNCH BLOCKED: reviewed RVFI-aware check_vcs.py is required; old check.py is forbidden')
    require(bool(CHECKER_TEST_SHA) and SCOPED_TEST.is_file() and sha(SCOPED_TEST) == CHECKER_TEST_SHA,
            'LAUNCH BLOCKED: reviewed successor tests are required')
    require(Path(socdir).resolve() == SOC, 'Only immutable SoC03 is allowed')
    soc, pins = e.checked_soc(SOC)
    software, extra = verify_software(build, soc)
    e.merge(pins, extra)
    inventory = smoke.checker_inventory()
    e.merge(pins, inventory)
    e.merge(pins, {str(SMOKE): SMOKE_SHA})
    e.merge(pins, {str(SCOPED_CHECKER): CHECKER_SHA, str(SCOPED_TEST): CHECKER_TEST_SHA})
    e.merge(pins, {str(p): sha(p) for p in (smoke.IMAGE_CHECK, Path(sys.executable).resolve(),
        Path('/usr/bin/bash').resolve(), Path('/usr/bin/readelf').resolve(),
        Path('/usr/bin/systemctl').resolve(), Path('/usr/bin/systemd-run').resolve(), *(HERE/n for n in OWN))})
    e.contract.verify(pins)
    return soc, software, pins, inventory


def recipes(out, soc, software, python):
    work = out/'work'
    result = smoke.recipes(out, soc, software, python)
    result['simulation'] = [x.replace('+TESTCASE=resident_pv_soc_smoke', '+TESTCASE=resident_pv_soc_boundary')
                            for x in result['simulation']]
    result['boundary'] = [python, '-B', str(SCOPED_CHECKER), '--build', software_build(software),
                         '--log', str(work/'run.vcs.log'), '--vector', str(work/'vector_trace.csv'),
                         '--commit', str(work/'commit.csv')]
    return result


def software_build(software):
    return str(Path(software['elf']).parent)


def output_path(path):
    out = Path(path).resolve()
    require(out.parent == OUT and re.fullmatch('resident_pv_soc_boundary_vcs_[A-Za-z0-9_-]{1,100}', out.name),
            'Use a fresh direct signoff boundary output')
    return out


def selection(out, soc, software, inventory, env):
    return dict(schema='resident-pv-boundary-run-v1', soc_build=str(SOC), build=str(BUILD),
        build_receipt_sha256=BUILD_SHA, commands=recipes(out, soc, software, str(Path(sys.executable).resolve())),
        environment=env, checker_inventory=inventory, sim_seconds=SIM_SECONDS,
        protocol_seconds=PROTOCOL_SECONDS, service_seconds=SERVICE_SECONDS,
        pv_scenarios=21, pv_attempts=33, expected_handler_traps=12, expected_accelerator_exceptions=10,
        compat_postludes=1, automatic_retry=False, automatic_abba=False)


def frozen_receipt(out):
    return dict(state='PREPARED_BOUNDARY_NOT_EXECUTED', execution='NOT_RUN', parent_review_required=True,
                source_pins_sha256=sha(out/'source-pins.json'))


def verify_prepared(out):
    out = output_path(out)
    require(json.loads((out/'prepared.json').read_text()) == frozen_receipt(out), 'Prepared receipt drift')
    pins = json.loads((out/'source-pins.json').read_text())
    e.contract.verify(pins)
    s = json.loads((out/'selection.json').read_text())
    soc, software, mandatory, inventory = collect(Path(s['soc_build']), Path(s['build']))
    require(all(pins.get(p) == h for p, h in mandatory.items()), 'Missing mandatory input pin')
    require(s == selection(out, soc, software, inventory, s['environment']), 'Unreviewed selection/checker inventory')
    require({p.name for p in (out/'inputs').iterdir()} == set(OWN), 'Unexpected frozen runner input')
    for name in OWN:
        require(pins.get(str(out/'inputs'/name)) == pins.get(str(HERE/name)) == sha(out/'inputs'/name),
                'Frozen runner/document drift')
    for name in ('selection.json', 'host-tests.log', 'host-tests.command.json',
                 'scoped-tests.log', 'scoped-tests.command.json',
                 'image-contract.log', 'image-contract.command.json'):
        require(pins.get(str(out/name)) == sha(out/name), 'Unpinned preflight evidence')
    return s, pins, soc, software


def prepare(out):
    require(Path(__file__).resolve() == HERE/'run.py', 'Prepare using the reviewed original runner')
    out = output_path(out)
    require(not out.exists(), 'Preserve all attempts; use a fresh output')
    out.mkdir()
    (out/'work').mkdir()
    status = dict(state='PREFLIGHT', owner_pid=os.getpid(), child_pid=None, execution='NOT_RUN')
    report = dict(state='FAIL', execution='NOT_RUN', performance_measured=False)
    try:
        soc, software, pins, inventory = collect()
        (out/'inputs').mkdir()
        for name in OWN:
            dest = out/'inputs'/name
            shutil.copyfile(HERE/name, dest)
            dest.chmod(0o444)
            e.merge(pins, {str(dest): sha(dest)})
        env = smoke.environment()
        s = selection(out, soc, software, inventory, env)
        save(out/'selection.json', s)
        e.merge(pins, {str(out/'selection.json'): sha(out/'selection.json')})
        os.environ.clear()
        os.environ.update(env)
        execute([str(Path(sys.executable).resolve()), '-B', str(out/'inputs/test_run.py'), '-v'], out/'inputs',
                out/'host-tests.log', 120, status, out/'status.json', 'HOST_TESTS')
        execute([str(Path(sys.executable).resolve()), '-B', str(SCOPED_TEST), '-v'], out/'inputs',
                out/'scoped-tests.log', 120, status, out/'status.json', 'SCOPED_HOST_TESTS')
        execute(s['commands']['image_contract'], out/'work', out/'image-contract.log', 180,
                status, out/'status.json', 'IMAGE_CONTRACT')
        require(smoke.checker_inventory() == inventory, 'Protocol checker inventory drift')
        e.contract.verify(pins)
        e.merge(pins, {str(out/n): sha(out/n) for n in ('host-tests.log', 'host-tests.command.json',
                       'scoped-tests.log', 'scoped-tests.command.json',
                       'image-contract.log', 'image-contract.command.json')})
        save(out/'source-pins.json', pins)
        save(out/'prepared.json', frozen_receipt(out))
        verify_prepared(out)
        report.update(frozen_receipt(out))
    except BaseException as exc:
        report['error'] = repr(exc)
    save(out/'prepare-report.json', report)
    status.update(state=report['state'], child_pid=None)
    smoke.status_save(out/'status.json', status)
    require(report['state'] == 'PREPARED_BOUNDARY_NOT_EXECUTED', 'Prepare failed; retained '+str(out))
    return report


def scoped_illegals(text, commit, vectors, software, proof):
    """No illegal RVFI retire is invented; handler evidence belongs to check_vcs."""
    specs = cases.attempts(vectors['cases'])
    with Path(commit).open(newline='') as stream:
        retired = [r for r in csv.DictReader(stream) if r['event'] == 'retire' and
                   int(r['insn'], 16) & 0x707f == 0x705b and int(r['insn'], 16) >> 25 == 2]
    require(len(retired) == 21 and all(int(r['trap']) == 0 and int(r['insn'], 16) == cases.PV_INSN
            and int(r['pc'], 16) == software['fault_pc'][str(cases.PV_INSN)] for r in retired),
            'RVFI must contain 21 successful PV retires, not synthetic illegal retires')
    events, issues = uvm_dut._events(text, '[ARA_CONTRACT_TRACE]', uvm_dut._CONTRACT_EVENT, 16)
    require(not issues and events, 'Malformed/missing independent contract events')
    pending, transactions = {}, []
    for cycle, req, rid, insn, resp, sid, exc in events:
        old = pending.pop(sid) if resp and sid in pending else None
        if req:
            require(rid not in pending, 'Duplicate outstanding CVXIF ID')
            current = dict(instruction=insn, error=None, request_cycle=cycle)
            pending[rid] = current
            transactions.append(current)
        if resp:
            owner = old if old is not None else pending.pop(sid, None)
            require(owner is not None, 'Orphan CVXIF exception/response')
            owner.update(error=exc, response_cycle=cycle)
    require(not pending, 'Unreturned scoped CVXIF transaction')
    def pv(insn):
        return insn & 0x707f == 0x705b and insn >> 25 == 2
    pv_transactions = [r for r in transactions if pv(r['instruction'])]
    expected = [s for s in specs if not (s['error'] and s['kind'] in ('fs_off', 'vs_off'))]
    require(len(pv_transactions) == len(expected) == 31 and
            all((r['instruction'], r['error']) == (s['instruction'], s['error'])
                for r, s in zip(pv_transactions, expected)), 'PV exception/request scope mismatch')
    require(all(r['error'] == 0 for r in transactions if not pv(r['instruction'])) and
            proof['contract_counts']['exceptions'] == sum(r['error'] for r in transactions) == 10,
            'Exception outside the ten allowed accelerator PV rejections')
    return dict(successful_pv_retires=21, accelerator_exceptions=10, cpu_only_fs_vs_cases=2,
                trap_handler_audit='check_vcs.py required separately', issues_ignored=0)


def service_unit(out):
    return 'resident-pv-boundary-'+out.name+'.service'


def service_command(out, review):
    verify_prepared(out)
    require(review == sha(out/'source-pins.json'), 'Parent review hash mismatch')
    return ['/usr/bin/systemd-run', '--user', '--unit='+service_unit(out),
        '--property=WorkingDirectory='+str(out/'work'), '--property=RuntimeMaxSec='+str(SERVICE_SECONDS),
        '--property=KillMode=control-group', '--property=TimeoutStopSec=20',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        str(Path(sys.executable).resolve()), '-B', '-u', str(out/'inputs/run.py'),
        'run', '--output', str(out), '--parent-reviewed', '--review-sha256', review]


def run(out, reviewed, review):
    out = output_path(out)
    require(reviewed and review == sha(out/'source-pins.json'), 'Explicit parent bundle review required')
    require(Path(__file__).resolve() == out/'inputs/run.py', 'Execute the frozen worker, not live source')
    require(not (out/'result.json').exists(), 'Execution already terminated; no retries')
    with (out/'attempt.json').open('x') as f:
        json.dump(dict(owner_pid=os.getpid(), review_sha256=review), f)
    status = dict(state='PREFLIGHT', owner_pid=os.getpid(), child_pid=None, unit=service_unit(out),
                  started=datetime.now(timezone.utc).isoformat())
    result = dict(state='FAIL', performance_measured=False, numerical_checked=False,
                  independent_protocol_checked=False, automatic_retry=False, deployment_approved=False)
    try:
        cgroup = Path('/proc/self/cgroup').read_text().strip().splitlines()[-1].split(':', 2)[-1]
        main_pid = int(subprocess.check_output(['/usr/bin/systemctl', '--user', 'show', service_unit(out),
                       '--property=MainPID', '--value'], text=True, timeout=10).strip())
        smoke.direct_owner(cgroup, service_unit(out), main_pid, os.getpid())
        save(out/'owner.json', dict(main_pid=main_pid, owner_pid=os.getpid(), cgroup=cgroup))
        require(not any((out/'work').iterdir()), 'Preserve old work; no repeat execution')
        s, pins, soc, software = verify_prepared(out)
        os.environ.clear()
        os.environ.update(s['environment'])
        execute(s['commands']['image_contract'], out/'work', out/'run-image-contract.log', 180,
                status, out/'status.json', 'IMAGE_CONTRACT')
        e.contract.verify(pins)
        start = time.monotonic()
        execute(s['commands']['simulation'], out/'work', out/'work/console.log', SIM_SECONDS,
                status, out/'status.json', 'RUNNING')
        wall = time.monotonic()-start
        work = out/'work'
        log, vector, commit = work/'run.vcs.log', work/'vector_trace.csv', work/'commit.csv'
        text = log.read_text()
        # Do not apply a blanket trap prohibition or edit/filter simulator output.
        require(text.count('Core Test *** SUCCESS ***') == 1, 'Missing/duplicate successful EOC')
        execute(s['commands']['protocol'], work, work/'protocol.log', PROTOCOL_SECONDS,
                status, out/'status.json', 'PROTOCOL_CHECK')
        proof = json.loads((work/'uvm_result.json').read_text())
        smoke.check_protocol(proof, soc, software, log, vector)
        execute(s['commands']['boundary'], work, work/'boundary.log', BOUNDARY_SECONDS,
                status, out/'status.json', 'BOUNDARY_CHECK')
        numeric = json.loads((work/'boundary.log').read_text())
        require(numeric['schema'] == 'resident-pv-soc-boundary-vcs-v1' and
                numeric['numerical']['numerical_checked'] is True and numeric['protocol_checked'] is False,
                'Boundary supplement scope drift')
        arch = numeric['trap_architecture']
        require(all(arch[k] == v for k, v in dict(successful_pv_retirements=21, faulting_pv_retirements=0,
                    real_csr_trap_groups=12, pv_arch_start=31, fs_vs_off_without_arch_start=2,
                    actual_fill_retirements=22, actual_release_retirements=22).items()),
                'Successor did not check the actual RVFI/handler convention')
        require(all(numeric['evidence_sha256'].get(str(p)) == sha(p) for p in
                    (log, vector, commit, Path(software['elf']), BUILD/'build.json', BUILD/'source-pins.json',
                     SCOPED_CHECKER, SCOPED_TEST)), 'Boundary evidence identity mismatch')
        vectors = json.loads((BUILD/'vectors/vectors.json').read_text())
        negative = scoped_illegals(text, commit, vectors, software, proof)
        require(sha(out/'source-pins.json') == review, 'Reviewed inventory drift')
        e.contract.verify(pins)
        post, _, _, _ = verify_prepared(out)
        require(post == s and sha(out/'source-pins.json') == review, 'Selection/inventory drift')
        result.update(state='PASS', numerical_checked=True, independent_protocol_checked=True,
            negative_scope=negative, boundary=numeric, post_pins_match=True, post_image_match=True,
            source_pins_sha256=review, image_pins=soc['image_pins'], elf_sha256=software['elf_sha256'],
            simulation_wall_seconds=wall, pv_scenarios=21, pv_attempts=33, compat_postludes=1)
    except BaseException as exc:
        result.update(state='TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else 'FAIL', error=repr(exc))
    try:
        result['artifacts'] = {str(p): sha(p) for p in out.rglob('*') if p.is_file() and
            p.name not in ('status.json', 'service.stdout.log', 'service.stderr.log', 'result.json')}
    except BaseException as exc:
        result.update(state='FAIL', artifact_error=repr(exc))
    save(out/'result.json', result)
    status.update(state=result['state'], child_pid=None, finished=datetime.now(timezone.utc).isoformat())
    smoke.status_save(out/'status.json', status)
    print(json.dumps(dict(state=result['state'], output=str(out))), flush=True)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = p.add_subparsers(dest='action', required=True)
    for action in ('prepare', 'preflight', 'service-command', 'run'):
        s = sub.add_parser(action, allow_abbrev=False)
        s.add_argument('--output', type=Path, required=True)
        if action in ('service-command', 'run'): s.add_argument('--review-sha256', required=True)
        if action == 'run': s.add_argument('--parent-reviewed', action='store_true')
    a = p.parse_args(argv)
    out = output_path(a.output)
    if a.action == 'prepare': print(json.dumps(prepare(out), indent=2))
    elif a.action == 'preflight':
        verify_prepared(out)
        print('PREFLIGHT_PASS_NOT_EXECUTED')
    elif a.action == 'service-command': print(shlex.join(service_command(out, a.review_sha256)))
    else: return int(run(out, a.parent_reviewed, a.review_sha256)['state'] != 'PASS')
    return 0


if __name__ == '__main__':
    def interrupted(sig, _frame):
        raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGTERM, signal.SIGINT): signal.signal(sig, interrupted)
    sys.exit(main())
