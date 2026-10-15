#!/usr/bin/env python3
"""One independently admitted, bounded closed-CSV audit. Never runs a DUT."""
import argparse
import json
import os
from pathlib import Path
import signal
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
ORIGINAL_PLAN_SHA = '6ed1c1ffafeddb136962cf49ab10e761441e9bf3d24be67a71770a2245a2ea3f'
ORIGINAL_CHECKER_SHA = 'cdf3dbb42e6c9d4ac72b5f57c9727ad660e441776064752aea6aee875bf85652'
BOUND = 600
SIGNALS = {signal.SIGINT, signal.SIGTERM}
read, sha, need = base.read, base.sha, base.require
SCOPE = dict(calls=4095, results=262080, guards=8190, returned_vstart_zero=4095,
             helper_instructions=53235, packed_output_reads=36855, fresh_output_bytes_each_call=66)
OWNERS = dict(compulsory_memory_owners=20475, required_target_owners=2592,
              required_op24_memory_targets=117, minimum_required_owners=23067)


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def identity(path):
    st = path.stat()
    return dict(bytes=st.st_size, mtime_ns=st.st_mtime_ns, inode=st.st_ino, device=st.st_dev)


def verify(pins):
    base.common.base.verify_pins(pins)


def original_identity():
    need(sha(SOURCE / 'plan.json') == ORIGINAL_PLAN_SHA and
         sha(checker.OLD / 'checker.py') == ORIGINAL_CHECKER_SHA, 'Own original plan/checker drift')
    original = read(SOURCE / 'plan.json')
    need(len(original['cases']) == 1 and original['cases'][0]['id'] == base.ID ==
         'arithmetic_original_e8_mf2_full4095_packed', 'Exact own fractional membership')
    return original


def provenance():
    plan = original_identity()
    complete = read(SOURCE / 'complete.json')
    need(complete['status'] == 'NOT_PASS' and complete['aborted'] is True and complete['retries'] == 0 and
         complete['plan_sha256'] == ORIGINAL_PLAN_SHA and len(complete['results']) == 1, 'Original failed terminal preserved')
    child = complete['results'][0]
    need(child['name'] == base.ID and child['status'] == 'ERROR' and child['returncode'] == 0 and
         child['reason'] == "Postcheck ValueError: Missing necessary architectural owner {'insn': 947993687, 'pc': 2147487708, 'retire_order': 157111, 'call': 1200, 'helper_index': 8, 'kind': 'target', 'required': True, 'arch_order': 13209, 'alloc': 0, 'done': 0}",
         'Only this own measured owner rejection is eligible')
    monitor = read(ROOT / 'child_outcome.unvalidated.json')
    need(type(monitor['returncode']) is int and monitor['returncode'] == 0 and
         0 < monitor['elapsed_s'] == child['elapsed_s'] <= plan['cases'][0]['timeout_s'] and
         not any(monitor[k] for k in ('timed_out', 'failure_seen', 'cancelled')), 'Actual durable simulator exit/budget')
    service = read(SOURCE / 'service_exit.json')
    need(service['kind'] == 'SYSTEMD_EXEC_STOP_POST_ACTUAL_ENVIRONMENT' and
         [service[k] for k in ('SERVICE_RESULT', 'EXIT_CODE', 'EXIT_STATUS')] == ['exit-code', 'exited', '1'],
         'Original service1 must remain a failed service')
    command = read(ROOT / 'command.json')
    need(monitor['command_sha256'] == sha(ROOT / 'command.json') and
         monitor['command'] == command['command'] and monitor['cwd'] == command['cwd'], 'Durable actual command binding')
    ledger, _, _ = base.common.image_context(Path(plan['image']))
    actual = SimpleNamespace(returncode=monitor['returncode'], elapsed_s=monitor['elapsed_s'], artifact_dir=ROOT)
    base.common.check_artifacts(actual, dict(plan['cases'][0], original_name=base.ID), ledger)
    for name in ('console.log', 'work/run.vcs.log'):
        base.console_gate((ROOT / name).read_text())
    spec = base.specification()
    need(plan['specs'] == {base.SHAPE: spec}, 'Own exact source/ELF spec, not M4 alias')
    need(spec['config'] == dict(id='rvv_matrix_e8_mf2', sew=8, lmul='mf2', cap=64, calls=4095,
         vtype=7, physical_group_registers=1, observed_group_bytes=64, mask_bytes=128, vlm_bytes=8), 'Fractional geometry')
    need(spec['backend']['helpers']['op_19'][8]['pc'] == 0x80000fdc, 'Own actual helper PC')
    return plan, monitor, service


