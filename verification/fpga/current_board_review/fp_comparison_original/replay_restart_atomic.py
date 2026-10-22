#!/usr/bin/env python3
"""Unlaunched successor of sealed06: sticky cancellation through final publication."""
import argparse
from contextlib import contextmanager
import copy
import hashlib
import os
from pathlib import Path
import signal
import sys
import threading
import time

sys.dont_write_bytecode = True
import replay_restart_successor as old

HERE, read, save, sha = old.HERE, old.read, old.save, old.sha
prior = old.prior
PLAN = HERE / 'candidate04_restart_plan07'
PREDECESSOR = HERE / 'candidate04_restart_plan06'
RUN = HERE / 'candidate04_restart_run03'
# Exact sealed06 identity, not an editable pointer to a future preparation.
PREDECESSOR_SHA = '396cca255723e58fb5ba089220ed94edbb09c5a9417a69ac81e044de0d54d1af'
SIGNALS = {signal.SIGINT, signal.SIGTERM}
HELPER = HERE.parent / 'integration/prepare.py'
HELPER_SHA = 'c8852599c65e0a0812a7dc77dc365eb40398252867a29b226f34d758e5c56cf8'


class AbortLatch:
    def __init__(self):
        self.lock = threading.RLock()
        self.event = threading.Event()
        self.signal_seen = False
        self.terminal = None

    def set(self):
        with self.lock:
            self.event.set()

    def is_set(self):
        return self.signal_seen or self.event.is_set()

    def wait(self, timeout=None):
        if self.is_set():
            return True
        self.event.wait(timeout)
        return self.is_set()

    def clear(self):
        raise RuntimeError('Abort latch cannot be cleared')

    def on_signal(self, signum, frame):
        # Python signal callbacks must not wait on a lock interrupted in this thread.
        self.signal_seen = True

    @contextmanager
    def signals(self):
        previous = {s: signal.signal(s, self.on_signal) for s in SIGNALS}
        try:
            yield
        finally:
            for s, handler in previous.items():
                signal.signal(s, handler)

    def accept(self, result):
        with self.lock:
            if self.is_set() and result.status == 'PASS':
                result.status, result.reason = 'CANCELLED', 'Sticky abort during/after validation'
        return result

    def publish(self, path, record, eligible):
        # Prepare both records outside the lock. Only terminal choice and rename
        # are serialized with abort; signals are deferred over that short region.
        old.require(threading.current_thread() is threading.main_thread() and
                    len(threading.enumerate()) == 1, 'Publication requires joined workers and main thread')
        good = dict(record, status='PASS_2_ORIGINAL_PREFIXES_260_CALLS_M4', aborted=False)
        bad = dict(record, status='NOT_PASS', aborted=True, calibration=[])
        good_path, bad_path = path.with_suffix('.pass.tmp'), path.with_suffix('.notpass.tmp')
        save(good_path, good)
        save(bad_path, bad)
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, SIGNALS)
        try:
            with self.lock:
                old.require(self.terminal is None, 'Terminal publication is single-use')
                # The last kernel pending-set snapshot is the PASS decision's
                # linearization point. No earlier signal sample is reused.
                passed = eligible and not self.is_set() and not (signal.sigpending() & SIGNALS)
                os.replace(good_path if passed else bad_path, path)
                self.terminal = passed
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)
            good_path.unlink(missing_ok=True)
            bad_path.unlink(missing_ok=True)
        return passed


def process_is_simv(comm, cmdline):
    argv0 = cmdline.split(b'\0', 1)[0].decode(errors='replace')
    return comm.strip() == 'simv' or Path(argv0).name == 'simv'


def scan_simv(root=Path('/proc')):
    live = []
    for proc in root.iterdir():
        if not proc.name.isdigit():
            continue
        try:
            comm = (proc / 'comm').read_text()
            cmdline = (proc / 'cmdline').read_bytes()
            if process_is_simv(comm, cmdline):
                live.append(dict(pid=int(proc.name), comm=comm.strip(),
                    argv=cmdline.replace(b'\0', b' ').decode(errors='replace'),
                    cgroup=(proc / 'cgroup').read_text()))
        except (FileNotFoundError, ProcessLookupError):
            continue
    return live


def resources(units):
    available = int(next(s.split()[1] for s in Path('/proc/meminfo').read_text().splitlines()
                         if s.startswith('MemAvailable:'))) * 1024
    return dict(time=time.time(), **old.resource_math(scan_simv(), available, units))


