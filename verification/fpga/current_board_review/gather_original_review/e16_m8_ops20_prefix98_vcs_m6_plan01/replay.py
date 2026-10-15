#!/usr/bin/env python3
"""Prepare or explicitly authorize one fixed9000s M6 prefix; never build/retry."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time

sys.dont_write_bytecode = True
import checker
from checker import HERE, REF, NAME, require, read, sha, common

TIMEOUT, OUTER = 9000, 10200
UNIT = 'ara-gather-e16m8-ei16-prefix98-m6-01.service'
PASS = 'PASS_M6_ORIGINAL_E16M8_EI16_PREFIX98_NOT_FULL_CHILD'
READY_SHA = '1fde3acbc776a3ce8b5ea40d20bfb4e46827758cacfacf5e0333c3d6d4526149'
REVIEW = HERE.parent/'e16_m8_ops20_prefix98_audit01/REVIEW.md'
REVIEW_SHA = 'c1cc53ccf3848c8af2bb6004ea02517f00eb358eaebb6e6a6da49e5d27dbeb67'
AUDIT_SHA = '5fd1d2e3add1f801d1d8f3ad9cd708848b41f445080ff63629231cc49897ae79'
LAUNCH_REQUIREMENTS = ['accepted_ei16_source_reference', 'new_parent_review', 'runtime_resource_admission']


def scope():
    proof = read(REF/'source_elf_proof.json')
    elf = proof['soc_elf']
    require(sha(Path(elf['path'])) == elf['sha256'], 'Reference SoC ELF drift')
    entry = read(REF/'soc01/programs.json')['programs'][NAME]
    require(entry == elf, 'Original ELF manifest differs')
    return dict(id=NAME, original_name=NAME, elf=elf['path'], sha256=elf['sha256'],
                timeout_s=TIMEOUT, pass_markers=elf['pass_markers']), checker.specification(Path(elf['path']))


def validate(data, image):
    require(data['status'] == 'PREPARED_NOT_RUN' and data['image'] == str(image) and
            data['image_sha256'] == sha(image/'image.json'), 'Wrong image/plan')
    case, spec = scope()
    require(data['case'] == case and data['spec'] == spec and data['jobs'] == 1 and
            data['timeout_s'] == TIMEOUT and data['service_timeout_s'] == OUTER and data['unit'] == UNIT and
            data['no_build'] and data['no_retry'] and data['no_fsdb'] and
            data['launch_requirements'] == LAUNCH_REQUIREMENTS and
            data['reference_ready_sha256'] == READY_SHA, 'Scope/budget/service drift')
    require(data['pins'].get(str(Path(__file__).resolve())) == sha(Path(__file__)), 'Worker drift')
    common.base.verify_pins(data['pins'])


def prepare(image, out, reserved):
    require(not out.exists(), 'Fresh plan only')
    require(sha(REF/'READY.json') == READY_SHA and sha(REVIEW) == REVIEW_SHA, 'Accepted reference/review drift')
    independent = REVIEW.with_name('audit.json')
    require(sha(independent) == AUDIT_SHA, 'Independent audit drift')
    accepted = read(independent)
    require(accepted['status'] == 'ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT' and
            accepted['ready_sha256'] == READY_SHA and accepted['retired'] == 2134409 and
            accepted['helper_counts'] == [98]*13, 'Independent source/reference not accepted')
    ready = read(REF/'READY.json')
    require(ready['status'] == 'READY_HOST_SPIKE_AUTHENTIC98_E16M8_OP20_NOT_DUT' and
            (ready['calls'], ready['capacity'], ready['fullcap_results'], ready['guards']) ==
            (98, 512, 50176, 196), 'Wrong accepted reference scope')
    common.base.verify_pins(ready['evidence_pins'])
    audit_path = REF/'audit01/audit.json'
    audit = read(audit_path)
    require(audit['status'] == 'PASS_ONE_AUTHENTIC98_E16M8_OP20_PREFIX_RAW_REFERENCE_NOT_DUT' and
            audit['reference']['firmware_retired_to_htif_store'] == 2134409 and
            audit['exact_calls'] == 98 and len(audit['raw_trace_negative_results']) == 5,
            'Raw reference not accepted')
    ledger, repo, _ = common.image_context(image)
    require(Path(ledger['snapshot']).parent.name == 'current_board_memory_candidate06', 'M6 image required')
    case, spec = scope()
    pins = {**read(REF/'baseline_pins.json'), **ready['evidence_pins'], **common.image_pins(image, ledger, repo)}
    # Bind transitively imported live helpers as well as frozen runner/source files.
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).is_file() and Path(path).resolve().is_relative_to(HERE.parents[5]):
            pins[str(Path(path).resolve())] = sha(Path(path))
    for p in (audit_path, HERE/'checker.py', HERE/'replay.py', HERE/'test_host.py', HERE/'README.md',
              HERE/'host01.json', REF/'READY.json', REVIEW, independent, REVIEW.with_name('audit.py'), checker.source.OBJDUMP,
              HERE.parent/'stall_prefix2_launch02/checker.py',
              HERE.parent/'gather_repair05/m5_successor01/prefix_terminal_audit01/audit.py'):
        pins[str(p)] = sha(p)
    host = read(HERE/'host01.json')
    require(host['status'] == 'PASS_HOST_ONLY' and host['failures'] == host['errors'] == 0 and
            host['tests'] == 32 and host['script_sha256'] == sha(HERE/'test_host.py'),
            'Host negatives not PASS')
    require(type(reserved) is int and 0 <= reserved <= 24, 'Invalid unused reservation')
    for folder in ('e16_m8_ops1_prefix98_vcs_m6_plan02', 'e8_m8_ops1_prefix66_vcs_m6_plan01'):
        for p in (HERE.parent/folder).iterdir():
            if p.is_file():
                pins[str(p)] = sha(p)
    common.base.verify_pins(pins)
    out.mkdir()
    common.save(out/'plan.json', dict(status='PREPARED_NOT_RUN', image=str(image),
        image_sha256=sha(image/'image.json'), snapshot_sha256=ledger['snapshot_sha256'],
        case=case, spec=spec, pins=pins, jobs=1, timeout_s=TIMEOUT, service_timeout_s=OUTER,
        unit=UNIT, reserved_slots=reserved, no_build=True, no_retry=True, no_fsdb=True,
        budget=dict(reference_retired=2134409, conservative_retired_per_second=273,
                    estimated_s=2134409/273, plus20percent_s=2134409/273*1.2,
                    nominal_exceeds_case_budget=False, margin_exceeds_three_hours=False,
                    margin_exceeds_case_budget=True,
                    estimated_guaranteed_to_pass=False, test_bound_s=TIMEOUT, outer_bound_s=OUTER),
        resource_snapshot=None, resource_check_deferred_to_authorized_run=True,
        reference_ready_sha256=READY_SHA, launch_requirements=LAUNCH_REQUIREMENTS,
        exact_historical_stopped_tuple=None, full_child_acceptance=False))
    digest = sha(out/'plan.json')
    command = [sys.executable, str(Path(__file__).resolve()), 'run', '--image', str(image), '--out', str(out),
               '--plan-sha256', digest, '--authorize-run',
               '--parent-review', 'PARENT_REVIEW_JSON', '--parent-review-sha256', 'PARENT_REVIEW_SHA256']
    import shlex
    unit_command = ['systemd-run', '--user', '--unit='+UNIT, '--property=RuntimeMaxSec='+str(OUTER),
        '--property=KillMode=control-group', '--property=Restart=no', '--property=WorkingDirectory='+str(HERE),
        '--property=StandardOutput=append:'+str(out/'service.log'),
        '--property=StandardError=append:'+str(out/'service.log'), *command]
    common.save(out/'ready.json', dict(status='PREPARED_NO_DUT_AWAIT_PARENT', plan_sha256=digest,
        command=command, service_command=shlex.join(unit_command), pins=len(pins), vcs_started=False))
    print('PREPARED_NO_DUT_AWAIT_PARENT', digest, flush=True)


def service_identity(unit):
    # Runtime environment sanitizer omits the user bus; supply its trusted UID path explicitly.
    runtime = Path('/run/user')/str(os.getuid())
    require(runtime.is_dir() and runtime.stat().st_uid == os.getuid() and (runtime/'bus').is_socket(),
            'Trusted user bus unavailable')
    env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime), DBUS_SESSION_BUS_ADDRESS='unix:path='+str(runtime/'bus'))
    names = ('Id', 'LoadState', 'ActiveState', 'SubState', 'MainPID', 'ControlGroup',
             'RuntimeMaxUSec', 'KillMode', 'Restart')
    query = subprocess.run(['systemctl', '--user', 'show', unit, '--property='+','.join(names)],
                           env=env, text=True, capture_output=True, timeout=10)
    require(query.returncode == 0 and not query.stderr.strip(), 'Service query error: '+query.stderr)
    props = dict(line.split('=', 1) for line in query.stdout.splitlines())
    cgroup = Path('/proc/self/cgroup').read_text()
    require(set(props) == set(names) and props['Id'] == unit and props['LoadState'] == 'loaded' and
            props['ActiveState'] == 'active' and props['SubState'] == 'running' and
            props['MainPID'] == str(os.getpid()) and props['ControlGroup'] and
            any(line.split(':', 2)[-1] == props['ControlGroup'] for line in cgroup.splitlines()) and
            props['ControlGroup'].endswith('/'+unit) and props['RuntimeMaxUSec'] == '2h 50min' and
            props['KillMode'] == 'control-group' and props['Restart'] == 'no', 'Wrong direct service owner/bound')
    return dict(properties=props, cgroup=cgroup, pid=os.getpid(), query_stdout=query.stdout)


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


def authorization_gate(plan, digest, review_path, review_digest):
    require(review_path is not None and review_digest and sha(review_path) == review_digest,
            'New pinned parent review required')
    review = read(review_path)
    require(review['decision'] == 'AUTHORIZE_E16_EI16_PREFIX98_ONCE' and
            review['plan_sha256'] == digest and review['unit'] == UNIT and
            review['budget_risk_accepted'] is True and
            review['reference_ready_sha256'] == READY_SHA and
            review['source_review_sha256'] == REVIEW_SHA,
            'Parent review scope/reference/budget acceptance')
    bound = {str(review_path): review_digest, str(REF/'READY.json'): READY_SHA,
             str(REVIEW): REVIEW_SHA}
    common.base.verify_pins(bound)
    return bound


def run(image, out, digest, authorized, review_path, review_digest):
    require(authorized and digest and sha(out/'plan.json') == digest, 'Explicit parent plan-SHA authorization required')
    plan = read(out/'plan.json')
    validate(plan, image)
    approval_pins = authorization_gate(plan, digest, review_path, review_digest)
    ledger, repo, (parent, options, testcase, _) = common.image_context(image)
    owner = service_identity(plan['unit'])
    admission = common.resources(out, 1, plan['reserved_slots'])
    with (out/'launch.json').open('x') as stream:
        json.dump(dict(owner=owner, admission=admission, plan_sha256=digest,
                       approval_pins=approval_pins, started=time.time()), stream, indent=2)
    abort = threading.Event()
    terminal = dict(status='NOT_PASS', plan_sha256=digest, retries=0, results=[], pins_unchanged=False)
    import ara_verify.runner as engine
    from ara_verify.trace import validate_trace
    original_fail = engine.FAIL_RE
    engine.FAIL_RE = re.compile(original_fail.pattern+'|'+checker.VETO.pattern, re.I)
    with common.abort_signals(abort):
        try:
            require(not (out/'replay').exists(), 'No retries/overwrite')
            case = plan['case']
            def check(result):
                report = checker.artifacts(result, case, ledger, plan['spec'], validate_trace)
                common.save(result.artifact_dir/'strict_prefix.json', report)
            opts = options(repo, out/'replay', 'default', 1, 1, False, False, True,
                           Path(ledger['simv']), True, TIMEOUT)
            tests = [testcase(NAME, 'app', '', Path(case['elf']), NAME, TIMEOUT)]
            results = checked_runner(parent, abort, check)(opts, tests, sys.argv).run()
            terminal['results'] = [dict(asdict(r), artifact_dir=str(r.artifact_dir)) for r in results]
            terminal_gate(results, read(out/'replay/run.json'), abort, ledger)
            require(read(out/'replay/summary.json') == terminal['results'], 'Summary differs')
            validate(plan, image)
            common.image_context(image)
            common.base.verify_pins(approval_pins)
            evidence = {str(p): sha(p) for p in (out/'launch.json', out/'replay/run.json', out/'replay/summary.json')}
            root = out/'replay/tests'/NAME
            for name in ('input.elf', 'inputs.json', 'command.json', 'console.log', 'work/run.vcs.log',
                         'commit_trace.csv', 'trace_summary.json', 'strict_prefix.json'):
                evidence[str(root/name)] = sha(root/name)
            terminal.update(status=PASS, pins_unchanged=True, evidence_pins=evidence,
                            exact_historical_stopped_tuple=None, full_child_acceptance=False)
        except BaseException as error:
            abort.set()
            terminal.update(status='NOT_PASS', error=f'{type(error).__name__}: {error}')
        finally:
            engine.FAIL_RE = original_fail
            terminal['finished'] = time.time()
            common.publish(out, terminal, abort)
    print(terminal['status'], flush=True)
    return int(terminal['status'] != PASS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'run'))
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--reserved-slots', type=int, default=0, help='Unused external reservation only; live counted once')
    parser.add_argument('--authorize-prepare', action='store_true')
    parser.add_argument('--authorize-run', action='store_true')
    parser.add_argument('--plan-sha256')
    parser.add_argument('--parent-review', type=Path)
    parser.add_argument('--parent-review-sha256')
    args = parser.parse_args()
    image, out = args.image.resolve(), args.out.resolve()
    require(out.parent == HERE, 'Fresh direct owned child only')
    env = common.base.shared.environment()
    os.environ.clear()
    os.environ.update(env)
    if args.mode == 'prepare':
        require(args.authorize_prepare, 'Explicit prepare required; no DUT')
        prepare(image, out, args.reserved_slots)
        return 0
    return run(image, out, args.plan_sha256, args.authorize_run,
               args.parent_review.resolve() if args.parent_review else None, args.parent_review_sha256)


if __name__ == '__main__':
    raise SystemExit(main())


