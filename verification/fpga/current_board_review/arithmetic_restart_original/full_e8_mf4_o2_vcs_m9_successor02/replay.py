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

IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/campaign/image')
JOBS, CASE_BOUND, WORKER_BOUND, OUTER = 1, 10800, 12000, 13200
UNIT = 'ara-arithmetic-full-e8-mf4-m9-01.service'
PASS = 'PASS_M9_FULL_ORIGINAL_E8_MF4_4095_CALLS_NOT_LINUX'


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
    require(sha(REF/'READY.json') == READY_SHA, 'Frozen full e8 reference READY drift')
    ready = read(REF/'READY.json')
    require(ready['status'] == 'HOST_SPIKE_FULL_E8_MF4_CAP32_PASS_NOT_DUT' and
            [ready[k] for k in ('full_original_calls','result_elements','guards','vstart_checks')] == [4095,131040,8190,4095], 'Exact full e8 reference')
    for key,bound in (('actual_reference_exit',120),('actual_reference_audit_exit',600)):
        outcome=ready[key]
        require(type(outcome['returncode']) is int and outcome['returncode']==0 and
                not outcome['timeout'] and outcome['elapsed_s']<=bound,'Actual reference/parse numeric exit')
    require(ready['full_raw_parses']==ready['reference_attempts']==1 and ready['reference_reruns']==0,'No reference retries')
    require(ready['budget_decision'] == 'PLAUSIBLE_UNMEASURED_M9_REQUIRES_REVIEW' and
            ready['conservative_projected_s'] <= CASE_BOUND, 'No budget extension')
    require(sha(ready['evidence_pins'])==ready['evidence_pins_sha256'],'Reference evidence map drift')
    pins=dict(read(ready['evidence_pins']))
    pins[ready['evidence_pins']]=ready['evidence_pins_sha256']
    pins[str(REF/'READY.json')]=READY_SHA
    common.base.verify_pins(pins)
    return pins


def validate(plan, image):
    require(image == IMAGE and plan['status'] == 'PREPARED_NOT_RUN' and plan['image'] == str(image) and
            plan['image_sha256'] == sha(image / 'image.json'), 'M9 image identity')
    require(plan['cases'] == scope() and plan['jobs'] == JOBS and plan['case_timeout_s'] == CASE_BOUND and
            plan['worker_timeout_s'] == WORKER_BOUND and plan['service_timeout_s'] == OUTER and
            plan['unit'] == UNIT and all(plan[k] is True for k in ('no_build', 'no_retry', 'no_fsdb', 'stop_first_fail')),
            'Exact scope/budget/owner contract')
    require(plan['reference_ready_sha256'] == READY_SHA and plan['user_conditional_authorization'] is True,
            'Reference/entry gate drift')
    require(type(plan['reserved_slots']) is int and 0 <= plan['reserved_slots'] <= 24, 'Unused reservations only')
    require(plan['pins'].get(str(HERE / 'replay.py')) == sha(HERE / 'replay.py') and
            plan['pins'].get(str(HERE / 'checker.py')) == sha(HERE / 'checker.py'), 'Worker/checker drift')
    common.base.verify_pins(plan['pins'])
    require(plan['specs'] == {s: checker.specification(s) for s in SHAPES}, 'Actual ELF specs drift')


