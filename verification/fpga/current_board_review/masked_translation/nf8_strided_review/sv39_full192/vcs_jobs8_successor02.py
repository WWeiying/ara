#!/usr/bin/env python3
"""NF8 orchestration successor: synchronized deadline and cancellation acceptance."""
import argparse
import csv
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
sys.dont_write_bytecode = True
import vcs_jobs8 as base

VERSION = 'deadline_cancel_successor02'
REVIEW = base.HERE.parents[2] / 'whole_register_original/nf8_full192_independent_review01.md'


def atomic_publish(path, value):
    """Replace only an owned successor artifact; sealed inputs still use save(x)."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.' + path.name + '.',
                                         suffix='.pending', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class CampaignAbort(base.scheduler.Abort):
    def __init__(self):
        super().__init__()
        self.terminal = False

    def stop(self, reason):
        with self.lock:
            if not self.terminal:
                super().stop(reason)


class GroupTerminal:
    """The shared abort lock serializes timeout with the group's acceptance edge."""
    def __init__(self, abort, failure, now=time.monotonic):
        self.abort = abort
        self.failure = failure
        self.now = now
        self.deadline = now() + base.CASE_OUTER
        self.closed = False
        self.timed_out = False

    def timeout(self):
        with self.abort.lock:
            if self.closed:
                return
            self.timed_out = True
            self.failure(ValueError('2520s runner/teardown bound reached'))

    def accept(self, result, path):
        with self.abort.lock:
            if self.now() >= self.deadline:
                self.timeout()
            base.require(not self.timed_out and self.abort.reason is None,
                         'Group cancelled or timed out before acceptance')
            # This is the completion linearization edge; a later timer is stale.
            self.closed = True
            atomic_publish(path, result)
            # A Python signal handler can reenter the RLock during the write.
            base.require(self.abort.reason is None, 'Cancellation during group publication')


def group_worker(out, group, abort):
    d = out / 'groups' / f'group{group:02d}'
    d.mkdir()
    source = base.reference_directory(group)
    status = base.read(source / 'status.json')
    checker = base.csv_oracle.Checker(base.read(source / 'soc.symbols.json'),
        base.read(source / 'cases.json'), status, base.read(out / 'ledgers' / f'group{group:02d}.json'))
    cmd = base.command(out, group, True)
    base.save(d / 'command.json', cmd)
    artifact = d / 'run/tests' / base.name(group)
    events = base.live_tail.DirectoryEvents(d)
    first_line = True

    def line(text):
        nonlocal first_line
        values = next(csv.reader([text]))
        if first_line:
            base.require(values == base.csv_oracle.FIELDS, 'Wrong CSV header')
            first_line = False
        else:
            base.require(len(values) == len(base.csv_oracle.FIELDS), 'Malformed CSV row')
            checker.row(dict(zip(base.csv_oracle.FIELDS, values)))

    def failure(error):
        with abort.lock:
            analysis = checker.failure(error)
            abort.stop(dict(group=group, analysis=analysis))
            if not (d / 'firstfailure.json').exists():
                base.save(d / 'firstfailure.json', analysis)

    started = time.monotonic()
    code = None
    process = timer = None
    terminal = GroupTerminal(abort, failure)
    try:
        with (d / 'worker.log').open('x') as log:
            process = abort.launch(group, lambda: subprocess.Popen(cmd, cwd=base.ref.base.ROOT,
                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True))
            timer = threading.Timer(max(0, terminal.deadline-time.monotonic()), terminal.timeout)
            timer.daemon = True
            timer.start()
            code = base.live_tail.wait_append(process, events, artifact / 'commit_trace.csv', line, failure)
        analysis = checker.finish()
        summary = base.read(d / 'run/summary.json')
        meta = base.read(d / 'run/run.json')
        inputs = base.read(artifact / 'inputs.json')
        image = base.read(base.IMAGE / 'image.json')
        base.require(code == 0 and len(summary) == 1 and summary[0]['name'] == base.name(group)
                     and summary[0]['status'] == 'PASS' and summary[0]['returncode'] == 0, 'Runner not PASS')
        base.require(meta['status'] == 'COMPLETE' and meta['tests'] == [base.name(group)]
                     and meta['commit_trace'] is True and meta['simv'] == image['simv']
                     and meta['invocation'] == cmd[2:], 'Run metadata mismatch')
        base.require(inputs['simv'] == dict(path=image['simv'], image_sha256=image['files']), 'Executed image mismatch')
        base.require(inputs['binary']['sha256'] == base.sha(artifact / 'input.elf') == status['elf_sha256']['soc']
                     and Path(inputs['binary']['source']).resolve() == source / 'soc.elf', 'Executed ELF mismatch')
        console = (artifact / 'console.log').read_text()
        base.require(console.count('NA_SV39_PASS') == 1 and 'NA_SV39_FAIL' not in console, 'Firmware not PASS')
        result = dict(status='PASS', returncode=code, analysis=analysis, summary=summary,
                      group=group, elapsed_s=time.monotonic()-started, timed_out=False)
        terminal.accept(result, d / 'complete.json')
    except Exception as error:
        failure(error)
        if process is None:
            events.close()
        result = dict(status='FAIL', returncode=code, analysis=checker.failure(error), group=group,
                      elapsed_s=time.monotonic()-started, timed_out=terminal.timed_out)
        atomic_publish(d / 'complete.json', result)
    finally:
        with abort.lock:
            terminal.closed = True
        if timer:
            timer.cancel()
            timer.join()
        abort.remove(group)
    return result