def verify(pins):
    # Do not rely on the formerly unpinned live helper to verify itself.
    for name, expected in pins.items():
        digest = hashlib.sha256()
        with Path(name).open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        old.require(digest.hexdigest() == expected, 'Pinned input changed: ' + name)


def local_modules():
    roots = (HERE.parents[3], Path('/home/wangwy/fpga_runs/current_board_memory_candidate04/frozen/sources'))
    paths = set()
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name:
            path = Path(name).resolve()
            if path.suffix == '.py' and any(path.is_relative_to(r) for r in roots):
                paths.add(path)
    return {str(p): sha(p) for p in sorted(paths)}


def module_gate(pins):
    modules = local_modules()
    old.require(all(pins.get(p) == digest for p, digest in modules.items()), 'Unpinned loaded project module')
    return modules


def runner_class(parent, entries, abort, admission=None):
    class Checked(parent):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.cancel_event = abort

        def _run_test(self, test, image):
            # Executor workers cannot consume the process-directed terminal
            # signals while the main thread performs its atomic publication.
            mask = signal.pthread_sigmask(signal.SIG_BLOCK, SIGNALS)
            try:
                if admission and not abort.is_set():
                    admission(test.name)
                result = super()._run_test(test, image)
                if result.status == 'PASS':
                    prior.checked_result(result, entries[test.name],
                        (result.artifact_dir / 'console.log').read_text(), abort)
                    if result.status == 'PASS' and not abort.is_set():
                        audit = prior.check_trace(entries[test.name], result.artifact_dir / 'commit_trace.csv')
                        save(result.artifact_dir / 'architectural_trace_audit.json', audit)
                elif result.status != 'DRY_RUN':
                    abort.set()
                return abort.accept(result)
            except BaseException:
                abort.set()
                raise
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, mask)
    return Checked


def execute(data, out, dry_run, abort, units=None):
    old.contract(data)
    ledger, repo, (parent, options, case, _), engine = old.identity()
    engine.FAIL_RE = old.re.compile(engine.FAIL_RE.pattern + '|' + prior.BAD.pattern, engine.FAIL_RE.flags)
    admission = None if dry_run else lambda name: save(out.parent / 'admission' / f'{name}.json', resources(units))
    checked = runner_class(parent, {c['id']: c for c in data['cases']}, abort, admission)
    tests = [case(c['id'], 'app', '', Path(c['elf']), c['id'], c['timeout_s']) for c in data['cases']]
    opts = options(repo, out, 'default', 2, 1, dry_run, False, True, Path(ledger['simv']), True, None)
    return checked(opts, tests, sys.argv).run()


def terminal_inputs(results, out):
    run, summary = read(out / 'run.json'), read(out / 'summary.json')
    old.require(run['status'] == 'COMPLETE' and run['status_counts'] == {'PASS': 2},
                'Runner did not complete exact two PASS statuses')
    old.require(len(results) == len(summary) == 2 and
                {r.name for r in results} == {r['name'] for r in summary} == old.NAMES,
                'Terminal membership differs')
    for result in results:
        row = next(x for x in summary if x['name'] == result.name)
        old.require(result.status == row['status'] == 'PASS' and result.returncode == row['returncode'] == 0,
                    'Terminal result/summary is not PASS rc0')
        old.require(str(result.artifact_dir) == row['artifact_dir'], 'Terminal artifact path differs')
    return dict(run_sha256=sha(out / 'run.json'), summary_sha256=sha(out / 'summary.json'))


