#!/usr/bin/env python3
"""One reviewed offline audit of a closed CSV; never executes a simulator."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
sys.dont_write_bytecode = True
import checker
base = checker.base
HERE = Path(__file__).resolve().parent
SOURCE = checker.OLD / 'prepared01'
ROOT = SOURCE / 'replay/tests' / base.ID
CSV = ROOT / 'commit_trace.csv'
PLAN_SHA = '4df0c5b631b8645fb51a4ca52ca1bb916dec03ad455e88c0a380a5b023f2c2db'
BOUND = 600
read, sha, need = base.read, base.sha, base.require


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def identity(path):
    st = path.stat()
    return dict(bytes=st.st_size, mtime_ns=st.st_mtime_ns, inode=st.st_ino, device=st.st_dev)


def provenance():
    need(sha(SOURCE / 'plan.json') == PLAN_SHA, 'Sealed original plan drift')
    plan = read(SOURCE / 'plan.json')
    need(len(plan['cases']) == 1 and plan['cases'][0]['id'] == base.ID, 'Original membership')
    complete = read(SOURCE / 'complete.json')
    need(complete['status'] == 'NOT_PASS' and complete['aborted'] is True and complete['retries'] == 0 and
         complete['plan_sha256'] == PLAN_SHA and len(complete['results']) == 1, 'Preserved original terminal')
    child = complete['results'][0]
    need(child['name'] == base.ID and child['status'] == 'ERROR' and child['returncode'] == 0 and
         child['reason'] == "Postcheck ValueError: Missing necessary architectural owner {'insn': 947993687, 'pc': 2147487702, 'retire_order': 771538, 'call': 1200, 'helper_index': 8, 'kind': 'target', 'required': True, 'arch_order': 13209, 'alloc': 0, 'done': 0}",
         'Only the measured owner postcheck rejection is eligible')
    monitor = read(ROOT / 'child_outcome.unvalidated.json')
    need(type(monitor['returncode']) is int and monitor['returncode'] == 0 and
         0 < monitor['elapsed_s'] == child['elapsed_s'] <= 10800 and
         not any(monitor[k] for k in ('timed_out', 'failure_seen', 'cancelled')), 'Durable actual child exit/budget')
    service = read(SOURCE / 'service_exit.json')
    need(service['kind'] == 'SYSTEMD_EXEC_STOP_POST_ACTUAL_ENVIRONMENT' and
         [service[k] for k in ('SERVICE_RESULT', 'EXIT_CODE', 'EXIT_STATUS')] == ['exit-code', 'exited', '1'],
         'Original actual service exit1 remains failure, not rewritten success')
    command = read(ROOT / 'command.json')
    need(monitor['command_sha256'] == sha(ROOT / 'command.json') and
         monitor['command'] == command['command'] and monitor['cwd'] == command['cwd'], 'Monitor actual command')
    ledger, _, _ = base.common.image_context(Path(plan['image']))
    actual = SimpleNamespace(returncode=monitor['returncode'], elapsed_s=monitor['elapsed_s'], artifact_dir=ROOT)
    base.common.check_artifacts(actual, dict(plan['cases'][0], original_name=base.ID), ledger)
    for name in ('console.log', 'work/run.vcs.log'):
        base.console_gate((ROOT / name).read_text())
    need(plan['specs'][base.SHAPE] == base.specification(), 'Original actual ELF specification')
    return plan, monitor, service


def verify(pins):
    base.common.base.verify_pins(pins)


def host():
    need(sha(SOURCE / 'plan.json') == PLAN_SHA, 'Original plan before Host')
    verify(read(SOURCE / 'plan.json')['pins'])
    out = HERE / 'host01'
    out.mkdir()
    pins = {str(HERE / n): sha(HERE / n) for n in ('checker.py', 'test_host.py', 'recovery.py')}
    save(out / 'preflight.json', dict(pins=pins))
    command = [sys.executable, '-B', str(HERE / 'test_host.py')]
    started = time.monotonic()
    timed = False
    with (out / 'output.log').open('x') as stream:
        process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)
        try:
            rc = process.wait(timeout=120)
        except subprocess.TimeoutExpired:
            timed = True
            process.kill()
            rc = process.wait()
    save(out / 'wait.json', dict(command=command, pid=process.pid, actual_wait_returncode=rc,
         elapsed_s=time.monotonic()-started, timed_out=timed, retries=0, pins=pins))
    verify(pins)
    need(rc == 0 and not timed, 'Host failed; preserve output, no automatic retry')
    print('HOST_PASS', flush=True)


def prepare():
    need(not (HERE / 'plan.json').exists(), 'Fresh recovery plan only')
    wait = read(HERE / 'host01/wait.json')
    need(type(wait['actual_wait_returncode']) is int and wait['actual_wait_returncode'] == 0 and
         wait['timed_out'] is False, 'Actual short Host exit')
    verify(wait['pins'])
    original, monitor, service = provenance()
    verify(original['pins'])
    pins = dict(original['pins'])
    # Load all runtime imports before sealing their exact source, including transport.
    base.validate_reset(base.specification())
    for module in list(sys.modules.values()):
        file = getattr(module, '__file__', None)
        if file:
            path = Path(file).resolve()
            if path.is_file() and str(path).startswith('/home/wangwy/'):
                pins[str(path)] = sha(path)
    for name in ('checker.py', 'test_host.py', 'recovery.py', 'README.md',
                 'host01/preflight.json', 'host01/output.log', 'host01/wait.json'):
        pins[str(HERE / name)] = sha(HERE / name)
    for name in ('plan.json', 'complete.json', 'service_exit.json', 'collector_result.json', 'collector_exit.json'):
        pins[str(SOURCE / name)] = sha(SOURCE / name)
    for name in ('input.elf', 'inputs.json', 'command.json', 'child_outcome.unvalidated.json',
                 'console.log', 'work/run.vcs.log', 'trace_summary.json', 'commit_trace.csv'):
        pins[str(ROOT / name)] = sha(ROOT / name)
    frozen = Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/frozen/sources/hardware/src/ara_dispatcher.sv')
    need(sha(frozen) == 'c179ddd08b2bdb8648246f187aa892be5853fda38aeca850402d5e5b9b17ef7d', 'Actual M9 null-slide implementation')
    pins[str(frozen)] = sha(frozen)
    verify(pins)
    plan = dict(status='PREPARED_PENDING_HILBERT_NOT_EXECUTED', original_plan_sha256=PLAN_SHA,
                source=str(SOURCE), csv=str(CSV), csv_identity=identity(CSV), pins=pins,
                audit_timeout_s=BOUND, semantic_passes=1, simulator_runs=0, retries=0,
                original_monitor=monitor, original_service=service,
                required_owners=dict(memory=20475, target=2592, op24=117, total=23067),
                full_scope=dict(calls=4095, results=2096640, guards=8190, vstart=4095,
                                helpers=53235, packed_reads=266175))
    save(HERE / 'plan.json', plan)
    print('PREPARED', sha(HERE / 'plan.json'), 'pins', len(pins), 'CSV bytes', plan['csv_identity']['bytes'], flush=True)


def checked_plan(digest):
    need(sha(HERE / 'plan.json') == digest, 'Recovery plan drift')
    plan = read(HERE / 'plan.json')
    need(plan['audit_timeout_s'] == BOUND and plan['semantic_passes'] == 1 and
         plan['simulator_runs'] == plan['retries'] == 0 and plan['original_plan_sha256'] == PLAN_SHA,
         'Fixed single offline bounds')
    need(identity(CSV) == plan['csv_identity'], 'Closed CSV stat drift')
    verify(plan['pins'])
    return plan


def audit(digest):
    out = HERE / 'fullparse01'
    result = dict(status='NOT_ACCEPTED', started=time.time(), retries=0, DUT_runs=0)
    try:
        plan = checked_plan(digest)
        provenance()
        abort = threading.Event()
        with base.common.abort_signals(abort):
            report = checker.audit(CSV, base.specification(), abort)
            need(report['actual_csv_sha256'] == plan['pins'][str(CSV)], 'Original closed CSV digest')
            checked_plan(digest)
            need(not abort.is_set(), 'Sticky offline abort')
            save(out / 'strict.json', report)
            result.update(status='ARCHITECTURAL_FULL4095_OFFLINE_ACCEPTED_ORIGINAL_SERVICE_FAILED_NOT_LINUX',
                plan_sha256=digest, strict_sha256=sha(out / 'strict.json'),
                csv_sha256=report['actual_csv_sha256'], pins_pre_post_unchanged=True,
                scope=plan['full_scope'], required_owners=plan['required_owners'],
                original_monitor=plan['original_monitor'], original_service=plan['original_service'])
    except BaseException as error:
        result['firstcause'] = type(error).__name__ + ': ' + str(error)
    result['finished'] = time.time()
    save(out / 'result.json', result)
    return 0 if result['status'].startswith('ARCHITECTURAL_FULL4095_OFFLINE_ACCEPTED_') else 1


def run(digest, review_path, review_sha):
    checked_plan(digest)
    need(sha(review_path) == review_sha, 'Independent exact review hash')
    review = read(review_path)
    need(review['status'] == 'NO_BLOCKER_ONE_CLOSED_CSV_RECOVERY_NOT_DUT' and
         review['plan_sha256'] == digest and review['checker_sha256'] == sha(HERE / 'checker.py') and
         review['runner_sha256'] == sha(Path(__file__)) and
         review['host_wait_sha256'] == sha(HERE / 'host01/wait.json'), 'Hilbert exact entry binding')
    out = HERE / 'fullparse01'
    out.mkdir()
    command = [sys.executable, '-B', str(Path(__file__).resolve()), 'audit', '--plan-sha256', digest]
    save(out / 'attempt.json', dict(command=command, plan_sha256=digest, review=str(review_path),
         review_sha256=review_sha, timeout_s=BOUND, max_attempts=1))
    started = time.monotonic()
    timed = False
    with (out / 'output.log').open('x') as stream:
        process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)
        try:
            rc = process.wait(timeout=BOUND)
        except subprocess.TimeoutExpired:
            timed = True
            process.kill()
            rc = process.wait()
    # Persist the actual OS wait before reading or interpreting any audit result.
    save(out / 'wait.json', dict(command=command, pid=process.pid, actual_wait_returncode=rc,
         elapsed_s=time.monotonic()-started, timed_out=timed, retries=0, plan_sha256=digest))
    summary = dict(status='NOT_ACCEPTED', actual_wait_returncode=rc, timed_out=timed,
                   wait_sha256=sha(out / 'wait.json'), plan_sha256=digest)
    if (out / 'result.json').exists():
        summary['result_sha256'] = sha(out / 'result.json')
        if rc == 0 and not timed and read(out / 'result.json')['status'].startswith('ARCHITECTURAL_FULL4095_OFFLINE_ACCEPTED_'):
            summary['status'] = 'ACCEPTED_ARCHITECTURAL_RECOVERY_NOT_OLD_SERVICE_PASS'
    save(out / 'terminal.json', summary)
    print(json.dumps(summary), flush=True)
    return rc if not timed else 124


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('host', 'prepare', 'run', 'audit'))
    parser.add_argument('--plan-sha256')
    parser.add_argument('--review', type=Path)
    parser.add_argument('--review-sha256')
    args = parser.parse_args()
    if args.mode == 'host':
        host()
    elif args.mode == 'prepare':
        prepare()
    elif args.mode == 'audit':
        return audit(args.plan_sha256)
    else:
        return run(args.plan_sha256, args.review, args.review_sha256)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
