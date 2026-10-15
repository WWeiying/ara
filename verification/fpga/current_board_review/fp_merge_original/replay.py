#!/usr/bin/env python3
"""One fixed original195-call M4 replay; preparation/audit never launch DUT."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'fp_comparison_original'))
import replay_restart_units as shared
import checker

read, save, sha, require = shared.read, shared.save, shared.sha, shared.old.require
PREP = HERE / 'prepared01'
PLAN = HERE / 'candidate04_plan01'
RUN = HERE / 'candidate04_run01'
UNIT = 'ara-fp-merge195-candidate04-01.service'
NAME = 'fp_merge_prefix195'
DEPENDENCY_REVIEW = shared.PLAN / 'parent_review.json'
DEPENDENCY_PLAN_SHA = '011540f110776d0c9296924f6d677f6c43ce8619ebaabd1f4b93d8f77b5b054a'
SOC_SHA = '01b9f6e58dec5ee13082e64211d23a37b94411d72051f517e3a0b46af479d124'


class Abort(shared.AbortLatch):
    def publish(self, path, record, eligible):
        require(threading.current_thread() is threading.main_thread() and len(threading.enumerate()) == 1,
                'Publication requires joined workers and main thread')
        good = dict(record, status='PASS_ORIGINAL_VFMERGE_PREFIX195_M4', aborted=False)
        bad = dict(record, status='NOT_PASS', aborted=True)
        good_path, bad_path = path.with_suffix('.pass.tmp'), path.with_suffix('.notpass.tmp')
        save(good_path, good)
        save(bad_path, bad)
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, shared.SIGNALS)
        try:
            with self.lock:
                require(self.terminal is None, 'Terminal publication is single-use')
                passed = eligible and not self.is_set() and not (signal.sigpending() & shared.SIGNALS)
                os.replace(good_path if passed else bad_path, path)
                self.terminal = passed
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)
            good_path.unlink(missing_ok=True)
            bad_path.unlink(missing_ok=True)
        return passed


def contract(data):
    require(data['unit'] == UNIT and data['jobs'] == 1 and data['test_timeout_s'] == 9000 and
            data['service_runtime_max_s'] == 9600 and data['stop_first_fail'] and data['no_build'] and
            data['retries'] == 0, 'Fixed execution contract differs')
    require(data['entry'] == read(PREP / 'programs.json')['soc'] and data['entry']['sha256'] == SOC_SHA and
            data['entry']['calls'] == 195 and data['dependency_plan_sha256'] == DEPENDENCY_PLAN_SHA,
            'Original ELF/oracle/dependency contract differs')


def resource_math(live, available, units):
    own = [p for p in live if UNIT in {x for line in p['cgroup'].splitlines() for x in line.split('/')}]
    require(UNIT not in units.values() and len(own) <= 1, 'Own/other unit collision or extra own simulator')
    rest = [p for p in live if p not in own]
    gate = shared.old.resource_math(rest, available, units)
    gate['total_live_plus_reserved'] += 1
    gate.update(own_slots=1, own_live=len(own), own_unit=UNIT)
    require(gate['total_live_plus_reserved'] <= 24, 'No slot: wait for parent-coordinated release; no retry')
    return gate


def resources(units):
    available = int(next(s.split()[1] for s in Path('/proc/meminfo').read_text().splitlines()
                         if s.startswith('MemAvailable:'))) * 1024
    return dict(time=time.time(), **resource_math(shared.scan_simv(), available, units))


def dependency_gate(data):
    review = read(DEPENDENCY_REVIEW)
    require(review['units'] == data['units'] and sha(shared.PLAN / 'plan.json') == DEPENDENCY_PLAN_SHA,
            'Reviewed roster/FP08 identity drift')
    # The reviewed helper supplies its own validated user-bus environment.
    return shared.dependency.gates(review, DEPENDENCY_PLAN_SHA)


def check_artifact(result, data):
    require(result.name == NAME and result.status == 'PASS' and result.returncode == 0 and not result.reason,
            'Result is not exact one PASS/rc0')
    folder = result.artifact_dir
    for path in (folder / 'console.log', folder / 'work/run.vcs.log'):
        checker.console(path.read_text())
    image = read(shared.prior.IMAGE / 'image.json')
    inputs = read(folder / 'inputs.json')
    require(sha(folder / 'input.elf') == SOC_SHA and inputs['binary'] == dict(
        source=data['entry']['path'], path=str(folder / 'input.elf'), sha256=SOC_SHA), 'Private ELF provenance differs')
    require(inputs['simv'] == dict(path=image['simv'], image_sha256=image['files']), 'Actual image metadata differs')
    command = read(folder / 'command.json')
    argv = command['command']
    require(command['cwd'] == str(folder / 'work') and argv[0] == image['simv'] and '+NO_FSDB' in argv,
            'Actual simulator command differs')
    for prefix, value in (('+PRELOAD=', str(folder / 'input.elf')), ('+TESTCASE=', NAME),
                          ('+COMMIT_TRACE=', str(folder / 'commit_trace.csv'))):
        require([x for x in argv if x.startswith(prefix)] == [prefix + value], 'Actual command identity differs')
    from ara_verify.trace import validate_trace
    path = folder / 'commit_trace.csv'
    generic = validate_trace(path)
    require(generic['cvx_exception_count'] == 0, 'CVX exception')
    return dict(generic=generic, original=checker.check_trace(path), trace_sha256=sha(path))


def runner_class(parent, data, abort, admission=None):
    class Checked(parent):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.cancel_event = abort

        def _run_test(self, test, image):
            mask = signal.pthread_sigmask(signal.SIG_BLOCK, shared.SIGNALS)
            try:
                if admission and not abort.is_set():
                    admission()
                result = super()._run_test(test, image)
                if result.status == 'PASS':
                    audit = check_artifact(result, data)
                    save(result.artifact_dir / 'original195_audit.json', audit)
                elif result.status != 'DRY_RUN':
                    abort.set()
                return abort.accept(result)
            except BaseException:
                abort.set()
                raise
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, mask)
    return Checked


def execute(data, output, dry, abort):
    contract(data)
    image, repo, (parent, options, case, _), engine = shared.old.identity()
    engine.FAIL_RE = checker.re.compile(engine.FAIL_RE.pattern + '|' + checker.BAD.pattern, engine.FAIL_RE.flags)
    admission = None if dry else lambda: save(RUN / 'dispatch_admission.json', resources(data['units']))
    cls = runner_class(parent, data, abort, admission)
    opts = options(repo, output, 'default', 1, 1, dry, False, True, Path(image['simv']), True, None)
    test = case(NAME, 'app', '', Path(data['entry']['path']), NAME, 9000)
    return cls(opts, [test], sys.argv).run()


def terminal(result, output):
    run, rows = read(output / 'run.json'), read(output / 'summary.json')
    require(run['status'] == 'COMPLETE' and run['status_counts'] == {'PASS': 1} and len(rows) == 1,
            'Runner interrupted/incomplete or wrong membership')
    row = rows[0]
    require(result.artifact_dir == output / 'tests' / NAME and
            result.name == row['name'] == NAME and result.status == row['status'] == 'PASS' and
            result.returncode == row['returncode'] == 0 and not result.reason and not row['reason'] and
            str(result.artifact_dir) == row['artifact_dir'], 'Runner summary disagreement')
    return dict(run_sha256=sha(output / 'run.json'), summary_sha256=sha(output / 'summary.json'))


def review_template(digest):
    return dict(parent_authorized=False, plan_sha256=digest,
        image_sha256=shared.prior.IMAGE_SHA, unit=UNIT, jobs=1,
        test_timeout_s=9000, service_runtime_max_s=9600, reservation_coordination_confirmed=False)


def prepare():
    require(not PLAN.exists() and not RUN.exists(), 'One fresh plan only')
    import audit
    text = io.StringIO()
    with contextlib.redirect_stdout(text):
        audit.main()
    image, repo, _, _ = shared.old.identity()
    PLAN.mkdir()
    save(PLAN / 'prepared_audit.json', json.loads(text.getvalue()))
    import unittest
    import test_plan
    with (PLAN / 'host_tests.log').open('x') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(test_plan))
    require(result.wasSuccessful(), 'Host gate failed')
    data = dict(status='PREPARED_NOT_AUTHORIZED', unit=UNIT, jobs=1, test_timeout_s=9000,
        service_runtime_max_s=9600, no_build=True, stop_first_fail=True, retries=0,
        entry=read(PREP / 'programs.json')['soc'], dependency_plan_sha256=DEPENDENCY_PLAN_SHA,
        units=read(DEPENDENCY_REVIEW)['units'], image_sha256=shared.prior.IMAGE_SHA,
        output=str(RUN), scope='Original ops0 partition195-call prefix; not full21504/Linux',
        budget_basis=dict(spike_retired=3382750, parent_startup_retired_per_s=800,
            extrapolated_s=3382750 / 800, limitation='Startup throughput is not full-run runtime; no completion promise'))
    abort = Abort()
    with abort.signals():
        rows = execute(data, PLAN / 'dryrun', True, abort)
    require(len(rows) == 1 and rows[0].name == NAME and rows[0].status == 'DRY_RUN' and not abort.is_set(), 'Dryrun scope')
    pins = read(PREP / 'pins.json')
    snapshot = Path(image['snapshot']) / 'snapshot.json'
    pins.update({str(repo / path): digest for path, digest in read(snapshot)['files'].items()})
    pins.update(image['files'])
    pins.update(shared.local_modules())
    dependencies = read(DEPENDENCY_REVIEW)['evidence']
    paths = [*HERE.glob('*.py'), HERE / 'host_model.c', HERE / 'README.md', HERE / 'LAUNCH.md',
        PREP / 'pins.json', PREP / 'complete.json', snapshot, shared.prior.IMAGE / 'image.json',
        Path(image['simv']).parent / 'vcs_source_manifest.json', Path(image['simv']).parent / 'simulator.conf',
        DEPENDENCY_REVIEW, shared.PLAN / 'plan.json', shared.prior.FINAL38 / 'plan.json',
        shared.dependency.GATHER / 'plan.json', *[Path(e['path']) for e in dependencies.values()],
        *[p for p in PLAN.rglob('*') if p.is_file()]]
    for path in paths:
        pins[str(path.resolve())] = sha(path)
    data['pins'] = pins
    contract(data)
    shared.verify(pins)
    shared.module_gate(pins)
    save(PLAN / 'plan.json', data)
    digest = sha(PLAN / 'plan.json')
    save(PLAN / 'review.template.json', review_template(digest))
    # Read-only host preflight; no Runner work/execute path is used here.
    dependencies = dependency_gate(data)
    admission = resources(data['units'])
    save(PLAN / 'preflight.json', dict(status='READY_NOT_LAUNCHED', plan_sha256=digest, pin_count=len(pins),
        tests=result.testsRun, VCS_started=False, dependencies=dependencies['dependency_admission'], resources=admission))
    print('READY_NOT_LAUNCHED', digest, flush=True)


def work(args):
    require(sys.flags.optimize == 0 and args.authorize_run and args.approved_plan_sha256 == sha(PLAN / 'plan.json'),
            'Explicit exact plan approval required')
    require(args.review and args.review_sha256 == sha(args.review), 'Pinned parent review required')
    require(not RUN.exists(), 'Fresh run only; no retry')
    abort = Abort()
    with abort.signals():
        data = read(PLAN / 'plan.json')
        contract(data)
        shared.verify(data['pins'])
        review = read(args.review)
        expected = review_template(args.approved_plan_sha256)
        expected.update(parent_authorized=True, reservation_coordination_confirmed=True)
        require(review == expected, 'Parent approval/limits/coordination differ')
        require(UNIT in {p for line in Path('/proc/self/cgroup').read_text().splitlines() for p in line.split('/')},
                'Worker must own the named service')
        dependency_gate(data)
        admission = resources(data['units'])
        shared.old.identity()
        shared.module_gate(data['pins'])
        require(not abort.is_set(), 'Aborted before launch')
        RUN.mkdir()
        save(RUN / 'launch.json', dict(plan_sha256=args.approved_plan_sha256, review_path=str(args.review),
            review_sha256=args.review_sha256, pid=os.getpid(), resources=admission, start=time.time()))
        record, eligible = dict(plan_sha256=args.approved_plan_sha256, calls=195, original_partition_complete=False), False
        try:
            results = execute(data, RUN / 'replay', False, abort)
            require(len(results) == 1, 'Wrong result cardinality')
            result = results[0]
            record['runner'] = terminal(result, RUN / 'replay')
            record['result'] = dict(name=result.name, status=result.status, returncode=result.returncode,
                elapsed_s=result.elapsed_s, reason=result.reason, artifact_dir=str(result.artifact_dir))
            record['audit_sha256'] = sha(result.artifact_dir / 'original195_audit.json')
            shared.verify(data['pins'])
            shared.old.identity()
            shared.module_gate(data['pins'])
            require(sha(PLAN / 'plan.json') == args.approved_plan_sha256 and sha(args.review) == args.review_sha256,
                    'Plan/review drift')
            record['pins_unchanged'], eligible = True, True
        except BaseException as error:
            abort.set()
            record['error'] = f'{type(error).__name__}: {error}'
        record['finished'] = time.time()
        return int(not abort.publish(RUN / 'complete.json', record, eligible))


def audit_plan(terminal_run=False):
    data = read(PLAN / 'plan.json')
    contract(data)
    shared.verify(data['pins'])
    shared.old.identity()
    shared.module_gate(data['pins'])
    if terminal_run:
        from types import SimpleNamespace
        complete = read(RUN / 'complete.json')
        require(complete['status'] == 'PASS_ORIGINAL_VFMERGE_PREFIX195_M4' and complete['aborted'] is False and
                complete['pins_unchanged'] is True and complete['plan_sha256'] == sha(PLAN / 'plan.json'), 'Not accepted terminal')
        result = SimpleNamespace(**complete['result'])
        result.artifact_dir = Path(result.artifact_dir)
        require(terminal(result, RUN / 'replay') == complete['runner'] and
                sha(result.artifact_dir / 'original195_audit.json') == complete['audit_sha256'], 'Stored audit/report drift')
        launch = read(RUN / 'launch.json')
        require(launch['plan_sha256'] == sha(PLAN / 'plan.json') and
                sha(Path(launch['review_path'])) == launch['review_sha256'], 'Launch approval drift')
        check_artifact(result, data)
    print(json.dumps(dict(status='INDEPENDENT_TERMINAL_PASS' if terminal_run else 'PLAN_AUDIT_PASS_NOT_DUT',
        plan_sha256=sha(PLAN / 'plan.json'), pins=len(data['pins']), jobs=1, calls=195), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'audit', 'terminal-audit', 'work'])
    parser.add_argument('--authorize-run', action='store_true')
    parser.add_argument('--approved-plan-sha256')
    parser.add_argument('--review', type=Path)
    parser.add_argument('--review-sha256')
    args = parser.parse_args()
    env = shared.prior.shared.environment()
    os.environ.clear()
    os.environ.update(env)
    if args.mode == 'prepare':
        prepare()
    elif args.mode in ('audit', 'terminal-audit'):
        audit_plan(args.mode == 'terminal-audit')
    else:
        raise SystemExit(work(args))
