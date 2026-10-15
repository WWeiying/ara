#!/usr/bin/env python3
"""Narrow late-abort successor. Original plan01 is preserved and not admitted."""
import argparse
import json
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
sys.dont_write_bytecode = True
import recovery as r
HERE = Path(__file__).resolve().parent
PREPARED = HERE / 'prepared02'
OLD_PLAN_SHA = '3ce5268b58f38e3c565d44690fe759a95a88618f15d8f2ec28b3aa251d4bf537'
SIGNALS = {signal.SIGINT, signal.SIGTERM}


def publish(out, result, abort):
    # Terminal decision only: all large report I/O and hashing precede this block.
    # Keep termination blocked until immediate audit-process exit after this call.
    signal.pthread_sigmask(signal.SIG_BLOCK, SIGNALS)
    r.need(not abort.is_set() and not (signal.sigpending() & SIGNALS), 'Abort before terminal publication')
    r.save(out / 'result.json', result)


def finalize(out, report, result, abort):
    r.save(out / 'strict.json', report)
    digest = r.sha(out / 'strict.json')
    r.need(not abort.is_set(), 'Abort during strict report save/hash')
    result.update(strict_sha256=digest, finished=time.time())
    publish(out, result, abort)


def checked_plan(digest):
    r.need(r.sha(PREPARED / 'plan.json') == digest, 'Successor plan drift')
    plan = r.read(PREPARED / 'plan.json')
    r.need(plan['prior_plan_sha256'] == OLD_PLAN_SHA and plan['audit_timeout_s'] == r.BOUND and
           plan['semantic_passes'] == 1 and plan['simulator_runs'] == plan['retries'] == 0, 'Exact successor bounds')
    r.need(r.sha(HERE / 'plan.json') == OLD_PLAN_SHA and r.identity(r.CSV) == plan['csv_identity'], 'Original plan/closed CSV drift')
    r.verify(plan['pins'])
    return plan


def prepare():
    original = r.checked_plan(OLD_PLAN_SHA)
    host = r.read(HERE / 'publish_host01/wait.json')
    r.need(host['actual_wait_returncode'] == 0 and host['timed_out'] is False, 'Actual publication Host exit')
    r.verify(host['pins'])
    pins = dict(original['pins'])
    for name in ('runner02.py', 'test_publish02.py', 'plan.json', 'PLAN01_NOT_ADMITTED.md',
                 'publish_host01/wait.json', 'publish_host01/output.log'):
        pins[str(HERE / name)] = r.sha(HERE / name)
    plan = dict(original, status='PREPARED_PENDING_HILBERT_NOT_EXECUTED', pins=pins,
                prior_plan_sha256=OLD_PLAN_SHA, final_publish='Blocked pending-signal/abort decision after strict save and hash')
    PREPARED.mkdir()
    r.save(PREPARED / 'plan.json', plan)
    print('PREPARED02', r.sha(PREPARED / 'plan.json'), 'pins', len(pins), flush=True)


def audit(digest):
    out = PREPARED / 'fullparse01'
    abort = threading.Event()
    started = time.time()
    try:
        with r.base.common.abort_signals(abort):
            plan = checked_plan(digest)
            r.provenance()
            report = r.checker.audit(r.CSV, r.base.specification(), abort)
            r.need(report['actual_csv_sha256'] == plan['pins'][str(r.CSV)], 'Closed CSV digest')
            checked_plan(digest)
            r.need(not abort.is_set(), 'Abort after complete validation')
            result = dict(status='ARCHITECTURAL_FULL4095_OFFLINE_ACCEPTED_ORIGINAL_SERVICE_FAILED_NOT_LINUX',
                started=started, retries=0, DUT_runs=0, plan_sha256=digest,
                csv_sha256=report['actual_csv_sha256'], pins_pre_post_unchanged=True,
                scope=plan['full_scope'], required_owners=plan['required_owners'],
                original_monitor=plan['original_monitor'], original_service=plan['original_service'])
            finalize(out, report, result, abort)
        return 0
    except BaseException as error:
        r.save(out / 'failure.json', dict(status='NOT_ACCEPTED', firstcause=type(error).__name__ + ': ' + str(error),
               started=started, finished=time.time(), aborted=abort.is_set(), retries=0, DUT_runs=0))
        return 1


def run(digest, path, expected):
    checked_plan(digest)
    r.need(r.sha(path) == expected, 'Actual independent review hash')
    review = r.read(path)
    r.need(review['status'] == 'NO_BLOCKER_ONE_CLOSED_CSV_RECOVERY_NOT_DUT' and
           review['plan_sha256'] == digest and review['checker_sha256'] == r.sha(HERE / 'checker.py') and
           review['runner_sha256'] == r.sha(Path(__file__)) and
           review['host_wait_sha256'] == r.sha(HERE / 'host01/wait.json'), 'Exact independent successor entry')
    out = PREPARED / 'fullparse01'
    out.mkdir()
    command = [sys.executable, '-B', str(Path(__file__).resolve()), 'audit', '--plan-sha256', digest]
    r.save(out / 'attempt.json', dict(command=command, plan_sha256=digest, review=str(path),
           review_sha256=expected, timeout_s=r.BOUND, max_attempts=1))
    started = time.monotonic()
    timed = False
    with (out / 'output.log').open('x') as stream:
        child = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)
        try:
            rc = child.wait(timeout=r.BOUND)
        except subprocess.TimeoutExpired:
            timed = True
            child.kill()
            rc = child.wait()
    r.save(out / 'wait.json', dict(command=command, pid=child.pid, actual_wait_returncode=rc,
           elapsed_s=time.monotonic()-started, timed_out=timed, retries=0, plan_sha256=digest))
    terminal = dict(status='NOT_ACCEPTED', actual_wait_returncode=rc, timed_out=timed,
                    wait_sha256=r.sha(out / 'wait.json'), plan_sha256=digest)
    if (out / 'result.json').exists():
        terminal['result_sha256'] = r.sha(out / 'result.json')
        if rc == 0 and not timed and r.read(out / 'result.json')['status'].startswith('ARCHITECTURAL_FULL4095_OFFLINE_ACCEPTED_'):
            terminal['status'] = 'ACCEPTED_ARCHITECTURAL_RECOVERY_NOT_OLD_SERVICE_PASS'
    if (out / 'failure.json').exists():
        terminal['failure_sha256'] = r.sha(out / 'failure.json')
    r.save(out / 'terminal.json', terminal)
    print(json.dumps(terminal), flush=True)
    return rc if not timed else 124


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('prepare', 'run', 'audit'))
    parser.add_argument('--plan-sha256')
    parser.add_argument('--review', type=Path)
    parser.add_argument('--review-sha256')
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare()
        return 0
    if args.mode == 'audit':
        return audit(args.plan_sha256)
    return run(args.plan_sha256, args.review, args.review_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