def host():
    original = original_identity()
    verify(original['pins'])
    out = HERE / 'host01'
    out.mkdir()
    names = ('checker.py', 'recovery.py', 'test_owner.py', 'test_publish.py', 'test_scope.py')
    pins = {str(HERE / name): sha(HERE / name) for name in names}
    save(out / 'preflight.json', dict(pins=pins, original_plan_sha256=ORIGINAL_PLAN_SHA))
    command = [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(HERE), '-p', 'test_*.py', '-v']
    start = time.monotonic()
    timed = False
    with (out / 'output.log').open('x') as stream:
        child = subprocess.Popen(command, cwd=HERE, stdout=stream, stderr=subprocess.STDOUT)
        try:
            rc = child.wait(timeout=120)
        except subprocess.TimeoutExpired:
            timed = True
            child.kill()
            rc = child.wait()
    save(out / 'wait.json', dict(command=command, pid=child.pid, actual_wait_returncode=rc,
         elapsed_s=time.monotonic()-start, timed_out=timed, retries=0, pins=pins))
    verify(pins)
    need(rc == 0 and not timed, 'Host did not pass; preserve first evidence')
    print('HOST_PASS', flush=True)


def prepare():
    need(not (HERE / 'plan.json').exists(), 'Fresh independent plan only')
    waited = read(HERE / 'host01/wait.json')
    need(type(waited['actual_wait_returncode']) is int and waited['actual_wait_returncode'] == 0 and
         waited['timed_out'] is False, 'Actual Host exit0')
    verify(waited['pins'])
    original, monitor, service = provenance()
    verify(original['pins'])
    evidence = read(HERE / 'host01/model_evidence.json')
    need(evidence['owners'] == OWNERS and evidence['scope'] == SCOPE and
         evidence['changed_zero_based_calls'] == [b+i for b in (1200, 2565, 3930) for i in range(6)],
         'Own complete source model independently confirms counts and exact18')
    base.validate_reset(base.specification())
    pins = dict(original['pins'])
    for module in list(sys.modules.values()):
        file = getattr(module, '__file__', None)
        if file:
            path = Path(file).resolve()
            if path.is_file() and str(path).startswith('/home/wangwy/'):
                pins[str(path)] = sha(path)
    for name in ('checker.py', 'recovery.py', 'test_owner.py', 'test_publish.py', 'test_scope.py', 'README.md',
                 'host01/preflight.json', 'host01/wait.json', 'host01/output.log', 'host01/model_evidence.json'):
        pins[str(HERE / name)] = sha(HERE / name)
    for name in ('plan.json', 'complete.json', 'service_exit.json', 'collector_result.json', 'collector_exit.json'):
        pins[str(SOURCE / name)] = sha(SOURCE / name)
    for name in ('input.elf', 'inputs.json', 'command.json', 'child_outcome.unvalidated.json',
                 'console.log', 'work/run.vcs.log', 'trace_summary.json', 'commit_trace.csv'):
        pins[str(ROOT / name)] = sha(ROOT / name)
    frozen = Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/frozen/sources/hardware/src/ara_dispatcher.sv')
    need(sha(frozen) == 'c179ddd08b2bdb8648246f187aa892be5853fda38aeca850402d5e5b9b17ef7d', 'Frozen exact null-slide implementation')
    pins[str(frozen)] = sha(frozen)
    verify(pins)
    plan = dict(status='PREPARED_PENDING_AVERROES_NOT_EXECUTED', original_plan_sha256=ORIGINAL_PLAN_SHA,
        source=str(SOURCE), csv=str(CSV), csv_identity=identity(CSV), pins=pins, audit_timeout_s=BOUND,
        semantic_passes=1, simulator_runs=0, retries=0, original_monitor=monitor, original_service=service,
        scope=SCOPE, required_owners=OWNERS, model_evidence_sha256=sha(HERE / 'host01/model_evidence.json'))
    save(HERE / 'plan.json', plan)
    print('PREPARED', sha(HERE / 'plan.json'), 'pins', len(pins), 'CSV bytes', plan['csv_identity']['bytes'], flush=True)


def checked_plan(digest):
    need(sha(HERE / 'plan.json') == digest, 'Late plan drift')
    plan = read(HERE / 'plan.json')
    need(plan['audit_timeout_s'] == BOUND and plan['semantic_passes'] == 1 and
         plan['simulator_runs'] == plan['retries'] == 0 and plan['original_plan_sha256'] == ORIGINAL_PLAN_SHA and
         plan['scope'] == SCOPE and plan['required_owners'] == OWNERS, 'Exact single offline scope/bounds')
    need(identity(CSV) == plan['csv_identity'], 'Closed CSV stat drift')
    verify(plan['pins'])
    return plan