def publish_campaign(out, plan, results, abort, post):
    # Signal delivery is deferred only across final publication. Pending signals
    # at the terminal edge count as cancellation, even when every runner exited0.
    signals = {signal.SIGTERM, signal.SIGINT}
    oldmask = signal.pthread_sigmask(signal.SIG_BLOCK, signals)
    try:
        with abort.lock:
            for sig in signal.sigpending() & signals:
                abort.stop(dict(signal=int(sig)))
            passed = (post == 'UNCHANGED' and abort.reason is None and
                      set(results) == set(base.GROUPS) and
                      all(r['status'] == 'PASS' and not r.get('timed_out', False) for r in results.values()))
            result = dict(status='CANDIDATE04_NF8_FULL192_PASS' if passed else 'CANDIDATE04_NF8_FULL192_NOT_PASS',
                          groups=results, firstfailure=abort.reason, post_hashes=post,
                          image_sha256=base.IMAGE_SHA, scope=plan['scope'], orchestration=VERSION)
            atomic_publish(out / 'complete.json', result)
            for sig in signal.sigpending() & signals:
                abort.stop(dict(signal=int(sig)))
            if passed and abort.reason is not None:
                result.update(status='CANDIDATE04_NF8_FULL192_NOT_PASS', firstfailure=abort.reason)
                atomic_publish(out / 'complete.json', result)
                passed = False
            # Terminal linearization: all timers joined, hashes done, publication
            # complete, and pending cancellation checked. Later signals are post-run.
            abort.terminal = True
            return int(not passed)
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, oldmask)


def publish_preflight(out, plan):
    atomic_publish(out / 'plan.json', plan)
    review = base.read(out / 'review.template.json')
    review.update(plan_sha256=base.sha(out / 'plan.json'), orchestration=VERSION)
    atomic_publish(out / 'review.template.json', review)
    return review