def prepare(image, out, reserved):
    require(image == IMAGE and not out.exists(), 'Exact M9/fresh owned output')
    pins = reference_pins()
    for path in (HERE.parent/'full_small2_vcs_m6_plan01/checker.py',
                 HERE.parent/'full_small2_reset_gpr_recovery01/reset_profile.json',
                 HERE.parent/'full_small2_reset_gpr_entry_review01/REVIEW.md'):
        pins[str(path)] = sha(path)
    checker.Strict(checker.specification(SHAPES[0]), read(REF/SHAPES[0]/'model.json'))
    ledger, repo, _ = common.image_context(image)
    require(Path(ledger['snapshot']).parent.name == 'current_board_memory_candidate09', 'M9 snapshot required')
    host = read(HERE / 'host01.json')
    require(host['status'] == 'PASS_HOST_ONLY' and host['failures'] == 0 and host['full_positive_shapes'] == list(SHAPES),
            'Full e8 Host oracle and real ABI entry required')
    require(host['actual_abi_entry_checked'] is True and host['tests'] >= 10, 'Actual e8 ABI Host missing')
    host_exit = read(HERE/'host_process_exit.json')
    require(host_exit['returncode'] == 0 and not host_exit['timed_out'], 'Actual Host process failed')
    common.base.verify_pins(host['pins'])
    pins.update(common.image_pins(image, ledger, repo))
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).is_file() and Path(path).resolve().is_relative_to(checker.G.parents[2]):
            pins[str(Path(path).resolve())] = sha(path)
    for n in ('checker.py', 'replay.py', 'test_host.py', 'reset_profile.json', 'host01.json', 'host01.log',
              'host_process_exit.json', 'run_host.py', 'host_records.py', 'prepare_profile.py',
              'exit_hook.py', 'README.md', 'USER_AUTHORIZATION.md'):
        pins[str(HERE / n)] = sha(HERE / n)
    plan = dict(status='PREPARED_NOT_RUN', image=str(image), image_sha256=sha(image / 'image.json'),
                snapshot_sha256=ledger['snapshot_sha256'], cases=scope(), specs={s: checker.specification(s) for s in SHAPES},
                pins=pins, jobs=JOBS, case_timeout_s=CASE_BOUND, worker_timeout_s=WORKER_BOUND,
                service_timeout_s=OUTER, unit=UNIT, reserved_slots=reserved, no_build=True, no_retry=True,
                no_fsdb=True, stop_first_fail=True, reference_ready_sha256=READY_SHA,
                user_conditional_authorization=True, resources_checked_only_at_run=True,
                scope='one full contiguous original e8 mf4 source program; not Linux/all22',
                cost=dict(budget_gate='FIT_PROJECTION_ONLY',
                          conservative_projection_s=read(REF/'READY.json')['conservative_projected_s']))
    validate(plan, image)
    out.mkdir()
    durable(out / 'plan.json', plan)
    digest = sha(out / 'plan.json')
    command = [sys.executable, '-B', str(HERE / 'replay.py'), 'run', '--image', str(image), '--out', str(out),
               '--plan-sha256', digest, '--authorize-run']
    service = ['systemd-run', '--user', '--unit=' + UNIT, '--property=RuntimeMaxSec=' + str(OUTER),
               '--property=KillMode=control-group', '--property=Restart=no', '--property=WorkingDirectory=' + str(HERE),
               '--property=StandardOutput=append:' + str(out / 'service.log'),
               '--property=StandardError=append:' + str(out / 'service.log'), *command]
    service.insert(-len(command), '--property=ExecStopPost='+shlex.join([
        sys.executable,'-B',str(HERE/'exit_hook.py'),'--out',str(out)]))
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
    require(entry_path is not None and entry_sha and sha(entry_path)==entry_sha and
            parent_path is None and parent_sha is None, 'Fresh independent entry review required')
    entry=read(entry_path)
    require(entry['status']=='NO_BLOCKER_ENTRY_REVIEW' and entry['plan_sha256']==digest and
            entry['image_sha256']==plan['image_sha256'] and entry['reference_ready_sha256']==READY_SHA and
            entry['scope']==[c['id'] for c in plan['cases']] and entry['pins']==plan['pins'],
            'Review must bind this exact full4095 M9 plan and all pins')
    path = HERE/'USER_AUTHORIZATION.md'
    require(plan['pins'].get(str(path)) == sha(path), 'Pinned user scope authorization')
    require(plan['cost']['conservative_projection_s'] <= CASE_BOUND and
            plan['cost']['budget_gate'] == 'FIT_PROJECTION_ONLY', 'Actual reference budget required')
    return {str(path): sha(path),str(entry_path):entry_sha}


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
                require(type(raw['returncode']) is int and raw['returncode'] == 0 and not raw['timed_out'] and not raw['failure_seen'] and
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