def publish(out, result, abort):
    # Only the final small result is in this terminal decision window.
    # Keep signals blocked until the audit process immediately exits.
    signal.pthread_sigmask(signal.SIG_BLOCK, SIGNALS)
    need(not abort.is_set() and not (signal.sigpending() & SIGNALS), 'Abort before terminal publication')
    save(out / 'result.json', result)


def finalize(out, report, result, abort):
    save(out / 'strict.json', report)
    digest = sha(out / 'strict.json')
    need(not abort.is_set(), 'Abort during strict report save/hash')
    result.update(strict_sha256=digest, finished=time.time())
    publish(out, result, abort)


def audit(digest):
    out = HERE / 'fullparse01'
    abort = threading.Event()
    started = time.time()
    try:
        with base.common.abort_signals(abort):
            plan = checked_plan(digest)
            provenance()
            report = checker.audit(CSV, base.specification(), abort)
            need(report['actual_csv_sha256'] == plan['pins'][str(CSV)], 'Original closed CSV digest')
            need(all(report['strict'][k] == v for k, v in SCOPE.items()), 'Exact own66-byte full scope')
            need(all(report['owner_coverage'][k] == v for k, v in OWNERS.items()), 'Own necessary owner scope')
            checked_plan(digest)
            need(not abort.is_set(), 'Abort after complete validation')
            result = dict(status='ARCHITECTURAL_E8MF2_FULL4095_OFFLINE_ACCEPTED_ORIGINAL_SERVICE_FAILED_NOT_LINUX',
                started=started, retries=0, DUT_runs=0, plan_sha256=digest,
                csv_sha256=report['actual_csv_sha256'], pins_pre_post_unchanged=True,
                scope=SCOPE, required_owners=OWNERS, original_monitor=plan['original_monitor'], original_service=plan['original_service'])
            finalize(out, report, result, abort)
        return 0
    except BaseException as error:
        save(out / 'failure.json', dict(status='NOT_ACCEPTED', firstcause=type(error).__name__ + ': ' + str(error),
             started=started, finished=time.time(), aborted=abort.is_set(), retries=0, DUT_runs=0))
        return 1


def run(digest, path, expected):
    checked_plan(digest)
    need(sha(path) == expected, 'Independent exact review hash')
    review = read(path)
    need(review['status'] == 'NO_BLOCKER_ONE_CLOSED_CSV_RECOVERY_NOT_DUT' and
         review['plan_sha256'] == digest and review['checker_sha256'] == sha(HERE / 'checker.py') and
         review['runner_sha256'] == sha(Path(__file__)) and review['host_wait_sha256'] == sha(HERE / 'host01/wait.json'),
         'Averroes exact entry binding')
    out = HERE / 'fullparse01'
    out.mkdir()
    command = [sys.executable, '-B', str(Path(__file__).resolve()), 'audit', '--plan-sha256', digest]
    save(out / 'attempt.json', dict(command=command, plan_sha256=digest, review=str(path),
         review_sha256=expected, timeout_s=BOUND, max_attempts=1))
    start = time.monotonic()
    timed = False
    with (out / 'output.log').open('x') as stream:
        child = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)
        try:
            rc = child.wait(timeout=BOUND)
        except subprocess.TimeoutExpired:
            timed = True
            child.kill()
            rc = child.wait()
    save(out / 'wait.json', dict(command=command, pid=child.pid, actual_wait_returncode=rc,
         elapsed_s=time.monotonic()-start, timed_out=timed, retries=0, plan_sha256=digest))
    terminal = dict(status='NOT_ACCEPTED', actual_wait_returncode=rc, timed_out=timed,
                    wait_sha256=sha(out / 'wait.json'), plan_sha256=digest)
    if (out / 'result.json').exists():
        terminal['result_sha256'] = sha(out / 'result.json')
        if rc == 0 and not timed and read(out / 'result.json')['status'].startswith('ARCHITECTURAL_E8MF2_FULL4095_OFFLINE_ACCEPTED_'):
            terminal['status'] = 'ACCEPTED_E8MF2_ARCHITECTURAL_RECOVERY_NOT_OLD_SERVICE_PASS'
    if (out / 'failure.json').exists():
        terminal['failure_sha256'] = sha(out / 'failure.json')
    save(out / 'terminal.json', terminal)
    print(json.dumps(terminal), flush=True)
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
