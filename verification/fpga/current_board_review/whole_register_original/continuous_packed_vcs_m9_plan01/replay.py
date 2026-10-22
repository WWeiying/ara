#!/usr/bin/env python3
"""Prepare/dryrun only without explicit reviewed authorization. Never builds."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import threading
import time

sys.dont_write_bytecode = True
import checker
from checker import HERE, REF, SHAPES, READY_SHA, read, sha, require, common

IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate09/campaign/image')
JOBS, CASE_BOUND, WORKER_BOUND, OUTER = 1, 10800, 12000, 13200
UNIT = 'ara-whole-continuous1134-m9-01.service'
PASS = 'PASS_M9_FULL_CONTINUOUS_WHOLE1134_NOT_LINUX'


def durable(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


class TerminalAbort(threading.Event):
    def __init__(self):
        super().__init__();self.lock=threading.RLock();self.closed=False

    def set(self):
        with self.lock:
            if not self.closed:super().set()


def write_json(path,data,mode='x'):
    with path.open(mode) as stream:
        json.dump(data,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())


def failed(terminal,abort):
    abort.set();terminal.update(status='NOT_ACCEPTED_LATE_ABORT',aborted=True)


def publish(out,terminal,abort,expires):
    signals={signal.SIGINT,signal.SIGTERM}
    previous=signal.pthread_sigmask(signal.SIG_BLOCK,signals)
    temporary=out/'complete.pending.json';target=out/'complete.json'
    try:
        if target.exists():raise ValueError('No terminal overwrite')
        terminal['aborted']=abort.is_set()
        write_json(temporary,terminal)
        with abort.lock:
            if abort.is_set() or signal.sigpending() & signals or time.monotonic()>=expires:
                failed(terminal,abort);write_json(temporary,terminal,mode='w')
            os.replace(temporary,target)
    finally:
        # Pending handlers still affect the open latch. In particular a signal
        # arriving inside rename must not be discarded by premature closure.
        signal.pthread_sigmask(signal.SIG_SETMASK,previous)
    with abort.lock:
        # Freeze the cancellation flags at one explicit point after restoring
        # handlers. A handler that already set abort cannot be lost between a
        # conditional read and latch closure; post-seal cancellation is later.
        abort.closed=True
        if abort.is_set() or time.monotonic()>=expires:
            threading.Event.set(abort)
            if terminal['status']!='NOT_ACCEPTED_LATE_ABORT':
                terminal.update(status='NOT_ACCEPTED_LATE_ABORT',aborted=True)
                try:
                    write_json(temporary,terminal);os.replace(temporary,target)
                except BaseException:
                    # An unpublishable correction must not leave candidate PASS.
                    target.unlink(missing_ok=True)
                    raise
        # Before worker exit, its return status and the atomically visible final
        # record agree. Any candidate visible earlier requires actual worker0.
    # Only file fsync+atomic visibility are claimed, not directory power-loss
    # durability; there is no new fallible directory IO after the decision.


def scope():
    spec = checker.specification('whole_all')
    return [dict(id='whole_continuous_packed1134',original_name='whole_all',shape='whole_all',
                 elf=spec['backend']['elf'],sha256=spec['backend']['sha256'],
                 timeout_s=CASE_BOUND,pass_markers=checker.EXPECTED_TEXT.splitlines())]


def reference_pins():
    pins = checker.reference_pins()
    require(isinstance(pins,dict) and pins, 'Actual full1134 reference pins required')
    require(sha(REF/'RESULT.json') == READY_SHA ==
            'a6423a31855de08ad5010d3209e7b7dacf07a1e0c7752c9265c123971e79ff68', 'Exact corrected02 reference')
    require(sha(REF/'OUTCOME.json')=='3896e21b6739d9693790b22987c43bf168fe35ea46dd2af1e2c37c124b6a84db',
            'Accepted measured-cost outcome identity')
    outcome = read(REF/'OUTCOME.json')
    require(outcome['status']=='FULL1134_PACKED_REFERENCE_ACCEPTED_PROXY_UNDER3H_NOT_DUT' and
            outcome['pins_before_after_unchanged'] is True and outcome['reference_attempts']==outcome['raw_parses']==1,
            'Complete single reference receipt')
    reference=outcome['reference']
    require([reference[k] for k in ('calls','exclusions','output_byte_checks','fresh_input_stores',
                                   'fresh_output_stores','output_word_reads','vstart_reads')] ==
            [1134,366,1233792,145152,154224,154224,2268], 'Whole original reference scope')
    for receipt in (outcome['result']['actual_spike'],outcome['result']['actual_audit'],outcome['outer']):
        require(type(receipt['returncode']) is int and receipt['returncode']==0 and receipt['timeout'] is False
                and receipt['attempts']==1, 'Actual reference/audit/outer numeric exits')
    require(0 < outcome['cost']['slow_20percent_plus300_s'] <= CASE_BOUND, 'Measured proxy fits unchanged case budget')
    for n in ('RESULT.json','OUTCOME.json'):pins[str(REF/n)]=sha(REF/n)
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
    authority=checker.G/'arithmetic_restart_original/full_e8_mf4_o2_vcs_m9_successor02/reset_profile.json'
    pins[str(authority)]=sha(authority)
    checker.Strict(checker.specification(SHAPES[0]))
    ledger, repo, _ = common.image_context(image)
    require(Path(ledger['snapshot']).parent.name == 'current_board_memory_candidate09', 'M9 snapshot required')
    host = read(HERE / 'host02.json')
    require(host['status'] == 'PASS_HOST_ONLY' and host['failures'] == 0 and host['full_positive_shapes'] == list(SHAPES),
            'Full whole1134 Host oracle and real ABI entry required')
    require(host['actual_abi_entry_checked'] is True and host['tests'] >= 10, 'Actual whole1134 ABI Host missing')
    host_exit = read(HERE/'host02_process_exit.json')
    require(type(host_exit['returncode']) is int and host_exit['returncode'] == 0 and
            host_exit['timed_out'] is False, 'Actual Host process failed')
    common.base.verify_pins(host['pins'])
    pins.update(host['pins'])
    worker_host=read(HERE/'host_worker02.json')
    require(worker_host['status']=='PASS_HOST_ONLY' and worker_host['failures']==0 and worker_host['tests']==5,
            'Actual lifecycle signal/numeric Host')
    common.base.verify_pins(worker_host['pins']);pins.update(worker_host['pins'])
    pins.update(common.image_pins(image, ledger, repo))
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).is_file() and Path(path).resolve().is_relative_to(checker.G.parents[2]):
            pins[str(Path(path).resolve())] = sha(path)
    for n in ('checker.py', 'stream.py', 'helper_semantics.py', 'replay.py', 'test_host.py', 'reset_profile.json',
              'host02.json', 'host02.log', 'host02_process_exit.json', 'host_worker02.json', 'host_records.py', 'run_host.py', 'exit_hook.py', 'collect.py',
              'launch_once.py', 'README.md', 'USER_AUTHORIZATION.md'):
        pins[str(HERE / n)] = sha(HERE / n)
    plan = dict(status='PREPARED_NOT_RUN', image=str(image), image_sha256=sha(image / 'image.json'),
                snapshot_sha256=ledger['snapshot_sha256'], cases=scope(), specs={s: checker.specification(s) for s in SHAPES},
                pins=pins, jobs=JOBS, case_timeout_s=CASE_BOUND, worker_timeout_s=WORKER_BOUND,
                service_timeout_s=OUTER, unit=UNIT, reserved_slots=reserved, no_build=True, no_retry=True,
                no_fsdb=True, stop_first_fail=True, reference_ready_sha256=READY_SHA,
                user_conditional_authorization=True, resources_checked_only_at_run=True,
                scope='original continuous1134 calls and366 exclusions, all1088 bytes/call; not Linux or partitions',
                cost=dict(budget_gate='FIT_PROJECTION_ONLY',
                          conservative_projection_s=read(REF/'OUTCOME.json')['cost']['slow_20percent_plus300_s']))
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
            'Review must bind this exact full1134 M9 plan and all pins')
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
    abort = TerminalAbort()
    deadline = time.monotonic() + WORKER_BOUND
    timer = threading.Timer(WORKER_BOUND, abort.set)
    timer.daemon = True
    import ara_verify.runner as engine
    old_monitor, old_fail, old_trace = engine._run_monitored, engine.FAIL_RE, engine.validate_trace
    expected_trace=out/'replay/tests/whole_continuous_packed1134/commit_trace.csv'
    trace_invocations=[]
    def combined_trace(path):
        require(Path(path).resolve()==expected_trace.resolve() and not trace_invocations,
                'Exactly one full CSV validation invocation')
        raw=read(expected_trace.parent/'child_outcome.unvalidated.json')
        require(type(raw['returncode']) is int and raw['returncode']==0 and raw['timed_out'] is False and
                raw['failure_seen'] is False and raw['cancelled'] is False, 'Numeric child success before trace validation')
        trace_invocations.append(str(path))
        return checker.stream_validate(Path(path),abort)
    engine.validate_trace=combined_trace
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
                require((result.artifact_dir/'strict_original.json').is_file() and
                        report==read(result.artifact_dir/'strict_original.json'),
                        'Single-pass durable strict report disagreement')
                require(trace_invocations==[str(expected_trace)],'One and only complete CSV parse')
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
            engine._run_monitored, engine.FAIL_RE, engine.validate_trace = old_monitor, old_fail, old_trace
            terminal['finished'] = time.time()
            publish(out, terminal, abort, deadline)
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
