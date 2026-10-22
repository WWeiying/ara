#!/usr/bin/env python3
"""Prepare or explicitly run one original single on frozen M6; never build."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

sys.dont_write_bytecode = True
import checker
from checker import HERE, REF, NAME, require, read, sha, common

IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image')
TIMEOUT, OUTER = 5400, 6600
UNIT = 'ara-redspecial-e16-mf4-original-m6-01.service'
PASS = 'PASS_M6_ORIGINAL_E16_MF4_SINGLE144_NOT_FULL_PARENT'
READY_SHA = 'f858249f61dc7b9c4e3507f78bb483543d0439ef74942e838fc1251931a661de'
PROOF_SHA = 'f6efe2b2b360e96d4caa69fef05764bf205040f6c7347033e01cbd19562185af'
REVIEW = HERE.parent / 'original_e16_mf4_reference_audit01/REVIEW.md'
REVIEW_SHA = 'd9ad719158b37c9a1c1788b1e44fab5f84f06bc0d50a601128d8322cee91dc4c'
AUDIT_SHA = 'a0cfeb4214f5569092f6acf9cfd4c9539e275b5699e319aa2e36e0d567ba8678'


def accepted_reference():
    require(sha(REF / 'READY.json') == READY_SHA and sha(REF / 'sourceproof.json') == PROOF_SHA,
            'Canonical source/reference drift')
    require(sha(REVIEW) == REVIEW_SHA and sha(REVIEW.with_name('result.json')) == AUDIT_SHA,
            'Independent review drift')
    audit = read(REVIEW.with_name('result.json'))
    require(audit['status'] == 'INDEPENDENT_RAW_SOURCE_REFERENCE_ACCEPTED_SINGLE_ONLY' and
            audit['ready_sha256'] == READY_SHA and audit['firmware_to_HTIF'] == 1858335 and
            audit['helper_instructions'] == 21 and audit['oracle_bytes'] == 144 and
            audit['actual_ISA'] == 'rv64gcv_zfh_zvfh_zvl1024b' and audit['profiles_exact_equal'] is False,
            'No actual independent single-reference acceptance')
    ready = read(REF / 'READY.json')
    common.base.verify_pins(ready['pins'])
    return ready


def scope():
    require(sha(REF / 'soc/program.elf') == checker.ELF_SHA, 'ELF drift')
    return dict(id=NAME, original_name=NAME, elf=str(REF / 'soc/program.elf'),
                sha256=checker.ELF_SHA, timeout_s=TIMEOUT,
                pass_markers=[checker.MARKER, 'BOARD_CASE_PASS ' + NAME, 'BOARD_REPLAY_PASS'])


def validate(plan, image):
    require(image == IMAGE and plan['status'] == 'PREPARED_NOT_RUN' and plan['image'] == str(image) and
            plan['image_sha256'] == sha(image / 'image.json'), 'Image/plan drift')
    require(plan['case'] == scope() and plan['jobs'] == 1 and plan['timeout_s'] == TIMEOUT and
            plan['service_timeout_s'] == OUTER and plan['unit'] == UNIT and
            all(plan[k] is True for k in ('no_build', 'no_retry', 'no_fsdb', 'stop_first_fail')),
            'Scope/budget/ownership drift')
    require(plan['reference_ready_sha256'] == READY_SHA and plan['source_review_sha256'] == REVIEW_SHA,
            'Reference scope drift')
    require(plan['pins'].get(str(Path(__file__).resolve())) == sha(Path(__file__)), 'Worker drift')
    require(type(plan['reserved_slots']) is int and 0 <= plan['reserved_slots'] <= 24, 'Bad unused reservation')
    common.base.verify_pins(plan['pins'])
    require(plan['spec'] == checker.specification(), 'ELF-derived specification drift')


def terminal_plan_gate(out, digest, image):
    require(sha(out / 'plan.json') == digest, 'Late disk plan drift')
    validate(read(out / 'plan.json'), image)


def prepare(image, out, reserved):
    require(image == IMAGE and not out.exists(), 'Fresh owned plan and actual M6 required')
    ready = accepted_reference()
    ledger, repo, _ = common.image_context(image)
    require(Path(ledger['snapshot']).parent.name == 'current_board_memory_candidate06', 'Wrong M6 snapshot')
    host = read(HERE / 'host03.json')
    require(host['status'] == 'PASS_HOST_ONLY' and host['failures'] == host['errors'] == 0 and
            host['tests'] >= 20 and host['script_sha256'] == sha(HERE / 'test_host.py') and
            host['checker_sha256'] == sha(HERE / 'checker.py') and host['runner_sha256'] == sha(HERE / 'replay.py'),
            'Current Host tests required')
    require(type(reserved) is int and 0 <= reserved <= 24, 'Unused reservation bounds')
    pins = {**ready['pins'], **common.image_pins(image, ledger, repo)}
    for module in list(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename and Path(filename).is_file() and Path(filename).resolve().is_relative_to(HERE.parents[4]):
            pins[str(Path(filename).resolve())] = sha(Path(filename))
    for p in [REF / 'READY.json', REF / 'sourceproof.json', REVIEW, REVIEW.with_name('result.json'),
              REVIEW.with_name('audit_raw.py'), checker.OBJDUMP, *[HERE / n for n in
              ('checker.py', 'replay.py', 'test_host.py', 'README.md', 'host01.json', 'host01.log',
               'host02.json', 'host02.log', 'host03.json', 'host03.log')]]:
        pins[str(p)] = sha(p)
    plan = dict(status='PREPARED_NOT_RUN', image=str(image), image_sha256=sha(image / 'image.json'),
        snapshot_sha256=ledger['snapshot_sha256'], case=scope(), spec=checker.specification(),
        pins=pins, jobs=1, timeout_s=TIMEOUT, service_timeout_s=OUTER, unit=UNIT,
        reserved_slots=reserved, no_build=True, no_retry=True, no_fsdb=True, stop_first_fail=True,
        reference_ready_sha256=READY_SHA, source_review_sha256=REVIEW_SHA,
        resource_snapshot=None, resources_checked_only_at_authorized_run=True,
        budget=dict(reference_firmware=1858335, scalar_mask_instructions=1612800,
                    parent_planning_estimate_s=2820, implied_retired_per_second=1858335/2820,
                    conservative273_retired_per_second_s=1858335/273,
                    estimated_completion_not_guaranteed=True, no_automatic_timeout_change=True),
        scope='one authentic reduced single; not full6720 or all11; actual ISA delta accepted reference-only',
        launch_requires='new pinned parent authorization and direct service/resource admission')
    validate(plan, image)
    out.mkdir(exist_ok=False)
    common.save(out / 'plan.json', plan)
    digest = sha(out / 'plan.json')
    import shlex
    worker = [sys.executable, '-B', str(HERE / 'replay.py'), 'run', '--image', str(image), '--out', str(out),
              '--plan-sha256', digest, '--authorize-run', '--parent-review', 'PARENT_REVIEW_JSON',
              '--parent-review-sha256', 'PARENT_REVIEW_SHA']
    command = ['systemd-run', '--user', '--unit=' + UNIT, '--property=RuntimeMaxSec=' + str(OUTER),
               '--property=KillMode=control-group', '--property=Restart=no', '--property=WorkingDirectory=' + str(HERE),
               '--property=StandardOutput=append:' + str(out / 'service.log'),
               '--property=StandardError=append:' + str(out / 'service.log'), *worker]
    common.save(out / 'ready.json', dict(status='PREPARED_NOT_LAUNCHED', plan_sha256=digest,
                command=worker, service_command=shlex.join(command), pins=len(pins), VCS_started=False))
    print('PREPARED_NOT_LAUNCHED', digest, flush=True)


def owner_gate(properties, cgroup, pid):
    require(set(properties) == {'Id', 'LoadState', 'ActiveState', 'SubState', 'MainPID', 'ControlGroup',
                               'RuntimeMaxUSec', 'KillMode', 'Restart'} and
            properties['Id'] == UNIT and properties['LoadState'] == 'loaded' and
            properties['ActiveState'] == 'active' and properties['SubState'] == 'running' and
            properties['MainPID'] == str(pid) and properties['ControlGroup'].endswith('/' + UNIT) and
            properties['ControlGroup'] in [line.split(':', 2)[-1] for line in cgroup.splitlines()] and
            properties['RuntimeMaxUSec'] == '1h 50min' and properties['KillMode'] == 'control-group' and
            properties['Restart'] == 'no', 'Wrong direct service owner/bound')


def service_identity():
    runtime = Path('/run/user') / str(os.getuid())
    require(runtime.is_dir() and runtime.stat().st_uid == os.getuid() and (runtime / 'bus').is_socket(),
            'Trusted user bus unavailable')
    env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime), DBUS_SESSION_BUS_ADDRESS='unix:path=' + str(runtime / 'bus'))
    fields = 'Id,LoadState,ActiveState,SubState,MainPID,ControlGroup,RuntimeMaxUSec,KillMode,Restart'
    query = subprocess.run(['systemctl', '--user', 'show', UNIT, '--property=' + fields],
                           env=env, text=True, capture_output=True, timeout=10)
    require(query.returncode == 0 and not query.stderr.strip(), 'Service query failed')
    props = dict(line.split('=', 1) for line in query.stdout.splitlines())
    group = Path('/proc/self/cgroup').read_text()
    owner_gate(props, group, os.getpid())
    return dict(properties=props, cgroup=group, pid=os.getpid())


def checked_runner(parent, abort, check):
    class Runner(parent):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.cancel_event = abort

        def _run_test(self, test, image):
            try:
                result = super()._run_test(test, image)
                if result.status == 'PASS':
                    check(result)
                    if abort.is_set():
                        result.status, result.reason = 'CANCELLED', 'Abort during strict validation'
                if result.status != 'PASS':
                    abort.set()
                return result
            except BaseException:
                abort.set()
                raise
    return Runner


def terminal_gate(results, metadata, abort, ledger):
    common.check_stage(results, metadata, [dict(id=NAME)], abort)
    require(metadata['tests'] == [NAME] and metadata['completed_at'] and metadata['jobs'] == 1 and
            metadata['timeout_s'] == TIMEOUT and metadata['simv'] == ledger['simv'] and
            metadata['commit_trace'] is True and metadata['code_coverage'] is False, 'Wrong COMPLETE contract')


def authorization_gate(digest, path, review_sha):
    require(path and review_sha and sha(path) == review_sha, 'Pinned parent run review required')
    review = read(path)
    require(review['decision'] == 'AUTHORIZE_ORIGINAL_E16_MF4_M6_ONCE' and review['plan_sha256'] == digest and
            review['unit'] == UNIT and review['reference_review_sha256'] == REVIEW_SHA and
            review['budget_risk_accepted'] is True, 'Parent review scope/budget mismatch')
    return {str(path): review_sha}


def run(image, out, digest, authorized, review_path, review_sha):
    require(authorized and digest and sha(out / 'plan.json') == digest, 'Explicit parent authorization/plan SHA required')
    plan = read(out / 'plan.json')
    validate(plan, image)
    approval_pins = authorization_gate(digest, review_path, review_sha)
    ledger, repo, (parent, options, testcase, _) = common.image_context(image)
    require(ledger['snapshot_sha256'] == plan['snapshot_sha256'], 'Snapshot drift')
    owner = service_identity()
    admission = common.resources(out, 1, plan['reserved_slots'])
    with (out / 'launch.json').open('x') as stream:
        json.dump(dict(owner=owner, admission=admission, started=time.time(), plan_sha256=digest), stream, indent=2)
    abort = threading.Event()
    terminal = dict(status='NOT_PASS', plan_sha256=digest, results=[], retries=0, pins_unchanged=False)
    import ara_verify.runner as engine
    from ara_verify.trace import validate_trace
    old_fail = engine.FAIL_RE
    engine.FAIL_RE = re.compile(old_fail.pattern + '|' + checker.VETO.pattern, re.I)
    with common.abort_signals(abort):
        try:
            require(not (out / 'replay').exists(), 'No retry/overwrite')
            case = plan['case']
            def check(result):
                common.save(result.artifact_dir / 'strict_original.json',
                            checker.artifacts(result, case, ledger, plan['spec'], validate_trace))
            opts = options(repo, out / 'replay', 'default', 1, 1, False, False, True,
                           Path(ledger['simv']), True, TIMEOUT)
            tests = [testcase(NAME, 'app', '', Path(case['elf']), NAME, TIMEOUT)]
            results = checked_runner(parent, abort, check)(opts, tests, sys.argv).run()
            terminal['results'] = [dict(asdict(r), artifact_dir=str(r.artifact_dir)) for r in results]
            terminal_gate(results, read(out / 'replay/run.json'), abort, ledger)
            require(read(out / 'replay/summary.json') == terminal['results'], 'Summary mismatch')
            terminal_plan_gate(out, digest, image)
            common.image_context(image)
            common.base.verify_pins(approval_pins)
            evidence = {str(p): sha(p) for p in (out / 'launch.json', out / 'replay/run.json', out / 'replay/summary.json')}
            root = out / 'replay/tests' / NAME
            for name in ('input.elf', 'inputs.json', 'command.json', 'console.log', 'work/run.vcs.log',
                         'commit_trace.csv', 'trace_summary.json', 'strict_original.json'):
                evidence[str(root / name)] = sha(root / name)
            terminal.update(status=PASS, evidence_pins=evidence, pins_unchanged=True,
                            full_parent_accepted=False, all11_accepted=False)
        except BaseException as error:
            abort.set()
            terminal.update(status='NOT_PASS', error=f'{type(error).__name__}: {error}')
        finally:
            engine.FAIL_RE = old_fail
            terminal['finished'] = time.time()
            common.publish(out, terminal, abort)
    print(terminal['status'], flush=True)
    return int(terminal['status'] != PASS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'run'])
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--reserved-slots', type=int, default=0)
    parser.add_argument('--authorize-prepare', action='store_true')
    parser.add_argument('--authorize-run', action='store_true')
    parser.add_argument('--plan-sha256')
    parser.add_argument('--parent-review', type=Path)
    parser.add_argument('--parent-review-sha256')
    args = parser.parse_args()
    image, out = args.image.resolve(), args.out.resolve()
    require(out.parent == HERE, 'Owned direct fresh child only')
    env = common.base.shared.environment()
    os.environ.clear()
    os.environ.update(env)
    if args.mode == 'prepare':
        require(args.authorize_prepare, 'Explicit prepare gate required')
        prepare(image, out, args.reserved_slots)
        return 0
    return run(image, out, args.plan_sha256, args.authorize_run,
               args.parent_review.resolve() if args.parent_review else None, args.parent_review_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
