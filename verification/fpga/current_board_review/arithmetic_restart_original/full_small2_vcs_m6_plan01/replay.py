#!/usr/bin/env python3
"""Prepare/dryrun only without explicit reviewed authorization. Never builds."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import threading
import time

sys.dont_write_bytecode = True
import checker
from checker import HERE, REF, SHAPES, READY_SHA, read, sha, require, common

IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image')
JOBS, CASE_BOUND, WORKER_BOUND, OUTER = 2, 10800, 12000, 13200
UNIT = 'ara-arithmetic-full-small2-m6-01.service'
PASS = 'PASS_M6_FULL_ORIGINAL_SMALL2_10080_CALLS_NOT_LINUX'


def durable(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def scope():
    cases = []
    for shape in SHAPES:
        spec = checker.specification(shape)
        p = spec['config']
        cases.append(dict(id=shape.replace('rvv_matrix_', 'arithmetic_full_'), original_name=shape,
                          shape=shape, elf=spec['backend']['elf'], sha256=spec['backend']['sha256'],
                          timeout_s=CASE_BOUND, pass_markers=[checker.marker(p),
                              'ARITHMETIC_FULL_PASS ' + shape, 'BOARD_REPLAY_PASS']))
    return cases


def reference_pins():
    require(sha(REF / 'READY.json') == READY_SHA, 'Frozen reference READY drift')
    ready = read(REF / 'READY.json')
    require(ready['status'] == 'FULL2_REFERENCE_RECOVERY_PASS_PENDING_INDEPENDENT_REVIEW_NOT_DUT' and
            ready['totals'] == dict(calls=10080, results=161280, guards=20160, vstart_checks=10080), 'Exact complete reference scope')
    pins = {**ready['evidence_pins'], **read(REF / 'recovery01/fullparse01/input_pins.json')}
    pins[str(REF / 'READY.json')] = READY_SHA
    common.base.verify_pins(pins)
    outcome = read(REF / 'recovery01/execution01/outcome.json')
    require(type(outcome['returncode']) is int and outcome['returncode'] == 0 and not outcome['timeout'] and
            outcome['elapsed_s'] <= 600, 'Actual offline wait outcome')
    return pins


def validate(plan, image):
    require(image == IMAGE and plan['status'] == 'PREPARED_NOT_RUN' and plan['image'] == str(image) and
            plan['image_sha256'] == sha(image / 'image.json'), 'M6 image identity')
    require(plan['cases'] == scope() and plan['jobs'] == JOBS and plan['case_timeout_s'] == CASE_BOUND and
            plan['worker_timeout_s'] == WORKER_BOUND and plan['service_timeout_s'] == OUTER and
            plan['unit'] == UNIT and all(plan[k] is True for k in ('no_build', 'no_retry', 'no_fsdb', 'stop_first_fail')),
            'Exact scope/budget/owner contract')
    require(plan['reference_ready_sha256'] == READY_SHA and plan['independent_entry_audit_pending'] is True,
            'Reference/entry gate drift')
    require(type(plan['reserved_slots']) is int and 0 <= plan['reserved_slots'] <= 24, 'Unused reservations only')
    require(plan['pins'].get(str(HERE / 'replay.py')) == sha(HERE / 'replay.py') and
            plan['pins'].get(str(HERE / 'checker.py')) == sha(HERE / 'checker.py'), 'Worker/checker drift')
    common.base.verify_pins(plan['pins'])
    require(plan['specs'] == {s: checker.specification(s) for s in SHAPES}, 'Actual ELF specs drift')


def prepare(image, out, reserved):
    require(image == IMAGE and not out.exists(), 'Exact M6/fresh owned output')
    pins = reference_pins()
    ledger, repo, _ = common.image_context(image)
    require(Path(ledger['snapshot']).parent.name == 'current_board_memory_candidate06', 'M6 snapshot required')
    host = read(HERE / 'host03.json')
    require(host['status'] == 'PASS_HOST_ONLY' and host['failures'] == 0 and host['full_positive_shapes'] == list(SHAPES),
            'Both complete Host oracles required')
    common.base.verify_pins(host['pins'])
    pins.update(common.image_pins(image, ledger, repo))
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).is_file() and Path(path).resolve().is_relative_to(checker.G.parents[2]):
            pins[str(Path(path).resolve())] = sha(path)
    for n in ('checker.py', 'replay.py', 'test_host.py', 'host01.json', 'host01.log', 'host02.interrupted.json',
              'host02.log', 'host03.json', 'host03.log', 'README.md'):
        pins[str(HERE / n)] = sha(HERE / n)
    plan = dict(status='PREPARED_NOT_RUN', image=str(image), image_sha256=sha(image / 'image.json'),
                snapshot_sha256=ledger['snapshot_sha256'], cases=scope(), specs={s: checker.specification(s) for s in SHAPES},
                pins=pins, jobs=JOBS, case_timeout_s=CASE_BOUND, worker_timeout_s=WORKER_BOUND,
                service_timeout_s=OUTER, unit=UNIT, reserved_slots=reserved, no_build=True, no_retry=True,
                no_fsdb=True, stop_first_fail=True, reference_ready_sha256=READY_SHA,
                independent_entry_audit_pending=True, resources_checked_only_at_run=True,
                scope='two full contiguous original source programs, not Linux/all22',
                cost=dict(firmware=[4406446,5922051], proxy_image='candidate04 prefix5',
                          observed_instructions_per_second=[619.182818,686.494927],
                          slow_proxy_plus20percent_s=[8539.861005,11477.161505],
                          e32_margin_exceeds_fixed_case_budget=True, completion_guaranteed=False))
    validate(plan, image)
    out.mkdir()
    durable(out / 'plan.json', plan)
    digest = sha(out / 'plan.json')
    command = [sys.executable, '-B', str(HERE / 'replay.py'), 'run', '--image', str(image), '--out', str(out),
               '--plan-sha256', digest, '--authorize-run', '--entry-review', 'ENTRY_REVIEW_JSON',
               '--entry-review-sha256', 'ENTRY_SHA', '--parent-review', 'PARENT_REVIEW_JSON',
               '--parent-review-sha256', 'PARENT_SHA']
    service = ['systemd-run', '--user', '--unit=' + UNIT, '--property=RuntimeMaxSec=' + str(OUTER),
               '--property=KillMode=control-group', '--property=Restart=no', '--property=WorkingDirectory=' + str(HERE),
               '--property=StandardOutput=append:' + str(out / 'service.log'),
               '--property=StandardError=append:' + str(out / 'service.log'), *command]
    durable(out / 'ready.json', dict(status='PREPARED_NOT_ADMITTED_NO_DUT', plan_sha256=digest,
            command=command, service_command=shlex.join(service), pin_count=len(pins), DUT_started=False))
    print('PREPARED_NOT_ADMITTED_NO_DUT', digest, flush=True)


def owner_gate(props, group, pid):
    fields = {'Id', 'LoadState', 'ActiveState', 'SubState', 'MainPID', 'ControlGroup', 'RuntimeMaxUSec', 'KillMode', 'Restart'}
    require(set(props) == fields and props['Id'] == UNIT and props['LoadState'] == 'loaded' and
            props['ActiveState'] == 'active' and props['SubState'] == 'running' and props['MainPID'] == str(pid) and
            props['ControlGroup'].endswith('/' + UNIT) and props['ControlGroup'] in
            [s.split(':', 2)[-1] for s in group.splitlines()] and props['RuntimeMaxUSec'] == '3h 40min' and
            props['KillMode'] == 'control-group' and props['Restart'] == 'no', 'Direct service ownership/bounds')


def service_identity():
    runtime = Path('/run/user') / str(os.getuid())
    require(runtime.is_dir() and runtime.stat().st_uid == os.getuid() and (runtime / 'bus').is_socket(), 'Trusted user bus')
    env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime), DBUS_SESSION_BUS_ADDRESS='unix:path=' + str(runtime / 'bus'))
    fields = 'Id,LoadState,ActiveState,SubState,MainPID,ControlGroup,RuntimeMaxUSec,KillMode,Restart'
    q = subprocess.run(['systemctl', '--user', 'show', UNIT, '--property=' + fields], env=env,
                       text=True, capture_output=True, timeout=10)
    require(q.returncode == 0 and not q.stderr.strip(), 'Service query failure')
    props = dict(line.split('=', 1) for line in q.stdout.splitlines())
    group = Path('/proc/self/cgroup').read_text()
    owner_gate(props, group, os.getpid())
    return dict(properties=props, cgroup=group, pid=os.getpid())


def reviews(plan, digest, entry_path, entry_sha, parent_path, parent_sha):
    require(entry_path and entry_sha and parent_path and parent_sha and
            sha(entry_path) == entry_sha and sha(parent_path) == parent_sha, 'Pinned independent entry and parent reviews required')
    entry, parent = read(entry_path), read(parent_path)
    require(entry['decision'] == 'APPROVE_FULL_SMALL2_M6_ENTRY' and entry['plan_sha256'] == digest and
            entry['image_sha256'] == plan['image_sha256'] and entry['reference_ready_sha256'] == READY_SHA and
            entry['full_reference_scope_accepted'] is True and entry['checker_host_reviewed'] is True,
            'Independent full-reference/entry acceptance required')
    require(parent['decision'] == 'AUTHORIZE_FULL_SMALL2_M6_ONCE' and parent['plan_sha256'] == digest and
            parent['entry_review_sha256'] == entry_sha and parent['unit'] == UNIT and
            parent['budget_risk_accepted'] is True, 'New parent authorization/budget required')
    pins = dict(entry['evidence_pins'])
    require(all(pins.get(str(p)) == sha(p) for p in (REF / 'READY.json', HERE / 'checker.py', HERE / 'host03.json')),
            'Independent entry evidence must bind actual inputs')
    common.base.verify_pins(pins)
    pins.update({str(entry_path): entry_sha, str(parent_path): parent_sha})
    return pins


def monitored_with_outcome(original, abort):
    def monitored(command, cwd, console, timeout, cancel_event=None):
        result = original(command, cwd, console, timeout, cancel_event)
        rc, elapsed, timed_out, failure_seen = result
        require(type(rc) is int, 'Actual numeric wait outcome required')
        root = Path(console).parent
        durable(root / 'child_outcome.unvalidated.json', dict(schema='UNVALIDATED_CHILD_OUTCOME_V2',
                architectural_acceptance=False, returncode=rc, elapsed_s=elapsed, timed_out=timed_out,
                failure_seen=failure_seen, cancelled=bool(cancel_event and cancel_event.is_set()),
                command=[str(x) for x in command], cwd=str(cwd), command_sha256=sha(root / 'command.json')))
        if rc != 0 or timed_out or failure_seen:
            abort.set()
        return result
    return monitored


def checked_runner(parent, abort, check, admission):
    class Runner(parent):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.cancel_event = abort

        def _run_test(self, test, image):
            result = None
            try:
                if not abort.is_set():
                    admission(test.name)
                result = super()._run_test(test, image)
                if result.status == 'PASS':
                    check(result)
                    if abort.is_set():
                        result.status, result.reason = 'CANCELLED', 'Abort during full validation'
                if result.status != 'PASS':
                    abort.set()
                return result
            except BaseException as error:
                abort.set()
                if result is not None:
                    result.status, result.reason = 'ERROR', f'Postcheck {type(error).__name__}: {error}'
                    return result
                raise
    return Runner


def terminal_disk_gate(out, digest, image):
    require(sha(out / 'plan.json') == digest, 'Late disk plan drift')
    validate(read(out / 'plan.json'), image)


def run(image, out, digest, authorized, entry_path, entry_sha, parent_path, parent_sha):
    require(authorized and digest and sha(out / 'plan.json') == digest, 'Explicit reviewed run gate')
    plan = read(out / 'plan.json')
    validate(plan, image)
    review_pins = reviews(plan, digest, entry_path, entry_sha, parent_path, parent_sha)
    ledger, repo, (base, options, testcase, _) = common.image_context(image)
    owner = service_identity()
    resource = common.resources(out, JOBS, plan['reserved_slots'])
    durable(out / 'launch.json', dict(started=time.time(), owner=owner, resources=resource, plan_sha256=digest))
    require(not (out / 'replay').exists(), 'No retry or overwrite')
    abort = threading.Event()
    deadline = time.monotonic() + WORKER_BOUND
    timer = threading.Timer(WORKER_BOUND, abort.set)
    timer.daemon = True
    import ara_verify.runner as engine
    old_monitor, old_fail = engine._run_monitored, engine.FAIL_RE
    engine._run_monitored = monitored_with_outcome(old_monitor, abort)
    engine.FAIL_RE = re.compile(old_fail.pattern + '|' + checker.VETO.pattern, re.I)
    terminal = dict(status='NOT_PASS', plan_sha256=digest, results=[], pins_unchanged=False, retries=0)
    with common.abort_signals(abort):
        timer.start()
        try:
            entries = {c['id']: c for c in plan['cases']}
            def admission(name):
                require(name in entries and time.monotonic() + CASE_BOUND + 900 <= deadline,
                        'Insufficient unchanged case/observer budget: NOT_RUN, no retry')
            def check(result):
                case = entries[result.name]
                raw = read(result.artifact_dir / 'child_outcome.unvalidated.json')
                require(raw['returncode'] == 0 and not raw['timed_out'] and not raw['failure_seen'] and
                        not raw['cancelled'] and raw['elapsed_s'] == result.elapsed_s, 'Durable child outcome differs')
                report = checker.artifacts(result, case, ledger, plan['specs'][case['shape']], abort)
                durable(result.artifact_dir / 'strict_original.json', report)
            opts = options(repo_root=repo, output_root=out / 'replay', config='default', jobs=JOBS, seed=1,
                           dry_run=False, build_only=False, skip_build=True, simv=Path(ledger['simv']),
                           commit_trace=True, timeout_s=CASE_BOUND)
            tests = [testcase(c['id'], 'app', '', Path(c['elf']), c['id'], CASE_BOUND) for c in plan['cases']]
            results = checked_runner(base, abort, check, admission)(opts, tests, sys.argv).run()
            terminal['results'] = [dict(asdict(r), artifact_dir=str(r.artifact_dir)) for r in results]
            metadata = read(out / 'replay/run.json')
            common.check_stage(results, metadata, plan['cases'], abort)
            require(metadata['tests'] == [c['id'] for c in plan['cases']] and metadata['jobs'] == JOBS and
                    metadata['timeout_s'] == CASE_BOUND and metadata['simv'] == ledger['simv'] and
                    metadata['commit_trace'] is True and metadata['code_coverage'] is False and metadata['completed_at'],
                    'Exact runner COMPLETE contract')
            require(read(out / 'replay/summary.json') == terminal['results'], 'Raw summary disagreement')
            terminal_disk_gate(out, digest, image)
            common.image_context(image)
            common.base.verify_pins(review_pins)
            evidence = {str(p): sha(p) for p in (out / 'launch.json', out / 'replay/run.json', out / 'replay/summary.json')}
            for c in plan['cases']:
                root = out / 'replay/tests' / c['id']
                for n in ('input.elf', 'inputs.json', 'command.json', 'console.log', 'work/run.vcs.log',
                          'child_outcome.unvalidated.json', 'commit_trace.csv', 'trace_summary.json', 'strict_original.json'):
                    evidence[str(root / n)] = sha(root / n)
            terminal.update(status=PASS, evidence_pins=evidence, approval_pins=review_pins, pins_unchanged=True)
        except BaseException as error:
            abort.set()
            terminal.update(status='NOT_PASS', error=f'{type(error).__name__}: {error}')
            if (out / 'replay/summary.json').exists():
                terminal['results'] = read(out / 'replay/summary.json')
        finally:
            timer.cancel()
            timer.join()
            if time.monotonic() >= deadline:
                abort.set()
            engine._run_monitored, engine.FAIL_RE = old_monitor, old_fail
            terminal['finished'] = time.time()
            common.publish(out, terminal, abort)
    print(terminal['status'], flush=True)
    return int(terminal['status'] != PASS)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'dryrun', 'run'))
    for name in ('image', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    for name in ('authorize-prepare', 'authorize-run'):
        p.add_argument('--' + name, action='store_true')
    p.add_argument('--reserved-slots', type=int, default=0)
    for name in ('plan-sha256', 'entry-review-sha256', 'parent-review-sha256'):
        p.add_argument('--' + name)
    for name in ('entry-review', 'parent-review'):
        p.add_argument('--' + name, type=Path)
    a = p.parse_args()
    image, out = a.image.resolve(), a.out.resolve()
    require(out.parent == HERE, 'Owned direct-child output only')
    env = common.base.shared.environment()
    os.environ.clear()
    os.environ.update(env)
    if a.mode == 'prepare':
        require(a.authorize_prepare, 'Explicit prepare authorization')
        prepare(image, out, a.reserved_slots)
        return 0
    if a.mode == 'dryrun':
        require(a.plan_sha256 and sha(out / 'plan.json') == a.plan_sha256, 'Pinned dryrun plan')
        plan = read(out / 'plan.json')
        validate(plan, image)
        ledger, _, _ = common.image_context(image)
        commands = []
        for c in plan['cases']:
            root = out / 'replay/tests' / c['id']
            commands.append(dict(cwd=str(root / 'work'), command=[ledger['simv'], '-l', 'run.vcs.log',
                '+ntb_random_seed=1', '+PRELOAD=' + str(root / 'input.elf'), '+TESTCASE=' + c['id'],
                '+NO_FSDB', '+COMMIT_TRACE=' + str(root / 'commit_trace.csv')]))
        durable(out / 'dryrun.json', dict(status='DRYRUN_ONLY_NO_PROCESS', plan_sha256=a.plan_sha256, commands=commands))
        print('DRYRUN_ONLY_NO_PROCESS', len(commands))
        return 0
    return run(image, out, a.plan_sha256, a.authorize_run, a.entry_review, a.entry_review_sha256,
               a.parent_review, a.parent_review_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