def preflight(out, host_root):
    base.preflight(out, host_root)
    with (out / 'successor_tests.log').open('x') as log:
        subprocess.run(['/usr/bin/python3', '-B', str(base.HERE / 'test_successor02.py')],
                       cwd=base.HERE, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    plan = base.read(out / 'plan.json')
    plan['orchestration'] = VERSION
    paths = [Path(__file__), base.HERE / 'test_successor02.py',
             base.HERE / 'SUCCESSOR02_REVIEW.md', REVIEW, out / 'successor_tests.log']
    plan['pins'].update({str(p): base.sha(p) for p in paths})
    base.verify(plan['pins'])
    review = publish_preflight(out, plan)
    print('SUCCESSOR02_PREFLIGHT_PASS_NOT_LAUNCHED', review['plan_sha256'], flush=True)


def worker(out, review_path, authorized):
    base.require(authorized and review_path is not None, 'Explicit reviewed authorization required')
    base.require(not (out / 'worker.json').exists(), 'One launch only; no repeat/retry')
    plan = base.read(out / 'plan.json')
    base.validate_plan(plan)
    base.require(plan.get('orchestration') == VERSION, 'Successor02 plan required')
    base.verify(plan['pins'])
    review = base.read(review_path)
    base.require(review.get('parent_authorized') is True
                 and review.get('plan_sha256') == base.sha(out / 'plan.json')
                 and review.get('image_sha256') == base.IMAGE_SHA and review.get('jobs') == 8
                 and review.get('nf7_unit') == base.capacity8.NF7_UNIT
                 and review.get('orchestration') == VERSION, 'Review identity/authorization differs')
    independent = review['independent_review']
    base.require(independent['no_blocker'] is True and base.sha(independent['path']) == independent['sha256'],
                 'Pinned independent no-blocker review required')
    image = base.check_image()
    base.require(image['files'] == plan['image_files'], 'Plan image differs')
    gate = base.capacity8.actual(review['reserved_units'])
    base.save(out / 'worker.json', dict(pid=os.getpid(), start_unix=time.time(), jobs=8, reserved_through_pilot=8,
              plan_sha256=base.sha(out / 'plan.json'), review_sha256=base.sha(review_path), gate=gate))
    abort = CampaignAbort()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda n, f: abort.stop(dict(signal=n)))

    def pilot_ok(result):
        base.require(result['status'] == 'PASS' and result['analysis']['trials'] == [0, 1, 2, 3], 'Pilot not complete')
        base.verify(plan['pins'])
        base.require(base.check_image() == image, 'Pilot input/image drift')
        with abort.lock:
            base.require(abort.reason is None, 'Pilot cancelled before remaining admission')
            base.save(out / 'pilot_acceptance.json', dict(status='PILOT_GROUP0_EXACT_ORACLE_PASS',
                group0_complete_sha256=base.sha(out / 'groups/group00/complete.json'),
                csv_sha256=base.sha(out / 'groups/group00/run/tests/nf8_g00/commit_trace.csv'),
                remaining_groups=list(range(1, 48)), remaining_jobs=8))

    results = base.scheduler.pilot_then_remaining(lambda g, a: group_worker(out, g, a), abort, pilot_ok)
    post = 'UNCHANGED'
    try:
        base.verify(plan['pins'])
        base.require(base.check_image() == image, 'Post image drift')
        base.require(base.sha(out / 'plan.json') == base.read(out / 'worker.json')['plan_sha256']
                     and base.sha(review_path) == base.read(out / 'worker.json')['review_sha256']
                     and base.sha(independent['path']) == independent['sha256'], 'Plan/review changed')
    except Exception as error:
        post = str(error)
    return publish_campaign(out, plan, results, abort, post)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['preflight', 'worker'])
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--host-root', type=Path)
    p.add_argument('--review', type=Path)
    p.add_argument('--authorize-run', action='store_true')
    a = p.parse_args()
    out = a.out.resolve()
    base.require(out.is_relative_to(base.HERE) and out != base.HERE, 'Owned output required')
    if a.action == 'preflight':
        preflight(out, a.host_root.resolve() if a.host_root else None)
    else:
        sys.exit(worker(out, a.review.resolve() if a.review else None, a.authorize_run))