def prepare():
    old.require(sha(PREDECESSOR / 'plan.json') == PREDECESSOR_SHA, 'Sealed06 changed')
    data = copy.deepcopy(read(PREDECESSOR / 'plan.json'))
    verify(data['pins'])
    old.require(sha(HELPER) == HELPER_SHA, 'Reviewed helper changed')
    PLAN.mkdir(exist_ok=False)
    import unittest
    import test_restart_successor
    import test_restart_atomic
    inherited = prior.self_test()
    old.require(len(inherited) == 27, 'Inherited host27 changed')
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(m)
                               for m in (test_restart_successor, test_restart_atomic))
    with (PLAN / 'host_tests.log').open('x') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    old.require(result.wasSuccessful(), 'Host gate failed')
    save(PLAN / 'host_gate.json', dict(status='PASS', inherited_count=27,
        inherited_checks=inherited, unittest_count=result.testsRun, log_sha256=sha(PLAN / 'host_tests.log')))
    data.update(output=str(RUN), predecessor_plan=str(PREDECESSOR / 'plan.json'),
                predecessor_sha256=PREDECESSOR_SHA, entrypoint=str(Path(__file__).resolve()))
    old.identity()
    data['pins'].update(local_modules())
    for path in (HELPER, PREDECESSOR / 'plan.json', PLAN / 'host_gate.json', PLAN / 'host_tests.log'):
        data['pins'][str(path)] = sha(path)
    data['fixes'] = ['Sticky abort through atomic terminal publication', 'Require COMPLETE and exact2 PASS summary',
                     'Pin loaded local module closure including integration/prepare.py', 'Count comm OR argv0 simv']
    old.contract(data)
    save(PLAN / 'plan.json', data)
    abort = AbortLatch()
    with abort.signals():
        rows = execute(data, PLAN / 'dryrun', True, abort)
    old.require(not abort.is_set() and len(rows) == 2 and {r.name for r in rows} == old.NAMES and
                all(r.status == 'DRY_RUN' for r in rows), 'Dry-run differs')
    module_gate(data['pins'])
    verify(data['pins'])
    digest = sha(PLAN / 'plan.json')
    save(PLAN / 'preflight.json', dict(status='READY_FOR_REVIEW_NOT_LAUNCHED', plan_sha256=digest,
        pins_unchanged=True, pin_count=len(data['pins']), VCS_started=False, gates_polled=False,
        loaded_modules=module_gate(data['pins'])))
    review = read(PREDECESSOR / 'review.template.json')
    review['plan_sha256'] = digest
    review['units']['prefix5'] = 'ara-arithmetic-prefix5-candidate04-01.service'
    save(PLAN / 'review.template.json', review)
    print('READY_NOT_LAUNCHED', digest, flush=True)


def work(approved, review_path, review_hash, authorized):
    old.require(sys.flags.optimize == 0, 'Python -O disables inherited trace assertions')
    old.require(authorized and approved == sha(PLAN / 'plan.json'), 'Explicit approved plan hash required')
    old.require(review_path is not None and review_hash == sha(review_path), 'Explicit pinned parent review required')
    old.require(not RUN.exists(), 'Fresh run only; no retry')
    abort = AbortLatch()
    with abort.signals():
        data = read(PLAN / 'plan.json')
        old.contract(data)
        verify(data['pins'])
        review = read(review_path)
        evidence = old.gates(review, approved)
        admission = resources(review['units'])
        old.identity()
        module_gate(data['pins'])
        old.require(not abort.is_set(), 'Aborted before launch')
        RUN.mkdir()
        (RUN / 'admission').mkdir()
        save(RUN / 'launch.json', dict(pid=os.getpid(), time=time.time(), plan_sha256=approved,
            review_path=str(review_path), review_sha256=review_hash, gate_records=evidence, admission=admission))
        record = dict(plan_sha256=approved, held682='HOLD_NOT_RUN', full942_dut_pass=False)
        eligible = False
        try:
            results = execute(data, RUN / 'replay', False, abort, review['units'])
            record['results'] = [dict(name=r.name, status=r.status, returncode=r.returncode,
                elapsed_s=r.elapsed_s, reason=r.reason, artifact_dir=str(r.artifact_dir)) for r in results]
            record['runner_evidence'] = terminal_inputs(results, RUN / 'replay')
            verify(data['pins'])
            old.identity()
            module_gate(data['pins'])
            old.require(sha(PLAN / 'plan.json') == approved and sha(review_path) == review_hash, 'Approval drift')
            old.require(all(sha(Path(x['path'])) == x['sha256'] for x in review['evidence'].values()), 'Gate drift')
            record['pins_unchanged'] = True
            record['calibration'] = [dict(name=r.name, elapsed_s=r.elapsed_s,
                **read(r.artifact_dir / 'architectural_trace_audit.json')) for r in results]
            eligible = True
        except BaseException as error:
            abort.set()
            record['error'] = f'{type(error).__name__}: {error}'
        record['finished'] = time.time()
        return int(not abort.publish(RUN / 'complete.json', record, eligible))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'work'])
    parser.add_argument('--authorize-run', action='store_true')
    parser.add_argument('--approved-plan-sha256')
    parser.add_argument('--review', type=Path)
    parser.add_argument('--review-sha256')
    args = parser.parse_args()
    env = prior.shared.environment()
    os.environ.clear()
    os.environ.update(env)
    if args.mode == 'prepare':
        prepare()
    else:
        raise SystemExit(work(args.approved_plan_sha256, args.review, args.review_sha256, args.authorize_run))

