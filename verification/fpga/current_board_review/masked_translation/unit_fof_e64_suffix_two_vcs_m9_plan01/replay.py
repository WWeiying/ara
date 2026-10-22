#!/usr/bin/env python3
"""No-build two-single M9 worker; prepare/dryrun never query live workers. Successor preserves sealed sources."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import shlex
import sys
import threading
import time
sys.dont_write_bytecode = True
import checker
from checker import HERE, G, REF, READY_SHA, IMAGE_SHA, common, read, sha, require, load

frozen = load('fof_frozen_batch', G / 'ordered_reduction/original_remaining9_vcs_m6_plan01/replay.py')
TERM = G/'arithmetic_restart_original/macc_disjoint482/full482_optimized_prepare01/vcs_m8_plan03/terminal_publish.py'
require(sha(TERM)=='495a2f91dde233c040eea231531d414b734184100b7c33a88dda98b6070ec718','Reviewed late-abort publisher')
terminal_publish=load('unit_fof_terminal_publish',TERM)
outcome = load('fof_frozen_outcome', G / 'fp_compare_unboxed_prefix265_vcs_m6_plan01/provenance_recovery01/adapter.py')
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/campaign/image')
JOBS, TIMEOUT, WORKER_BOUND, OUTER = 2, 1800, 3900, 4200
UNIT = 'ara-unit-fof-e64-two-m9-01.service'
PASS = 'PASS_M9_UNIT_FOF_E64_TWO_ORIGINAL_SINGLES_NOT_LINUX'

def validate(plan, image):
    require(image == IMAGE and plan['status'] == 'PREPARED_NOT_RUN' and plan['image'] == str(image)
            and plan['image_sha256'] == sha(image / 'image.json') == IMAGE_SHA, 'M9 image/plan drift')
    require(plan['cases'] == checker.scope() and plan['jobs'] == JOBS and plan['timeout_s'] == TIMEOUT
            and plan['worker_timeout_s'] == WORKER_BOUND and plan['service_timeout_s'] == OUTER
            and plan['unit'] == UNIT and all(plan[k] is True for k in ('no_build', 'no_retry', 'no_fsdb', 'stop_first_fail')),
            'Exact scope/budget/ownership')
    require(plan['reference_ready_sha256'] == READY_SHA, 'Reference binding')
    require(type(plan['reserved_slots']) is int and 0 <= plan['reserved_slots'] <= 24, 'Unused reservation only')
    original = read(REF / 'input_pins.json')
    require(len(original) == 732 and all(plan['pins'].get(p) == h for p, h in original.items()), 'Preserve every original732 pin')
    require(plan['pins'].get(str(HERE / 'replay.py')) == sha(HERE / 'replay.py'), 'Worker drift')
    require(plan['specs'] == {str(s): checker.specification(s) for s in checker.SHAPES}, 'Actual SoC spec drift')
    common.base.verify_pins(plan['pins'])

def terminal_plan_gate(out, digest, image):
    require(sha(out / 'plan.json') == digest, 'Fresh disk plan SHA')
    validate(read(out / 'plan.json'), image)
    require(sha(out / 'plan.json') == digest, 'Plan changed during validation')

def prepare(image, out, reserved):
    require(image == IMAGE and not out.exists(), 'Fresh output / exact M9')
    require(sha(REF / 'READY.json') == READY_SHA, 'READY drift')
    pins = dict(read(REF / 'input_pins.json'))
    require(sha(REF/'input_pins.json')==read(REF/'READY.json')['input_pins_sha256'],'Reference pins identity')
    pins[str(REF/'input_pins.json')]=sha(REF/'input_pins.json')
    pins[str(REF / 'READY.json')] = READY_SHA
    host = read(HERE / 'host02/status.json')
    require(host['status'] == 'PASS_HOST_ONLY_NOT_DUT' and host['failures'] == 0, 'Host gate')
    common.base.verify_pins(host['pins'])
    pins.update(host['pins'])
    ledger, repo, _ = common.image_context(image)
    pins.update(common.image_pins(image, ledger, repo))
    for module in list(sys.modules.values()):
        p = getattr(module, '__file__', None)
        if p and Path(p).is_file() and Path(p).resolve().is_relative_to(G.parents[2]):
            pins[str(Path(p).resolve())] = sha(Path(p))
    # The immutable oracle loads its decoder via importlib without registering it.
    for p in (Path(checker.source.__file__), checker.source.UTIL, Path(checker.source.u.decoder.__file__),
              *[HERE / n for n in ('checker.py', 'replay.py', 'test_worker.py', 'README.md', 'AUTHORIZATION.md',
                                   'source_owners.py', 'host02/status.json', 'host02/output.log', 'host02/execution.json')]):
        pins[str(p)] = sha(p)
    plan = dict(status='PREPARED_NOT_RUN', image=str(image), image_sha256=IMAGE_SHA,
        snapshot_sha256=ledger['snapshot_sha256'], cases=checker.scope(),
        specs={str(s): checker.specification(s) for s in checker.SHAPES}, pins=pins,
        jobs=JOBS, timeout_s=TIMEOUT, worker_timeout_s=WORKER_BOUND, service_timeout_s=OUTER,
        unit=UNIT, reserved_slots=reserved, no_build=True, no_retry=True, no_fsdb=True, stop_first_fail=True,
        reference_ready_sha256=READY_SHA, reference_original_pins=732,
        review_scope='Tesla final short review binds plan/worker/checker/reference; preparation only',
        budget=dict(firmware_records=[172731, 172731], slower_proxy_retire_per_s=273,
                    slower_proxy_plus20_s=[172731 / 273 * 1.2, 172731 / 273 * 1.2],
                    per_case_validation_reserve_s=300, guarantee=False, automatic_extension=False),
        resources_checked_only_at_authorized_run=True, durable_numeric_outcome_before_postcheck=True,
        scope='e64 scenario1 ordinary and scenario2 FOF; original VL8/full oracle, not Linux',
        zero_physical_MMU_activity_proved=False)
    validate(plan, image)
    out.mkdir()
    common.save(out / 'plan.json', plan)
    digest = sha(out / 'plan.json')
    command = [sys.executable, '-B', str(HERE / 'replay.py'), 'run', '--image', str(image), '--out', str(out),
               '--authorize-run', '--plan-sha256', digest, '--parent-review', 'TESLA_REVIEW_JSON',
               '--parent-review-sha256', 'TESLA_REVIEW_SHA256']
    service = ['systemd-run', '--user', '--unit=' + UNIT, '--property=RuntimeMaxSec=' + str(OUTER),
               '--property=KillMode=control-group', '--property=Restart=no', '--property=WorkingDirectory=' + str(HERE),
               '--property=StandardOutput=append:' + str(out / 'service.log'),
               '--property=StandardError=append:' + str(out / 'service.log'), *command]
    common.save(out / 'ready.json', dict(status='PREPARED_NOT_LAUNCHED_PARENT_AUTHORIZATION_REQUIRED',
        plan_sha256=digest, command=command, service_command=shlex.join(service), pins=len(pins), DUT_started=False))
    print('PREPARED_NOT_LAUNCHED', digest, flush=True)

def owner_gate(p, cgroup, pid):
    names = {'Id', 'LoadState', 'ActiveState', 'SubState', 'MainPID', 'ControlGroup', 'RuntimeMaxUSec', 'KillMode', 'Restart'}
    require(set(p) == names and p['Id'] == UNIT and p['LoadState'] == 'loaded' and p['ActiveState'] == 'active'
            and p['SubState'] == 'running' and p['MainPID'] == str(pid) and p['ControlGroup'].endswith('/' + UNIT)
            and p['ControlGroup'] in [s.split(':', 2)[-1] for s in cgroup.splitlines()]
            and p['RuntimeMaxUSec'] == '1h 10min' and p['KillMode'] == 'control-group' and p['Restart'] == 'no',
            'Actual direct service owner/hard budget')

def authorization_gate(plan, digest, path, review_sha):
    require(path and review_sha and sha(path) == review_sha, 'Pinned Tesla short review')
    r = read(path)
    require(r['decision']=='NO_BLOCKER' and r['blockers']==[] and r['plan_sha256']==digest
            and r['worker_sha256']==sha(HERE/'replay.py') and r['checker_sha256']==sha(HERE/'checker.py')
            and r['reference_ready_sha256']==READY_SHA, 'Exact independent review binding')
    return {str(path): review_sha}

def durable_monitor(original, abort):
    def monitored(command, cwd, console_path, timeout_s, cancel_event=None):
        try:
            rc, elapsed, timed_out, failure_seen = original(command, cwd, console_path, timeout_s, cancel_event)
        except BaseException:
            abort.set()
            raise
        require(type(rc) is int, 'Actual numeric process wait outcome required')
        r = dict(schema='UNVALIDATED_MONITOR_OUTCOME_V1', architectural_acceptance=False,
            returncode=rc, elapsed_s=elapsed, timed_out=timed_out, failure_seen=failure_seen,
            abort_set=bool(cancel_event and cancel_event.is_set()), command=list(map(str, command)), cwd=str(cwd),
            command_sha256=sha(Path(console_path).parent / 'command.json'))
        with (Path(console_path).parent / 'monitor_outcome.unvalidated.json').open('x') as stream:
            json.dump(r, stream, indent=2)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        if rc != 0 or timed_out or failure_seen or bool(cancel_event and cancel_event.is_set()):
            abort.set()
        return rc, elapsed, timed_out, failure_seen
    return monitored

def checked_runner(parent, abort, check, admission):
    class DurableParent(parent):
        def _run_test(self, test, image):
            result = super()._run_test(test, image)
            outcome.persist_unvalidated_outcome(result)
            return result
    return frozen.checked_runner(DurableParent, abort, check, admission)

def options_for(options, repo, out, ledger, dry=False):
    return options(repo_root=repo, output_root=out / ('dryrun' if dry else 'replay'), config='default',
                   jobs=JOBS, seed=1, dry_run=dry, build_only=False, skip_build=True,
                   simv=Path(ledger['simv']), commit_trace=True, timeout_s=TIMEOUT)

def tests_for(testcase, cases):
    return [testcase(c['id'], 'app', '', Path(c['elf']), c['id'], TIMEOUT) for c in cases]

def dryrun(image, out, digest):
    terminal_plan_gate(out, digest, image)
    require(not (out / 'dryrun').exists(), 'Fresh dryrun only')
    ledger, repo, (parent, options, testcase, _) = common.image_context(image)
    cases = read(out / 'plan.json')['cases']
    results = parent(options_for(options, repo, out, ledger, True), tests_for(testcase, cases), sys.argv).run()
    require([r.name for r in results] == [c['id'] for c in cases] and all(r.status == 'DRY_RUN' for r in results), 'Exact2 dryrun')
    terminal_plan_gate(out, digest, image)
    common.save(out / 'dryrun_gate.json', dict(status='DRYRUN_ONLY_NO_DUT', plan_sha256=digest,
                                            cases=[r.name for r in results], jobs=JOBS))

def run(image, out, digest, authorized, review, review_sha):
    require(authorized and digest, 'Explicit new run authorization')
    terminal_plan_gate(out, digest, image)
    plan = read(out / 'plan.json')
    approval = authorization_gate(plan, digest, review, review_sha)
    ledger, repo, (parent, options, testcase, _) = common.image_context(image)
    require(ledger['snapshot_sha256'] == plan['snapshot_sha256'], 'Snapshot drift')
    frozen.UNIT, frozen.owner_gate = UNIT, owner_gate
    owner = frozen.service_identity()
    resource = common.resources(out, JOBS, plan['reserved_slots'])
    with (out / 'launch.json').open('x') as stream:
        json.dump(dict(owner=owner, resources=resource, approval_pins=approval, started=time.time(), plan_sha256=digest), stream, indent=2)
    abort = terminal_publish.TerminalAbort()
    deadline = time.monotonic() + WORKER_BOUND
    timer = threading.Timer(WORKER_BOUND, abort.set)
    timer.daemon = True
    terminal = dict(status='NOT_PASS', plan_sha256=digest, image_sha256=IMAGE_SHA, results=[], retries=0, pins_unchanged=False)
    import ara_verify.runner as engine
    from ara_verify.trace import validate_trace
    old_fail, old_monitor = engine.FAIL_RE, engine._run_monitored
    engine.FAIL_RE = re.compile(old_fail.pattern + '|' + checker.VETO.pattern, re.I)
    # Patch once around the whole two-thread runner, never once per overlapping test.
    engine._run_monitored = durable_monitor(old_monitor, abort)
    with common.abort_signals(abort):
        timer.start()
        try:
            require(not (out / 'replay').exists(), 'No retries/overwrite')
            entries = {c['id']: c for c in plan['cases']}
            def admission(name):
                require(name in entries and not abort.is_set() and time.monotonic() + TIMEOUT + 300 <= deadline,
                        'Aborted/unknown/insufficient unchanged deadline')
            def check(result):
                case = entries[result.name]
                strict = checker.artifacts(result, case, ledger, plan['specs'][str(case['scenario'])], validate_trace)
                common.save(result.artifact_dir / 'strict_original.json', strict)
            results = checked_runner(parent, abort, check, admission)(
                options_for(options, repo, out, ledger), tests_for(testcase, plan['cases']), sys.argv).run()
            terminal['results'] = [dict(asdict(r), artifact_dir=str(r.artifact_dir)) for r in results]
            meta = read(out / 'replay/run.json')
            common.check_stage(results, meta, plan['cases'], abort)
            require(meta['tests'] == [c['id'] for c in plan['cases']] and meta['jobs'] == JOBS
                    and meta['timeout_s'] == TIMEOUT and meta['seed'] == 1 and meta['simv'] == ledger['simv']
                    and meta['commit_trace'] is True and meta['code_coverage'] is False, 'Exact COMPLETE runner contract')
            require(read(out / 'replay/summary.json') == terminal['results'], 'Summary mismatch')
            terminal_plan_gate(out, digest, image)
            common.image_context(image)
            common.base.verify_pins(approval)
            evidence = {str(p): sha(p) for p in (out / 'launch.json', out / 'replay/run.json', out / 'replay/summary.json')}
            for case in plan['cases']:
                root = out / 'replay/tests' / case['id']
                for name in ('input.elf', 'inputs.json', 'command.json', 'console.log', 'work/run.vcs.log',
                             'commit_trace.csv', 'trace_summary.json', 'monitor_outcome.unvalidated.json',
                             'child_outcome.unvalidated.json', 'strict_csv.json', 'strict_original.json'):
                    evidence[str(root / name)] = sha(root / name)
            require(sha(out / 'plan.json') == digest, 'Final disk plan drift')
            terminal.update(status=PASS, evidence_pins=evidence, pins_unchanged=True,
                            all8_historical_or_Linux_accepted=False, zero_MMU_physical_activity_proved=False)
        except BaseException as error:
            abort.set()
            terminal.update(status='NOT_PASS', error=f'{type(error).__name__}: {error}')
            common.save(out/'firstfailure.json', dict(error=terminal['error'],time=time.time()))
            if (out / 'replay/summary.json').exists():
                terminal['results'] = read(out / 'replay/summary.json')
        finally:
            frozen.quiesce_deadline(timer, abort, deadline)
            engine.FAIL_RE, engine._run_monitored = old_fail, old_monitor
            terminal['finished'] = time.time()
            terminal_publish.publish(out, terminal, abort, deadline)
    print(terminal['status'], flush=True)
    return int(terminal['status'] != PASS)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['prepare', 'dryrun', 'run'])
    for name in ('image', 'out', 'parent-review'):
        p.add_argument('--' + name, type=Path, required=name != 'parent-review')
    p.add_argument('--reserved-slots', type=int, default=0)
    for name in ('authorize-prepare', 'authorize-run'):
        p.add_argument('--' + name, action='store_true')
    for name in ('plan-sha256', 'parent-review-sha256'):
        p.add_argument('--' + name)
    a = p.parse_args()
    image, out = a.image.resolve(), a.out.resolve()
    require(out.parent == HERE, 'Owned direct child only')
    env = common.base.shared.environment()
    env.update(XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}',DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
    os.environ.clear(); os.environ.update(env)
    if a.mode == 'prepare':
        require(a.authorize_prepare, 'Explicit prepare authorization')
        prepare(image, out, a.reserved_slots)
        return 0
    if a.mode == 'dryrun':
        dryrun(image, out, a.plan_sha256)
        return 0
    return run(image, out, a.plan_sha256, a.authorize_run, a.parent_review, a.parent_review_sha256)

if __name__ == '__main__':
    raise SystemExit(main())
