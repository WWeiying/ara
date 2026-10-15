#!/usr/bin/env python3
"""One future frozen M6 worker. Code/Host preparation is not an accepted plan."""
import argparse
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
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
from checker import HERE, REF, common, read, require, sha
from newscope import *

LAUNCH_REQUIREMENTS = ['accepted_READY02_original_binary_proof', 'independent_reference_acceptance',
                       'new_parent_planSHA_authorization', 'direct_service_owner', 'runtime_resources']
HOST_REPORT = 'host03.json'


def merge_pins(*tables):
    pins = {}
    for table in tables:
        for path, digest in table.items():
            require(path not in pins or pins[path] == digest, 'Conflicting input pin: '+path)
            pins[path] = digest
    return pins


def audit_payload_gate(ready, audit, execution, started, reference):
    """The actual completed independent schema, not a synthesized acceptance."""
    require(audit['status'] == 'ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT' and
            audit['ready_sha256'] == READY02_SHA and audit['old_ready_sha256'] == OLD_READY_SHA and
            audit['full_original_binary_proof_sha256'] == ORIGINAL_PROOF_SHA and
            audit['pins_pre_post_unchanged'] is True and audit['raw_parses'] == 1 and
            audit['numeric_prefix66_only'] is True and audit['unknown_stall_reproduction'] is False and
            audit['full2688_execution'] is False and audit['DUT'] is False,
            'Actual independent source reference acceptance unresolved')
    require((audit['firmware_retired'], audit['full_results'], audit['guards'], audit['scalar_loads'],
             audit['physical_predicate_bytes'], audit['logical_predicate_bytes'], audit['endpoint'],
             audit['actual_source31'], audit['capacity_returns'], audit['full_vector_inputs_results_stores']) ==
            (REFERENCE_RETIRED, RESULT_CHECKS, GUARD_CHECKS, ORACLE_LOADS, PREDICATE_BYTES,
             LOGICAL_MASK_BYTES, ENDPOINT, 177, 1, BOUND) and audit['helper_counts'] == [BOUND]*13,
            'Independent full prefix counts/physical scope differ')
    require(len(audit['vlenb_reads']) == 2 and all(v['value'] == VLENB for v in audit['vlenb_reads']),
            'Independent actual vlenb reads differ')
    require(len(audit['calls']) == BOUND and ready['ordered_tuples'] == [c['tuple'] for c in audit['calls']],
            'Independent complete ordered calls differ')
    for n, (actual, expected) in enumerate(zip(audit['calls'], checker.model()['rows']), 1):
        require(actual['ordinal'] == n and actual['tuple'] == expected['tuple'] and
                actual['vl'] == expected['vl'] and actual['vstart'] == expected['vstart'] and
                actual['opcode'] == '0x308fbc57' and actual['actual_source31'] == 177 and
                actual['returned_vstart'] == 0, 'Independent call payload differs')
    require(reference['status'] == 'PASS_SPIKE_RAW66_SETUP_ASM_FULLORACLE_NOT_DUT' and
            reference['source_label'] == SOURCE_LABEL and reference['runtime_id'] == RUNTIME_ID and
            audit['raw_sha256'] == reference['commit_sha256'] and
            audit['raw_bytes'] == reference['commit_bytes'] == ready['actual_reference_raw_bytes'] and
            audit['input_pin_count'] == 105 and audit['boot_records'] == 5 and
            audit['post_exit_original_park_records'] == 1701 and audit['total_raw_records'] == 1355000,
            'Independent full-EOF/raw identity differs')
    require(type(execution['returncode']) is int and execution['returncode'] == 0 and
            execution['timed_out'] is False and execution['retries'] == 0 and
            type(execution['child_pid']) is int and execution['child_pid'] > 0 and
            0 < execution['elapsed_s'] <= 600 and execution['audit_pins_sha256'] == AUDITOR_PINS_SHA and
            execution['command'] == started['command'] and started['timeout_s'] == 600 and
            started['retries'] == 0, 'Actual independent execution rc/bound/provenance differs')


def durable(path, data):
    path = Path(path)
    with path.open('x') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def first_cause(root, cause):
    try:
        durable(Path(root) / 'first_cause.json', cause)
    except FileExistsError:
        pass


def persist_unvalidated(result):
    """Runner classification is secondary to the already persisted monitor tuple."""
    root = Path(result.artifact_dir)
    # The real runner already created its directory. Host fixtures do so too.
    path = root / 'runner_result.unvalidated.json'
    durable(path, dict(schema='UNVALIDATED_CHILD_OUTCOME_V2', architectural_acceptance=False,
                       name=result.name, status=result.status, returncode=result.returncode,
                       elapsed_s=result.elapsed_s, reason=result.reason, artifact_dir=str(root)))
    require(result.returncode is None or type(result.returncode) is int, 'Invalid runner classification exit')
    return path


def monitor_command(command, root, simv):
    return [str(simv), '-l', 'run.vcs.log', '+ntb_random_seed=1', '+PRELOAD='+str(root / 'input.elf'),
            '+TESTCASE='+RUNTIME_ID, '+NO_FSDB', '+COMMIT_TRACE='+str(root / 'commit_trace.csv')]


def monitored(original, abort, root, simv):
    """Persist the actual wait tuple before the frozen runner can read any log."""
    root = Path(root).resolve()
    def call(command, cwd, console, timeout, cancel_event=None):
        try:
            require(Path(cwd).resolve() == root / 'work' and Path(console).resolve() == root / 'console.log' and
                    timeout == TIMEOUT and [str(x) for x in command] == monitor_command(command, root, simv),
                    'Actual monitor runtime/private-CWD/command/bound drift')
            outcome = original(command, cwd, console, timeout, cancel_event)
            code, elapsed, timed_out, failure_seen = outcome
            # No command.json read, checker, or result object is needed for this first durable write.
            durable(root / 'child_outcome.unvalidated.json', dict(
                schema='UNVALIDATED_MONITOR_OUTCOME_V1', architectural_acceptance=False,
                name=RUNTIME_ID, source_label=SOURCE_LABEL, returncode=code, elapsed_s=elapsed,
                timed_out=timed_out, failure_seen=failure_seen, command=[str(x) for x in command],
                cwd=str(cwd), console_path=str(console), timeout_s=timeout))
            require(type(code) is int and type(timed_out) is bool and type(failure_seen) is bool,
                    'Actual monitor numeric tuple required')
            if code != 0 or timed_out or failure_seen:
                first_cause(root, dict(kind='MONITOR_OUTCOME', returncode=code, timed_out=timed_out,
                                      failure_seen=failure_seen, elapsed_s=elapsed))
            # The frozen parent classifies this completed child next. With jobs1,
            # the outer wrapper latches abort on that result or any generic exception.
            return outcome
        except BaseException:
            abort.set()
            raise
    return call


@contextmanager
def engine_hooks(engine, abort, root, simv):
    old_monitor, old_fail = engine._run_monitored, engine.FAIL_RE
    engine._run_monitored = monitored(old_monitor, abort, root, simv)
    engine.FAIL_RE = re.compile(old_fail.pattern+'|'+checker.VETO.pattern, re.I)
    try:
        yield
    finally:
        engine._run_monitored, engine.FAIL_RE = old_monitor, old_fail


def command_provenance(result):
    root = Path(result.artifact_dir)
    raw = (root / 'command.json').read_bytes()
    command = json.loads(raw)
    durable(root / 'child_command.provenance.json', dict(
        command_path=str(root / 'command.json'), command_sha256=hashlib.sha256(raw).hexdigest(), command=command))


def checked_runner(parent, abort, check, admission):
    class Runner(parent):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.cancel_event = abort

        def _run_test(self, test, image):
            result = None
            try:
                require(not abort.is_set(), 'Aborted before dispatch')
                admission(test.name)
                result = super()._run_test(test, image)
                persist_unvalidated(result)
                if result.status != 'PASS' or result.returncode != 0:
                    abort.set()
                    first_cause(result.artifact_dir, dict(kind='CHILD_OUTCOME', name=result.name,
                                status=result.status, returncode=result.returncode, reason=result.reason))
                # Metadata failures occur after the numeric child record and first failure latch.
                command_provenance(result)
                if result.status == 'PASS' and result.returncode == 0:
                    require(not abort.is_set(), 'Late abort before validation')
                    check(result)
                    if abort.is_set():
                        first_cause(result.artifact_dir, dict(kind='LATE_ABORT', returncode=result.returncode))
                        result.status, result.reason = 'CANCELLED', 'Abort during validation'
                return result
            except BaseException as error:
                abort.set()
                if result is not None:
                    root = Path(result.artifact_dir)
                else:
                    output = getattr(self, 'output_root', None)
                    root = Path(output) / 'tests' / RUNTIME_ID if output is not None else None
                if root is not None and root.is_dir():
                    child = root / 'child_outcome.unvalidated.json'
                    numeric = read(child)['returncode'] if child.is_file() else None
                    first_cause(root, dict(kind='POSTCHECK_EXCEPTION',
                                returncode=numeric,
                                runner_returncode=result.returncode if result is not None else None,
                                error=f'{type(error).__name__}: {error}'))
                raise
    return Runner


def accepted_reference(ready_path, ready_digest, audit_path, audit_digest):
    require(ready_path and ready_digest and audit_path and audit_digest,
            'Actual READY02 and independent accepted report/hash required; unresolved HOLD')
    ready_path, audit_path = Path(ready_path).resolve(), Path(audit_path).resolve()
    require(ready_path.parent == REF and ready_path.name == 'READY02.json' and
            ready_digest == READY02_SHA and sha(ready_path) == ready_digest,
            'Actual READY02 pin required; old READY refused')
    audit_root = HERE.parent / 'e8_m4_ops3_prefix66_reference_audit01'
    require(audit_path == audit_root / 'audit.json' and audit_digest == AUDIT_SHA and
            sha(audit_path) == audit_digest, 'Independent report pin drift')
    ready, audit = read(ready_path), read(audit_path)
    require(ready['status'] == 'ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT' and
            ready['entire_original_linux_binary_rebuild_proven'] is True,
            'Exact original Linux binary rebuild proof unresolved')
    proof_path = REF / 'original_linux_rebuild02/proof.json'
    require(sha(proof_path) == ORIGINAL_PROOF_SHA and ready['pins'].get(str(proof_path)) == ORIGINAL_PROOF_SHA,
            'Exact Buildroot14.3 proof pin required')
    proof = read(proof_path)
    require(proof['status'] == 'PASS_FULL_ORIGINAL_LINUX_ELF_BYTE_IDENTICAL' and
            proof['original_linux_elf_sha256'] == proof['rebuilt_linux_elf_sha256'] == ORIGINAL_ELF_SHA and
            proof['actual_numeric_returncode'] == 0 and proof['compile_attempts'] == 1,
            'Byte-identical original Linux ELF proof failed')
    require(ready['full_linux_rebuild_proof_sha256'] == ORIGINAL_PROOF_SHA,
            'READY02 exact supplemental proof linkage differs')
    evidence = {'audit.json': AUDIT_SHA, 'REVIEW.md': REVIEW_SHA,
                'execution.json': AUDIT_EXECUTION_SHA, 'auditor_pins.json': AUDITOR_PINS_SHA}
    for name, digest in evidence.items():
        require(sha(audit_root / name) == digest, 'Independent finished evidence drift: '+name)
    execution = read(audit_root / 'execution.json')
    started = read(audit_root / 'execution_started.json')
    reference_path = REF / 'reference/reference.json'
    require(sha(reference_path) == ready['reference_sha256'] == ready['pins'][str(reference_path)],
            'Pinned reference.json metadata identity differs')
    reference = read(reference_path)
    require(ready['pins'][str(REF / 'reference/commits.log')] == reference['commit_sha256'],
            'Pinned reference raw commit linkage differs')
    audit_payload_gate(ready, audit, execution, started, reference)
    require((ready['source_label'], ready['runtime_id'], ready['sew'], ready['lmul'], ready['vlenb'],
             ready['capacity'], ready['calls'], ready['physical_predicate_bytes'], ready['setup_values_per_call'],
             ready['setup_bytes_per_call'], ready['fullcap_results'], ready['guards'], ready['oracle_loads'],
             ready['helper_instruction_count'], ready['endpoint']) ==
            (SOURCE_LABEL, RUNTIME_ID, SEW, LMUL, VLENB, CAP, BOUND, PREDICATE_BYTES, SETUP_VALUES,
             SETUP_BYTES, RESULT_CHECKS, GUARD_CHECKS, ORACLE_LOADS, HELPER_INSTRUCTIONS, ENDPOINT),
            'Accepted reference physical scope differs')
    require(ready['soc_elf']['sha256'] == SOC_ELF_SHA and ready['actual_firmware_retired'] == REFERENCE_RETIRED,
            'Frozen reference ELF/count drift')
    verified = read(audit_root / 'verified_input_pins.json')
    auditor_pins = read(audit_root / 'auditor_pins.json')
    require(len(verified) == audit['input_pin_count'] and auditor_pins and
            auditor_pins[str(audit_root / 'audit.py')] == audit['auditor_sha256'] and
            auditor_pins[str(audit_root / 'model.py')] == audit['model_sha256'],
            'Actual independent transitive input/auditor pins differ')
    pins = merge_pins(read(REF / 'baseline_pins.json'), ready['pins'], proof['pins'], verified,
                      auditor_pins, {str(ready_path): ready_digest},
                      {str(audit_root / name): digest for name, digest in evidence.items()})
    for name in ('verified_input_pins.json', 'execution_started.json', 'invocation_started.json',
                 'parse_started.json', 'audit.stdout.log', 'audit.stderr.log'):
        pins[str(audit_root / name)] = sha(audit_root / name)
    common.base.verify_pins(pins)
    return ready, pins


def scope():
    proof = read(REF / 'source_elf_proof.json')
    elf = proof['soc_elf']
    require(elf == read(REF / 'soc01/programs.json')['programs'][RUNTIME_ID] and
            sha(Path(elf['path'])) == elf['sha256'] == SOC_ELF_SHA, 'SoC manifest/source identity drift')
    return dict(id=RUNTIME_ID, original_name=SOURCE_LABEL, elf=elf['path'], sha256=elf['sha256'],
                timeout_s=TIMEOUT, pass_markers=elf['pass_markers']), checker.specification(Path(elf['path']))


def validate(plan, image):
    require(image == Path(IMAGE) and plan['status'] == 'PREPARED_NOT_RUN' and plan['image'] == str(image) and
            plan['image_sha256'] == sha(image / 'image.json'), 'Exact frozen M6 image/plan required')
    case, spec = scope()
    require(plan['case'] == case and plan['spec'] == spec and plan['jobs'] == JOBS and
            plan['timeout_s'] == TIMEOUT and plan['service_timeout_s'] == OUTER and plan['unit'] == UNIT and
            plan['independent_review_sha256'] == REVIEW_SHA and
            plan['independent_execution_sha256'] == AUDIT_EXECUTION_SHA and
            plan['launch_requirements'] == LAUNCH_REQUIREMENTS and
            all(plan[k] is True for k in ('no_build', 'no_retry', 'no_fsdb', 'no_code_coverage', 'no_ucli')),
            'Exact case/budget/resource/run contract drift')
    _, pins = accepted_reference(plan['reference_ready'], plan['reference_ready_sha256'],
                                 plan['independent_audit'], plan['independent_audit_sha256'])
    require(all(plan['pins'].get(p) == d for p, d in pins.items()), 'Incomplete reference pins')
    require(plan['pins'].get(str(HERE / 'replay.py')) == sha(HERE / 'replay.py'), 'Worker pin drift')
    common.base.verify_pins(plan['pins'])


def terminal_plan_gate(out, digest, image):
    require(sha(out / 'plan.json') == digest, 'Fresh disk plan drift')
    validate(read(out / 'plan.json'), image)
    require(sha(out / 'plan.json') == digest, 'Plan drift during late validation')


def prepare(image, out, reserved, ready, ready_sha, audit, audit_sha):
    # No output directory or execution plan until both prerequisites actually pass.
    require(out.parent == HERE and not out.exists() and image == Path(IMAGE), 'Fresh owned plan / frozen M6 only')
    _, pins = accepted_reference(ready, ready_sha, audit, audit_sha)
    host = read(HERE / HOST_REPORT)
    require(host['status'] == 'PASS_HOST_ONLY_NOT_DUT' and host['failures'] == host['errors'] == 0,
            'Host negatives not accepted')
    common.base.verify_pins(host['pins'])
    ledger, repo, _ = common.image_context(image)
    require(Path(ledger['snapshot']).parent.name == 'current_board_memory_candidate06', 'M6 snapshot required')
    case, spec = scope()
    pins.update(common.image_pins(image, ledger, repo))
    pins.update(host['pins'])
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).is_file() and Path(path).resolve().is_relative_to(HERE.parents[5]):
            pins[str(Path(path).resolve())] = sha(Path(path))
    for name in ('newscope.py', 'checker.py', 'replay.py', 'test_host.py', 'README.md', HOST_REPORT):
        pins[str(HERE / name)] = sha(HERE / name)
    pins[str(checker.source.OBJDUMP)] = sha(checker.source.OBJDUMP)
    require(type(reserved) is int and 0 <= reserved <= 24, 'Invalid unused reservation')
    common.base.verify_pins(pins)
    plan = dict(status='PREPARED_NOT_RUN', image=str(image), image_sha256=sha(image / 'image.json'),
                snapshot_sha256=ledger['snapshot_sha256'], case=case, spec=spec, pins=pins,
                jobs=JOBS, timeout_s=TIMEOUT, service_timeout_s=OUTER, unit=UNIT, reserved_slots=reserved,
                no_build=True, no_retry=True, no_fsdb=True, no_code_coverage=True, no_ucli=True,
                reference_ready=str(ready.resolve()), reference_ready_sha256=ready_sha,
                independent_audit=str(audit.resolve()), independent_audit_sha256=audit_sha,
                independent_review_sha256=REVIEW_SHA, independent_execution_sha256=AUDIT_EXECUTION_SHA,
                launch_requirements=LAUNCH_REQUIREMENTS, full_child_acceptance=False,
                resource_snapshot=None, resources_checked_only_at_authorized_run=True,
                budget=dict(reference_retired=REFERENCE_RETIRED, proxy_retired_per_second=PROXY_RETIRED_PER_SECOND,
                            estimated_s=REFERENCE_RETIRED/PROXY_RETIRED_PER_SECOND, completion_guaranteed=False,
                            fixed_case_s=TIMEOUT, fixed_outer_s=OUTER, no_runtime_budget_increase=True),
                unvalidated_numeric_outcome_before_postcheck=True)
    validate(plan, image)
    out.mkdir()
    durable(out / 'plan.json', plan)
    digest = sha(out / 'plan.json')
    command = [sys.executable, '-B', str(HERE / 'replay.py'), 'run', '--image', str(image), '--out', str(out),
               '--authorize-run', '--plan-sha256', digest, '--parent-review', 'UNRESOLVED_PARENT_REVIEW_JSON',
               '--parent-review-sha256', 'UNRESOLVED_PARENT_REVIEW_SHA256']
    unit_command = ['systemd-run', '--user', '--unit='+UNIT, '--property=RuntimeMaxSec='+str(OUTER),
                    '--property=KillMode=control-group', '--property=Restart=no',
                    '--property=WorkingDirectory='+str(HERE),
                    '--property=StandardOutput=append:'+str(out / 'service.log'),
                    '--property=StandardError=append:'+str(out / 'service.log'), *command]
    durable(out / 'ready.json', dict(status='PREPARED_NOT_ADMITTED_NO_DUT', plan_sha256=digest,
                command=command, service_command=shlex.join(unit_command), parent_approval='UNRESOLVED', vcs_started=False))
    print('PREPARED_NOT_ADMITTED_NO_DUT', digest, flush=True)


def build_options(options, repo, out, ledger, dry=False):
    return options(repo_root=repo, output_root=out / ('dryrun' if dry else 'replay'), config='default',
                   jobs=JOBS, seed=1, dry_run=dry, build_only=False, skip_build=True,
                   simv=Path(ledger['simv']), commit_trace=True, timeout_s=TIMEOUT)


def dryrun(image, out, digest):
    terminal_plan_gate(out, digest, image)
    require(not (out / 'dryrun').exists(), 'Fresh dryrun only; no retry/overwrite')
    ledger, repo, (parent, options, testcase, _) = common.image_context(image)
    case = read(out / 'plan.json')['case']
    opts = build_options(options, repo, out, ledger, True)
    require(opts.dry_run and opts.skip_build and not opts.build_only and not opts.code_coverage,
            'Dryrun must neither compile nor execute')
    class NoBuildDryRunner(parent):
        def build(self):
            return Path(ledger['simv'])
    results = NoBuildDryRunner(opts, [testcase(RUNTIME_ID, 'app', '', Path(case['elf']), RUNTIME_ID, TIMEOUT)],
                               sys.argv).run()
    require(len(results) == 1 and results[0].name == RUNTIME_ID and results[0].status == 'DRY_RUN' and
            results[0].returncode is None, 'Exact one-case dryrun required')
    root = out / 'dryrun/tests' / RUNTIME_ID
    command = read(root / 'command.json')
    require(command == dict(command=[ledger['simv'], '-l', 'run.vcs.log', '+ntb_random_seed=1',
                         '+PRELOAD='+case['elf'], '+TESTCASE='+RUNTIME_ID, '+NO_FSDB',
                         '+COMMIT_TRACE='+str(root / 'commit_trace.csv')], cwd=str(root / 'work')),
            'Dryrun exact runtime command provenance differs')
    require(not any((root / n).exists() for n in ('console.log', 'commit_trace.csv', 'work/run.vcs.log')),
            'Dryrun unexpectedly produced DUT evidence')
    terminal_plan_gate(out, digest, image)
    durable(out / 'dryrun_gate.json', dict(status='DRYRUN_ONLY_NO_DUT', jobs=JOBS, cases=[RUNTIME_ID],
                plan_sha256=digest, parent_approval='UNRESOLVED', VCS_started=False, build_invoked=False,
                evidence_pins={str(p): sha(p) for p in (root / 'command.json', out / 'dryrun/run.json',
                                                       out / 'dryrun/summary.json')}))
    print('DRYRUN_ONLY_NO_DUT', digest, flush=True)


def owner_gate(props, cgroup, pid):
    fields = {'Id', 'LoadState', 'ActiveState', 'SubState', 'MainPID', 'ControlGroup', 'RuntimeMaxUSec', 'KillMode', 'Restart'}
    require(set(props) == fields and props['Id'] == UNIT and props['LoadState'] == 'loaded' and
            props['ActiveState'] == 'active' and props['SubState'] == 'running' and props['MainPID'] == str(pid) and
            props['ControlGroup'].endswith('/'+UNIT) and props['ControlGroup'] in
            [line.split(':', 2)[-1] for line in cgroup.splitlines()] and
            props['RuntimeMaxUSec'] == '1h 50min' and props['KillMode'] == 'control-group' and props['Restart'] == 'no',
            'Direct owning systemd worker / fixed outer bound required')


def service_identity():
    runtime = Path('/run/user') / str(os.getuid())
    require(runtime.is_dir() and runtime.stat().st_uid == os.getuid() and (runtime / 'bus').is_socket(), 'Trusted user bus required')
    env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime), DBUS_SESSION_BUS_ADDRESS='unix:path='+str(runtime / 'bus'))
    names = 'Id,LoadState,ActiveState,SubState,MainPID,ControlGroup,RuntimeMaxUSec,KillMode,Restart'
    query = subprocess.run(['systemctl', '--user', 'show', UNIT, '--property='+names],
                           env=env, text=True, capture_output=True, timeout=10)
    require(query.returncode == 0 and not query.stderr.strip(), 'Service query failed')
    props = dict(line.split('=', 1) for line in query.stdout.splitlines())
    cgroup = Path('/proc/self/cgroup').read_text()
    owner_gate(props, cgroup, os.getpid())
    return dict(properties=props, cgroup=cgroup, pid=os.getpid(), query_stdout=query.stdout)


def authorization_gate(plan, digest, path, path_sha):
    require(path and path_sha and sha(path) == path_sha, 'Actual new pinned parent authorization required')
    review = read(path)
    require(review['decision'] == 'AUTHORIZE_E8M4_VI31_PREFIX66_M6_ONCE' and review['plan_sha256'] == digest and
            review['unit'] == UNIT and review['budget_risk_accepted'] is True and
            review['reference_ready_sha256'] == plan['reference_ready_sha256'] and
            review['independent_audit_sha256'] == plan['independent_audit_sha256'], 'Parent scope/acceptance gate')
    return {str(path): path_sha}


def terminal_gate(results, metadata, abort, ledger):
    common.check_stage(results, metadata, [dict(id=RUNTIME_ID)], abort)
    require(metadata['tests'] == [RUNTIME_ID] and metadata['completed_at'] and metadata['jobs'] == JOBS and
            metadata['timeout_s'] == TIMEOUT and metadata['seed'] == 1 and metadata['simv'] == ledger['simv'] and
            metadata['commit_trace'] is True and metadata['code_coverage'] is False, 'Exact COMPLETE contract')
    require(len(results) == 1 and not results[0].reason and type(results[0].returncode) is int and
            0 <= results[0].elapsed_s <= TIMEOUT, 'Exact complete result/budget')


def run(image, out, digest, authorized, review, review_sha):
    require(authorized and digest, 'Explicit authorization required; preparation is not launch permission')
    terminal_plan_gate(out, digest, image)
    plan = read(out / 'plan.json')
    approvals = authorization_gate(plan, digest, review, review_sha)
    ledger, repo, (parent, options, testcase, _) = common.image_context(image)
    require(ledger['snapshot_sha256'] == plan['snapshot_sha256'], 'Snapshot drift')
    owner, resource = service_identity(), common.resources(out, JOBS, plan['reserved_slots'])
    durable(out / 'launch.json', dict(owner=owner, admission=resource, approval_pins=approvals,
                                    plan_sha256=digest, started=time.time()))
    abort = threading.Event()
    terminal = dict(status='NOT_PASS', plan_sha256=digest, results=[], retries=0, pins_unchanged=False)
    import ara_verify.runner as engine
    from ara_verify.trace import validate_trace
    root = out / 'replay/tests' / RUNTIME_ID
    with common.abort_signals(abort), engine_hooks(engine, abort, root, ledger['simv']):
        try:
            require(not (out / 'replay').exists(), 'No retries/overwrite')
            case = plan['case']
            def admission(name):
                require(name == RUNTIME_ID and not abort.is_set(), 'Unknown/aborted dispatch')
                terminal_plan_gate(out, digest, image)
                common.base.verify_pins(approvals)
                common.resources(out, JOBS, plan['reserved_slots'])
            def check(result):
                report = checker.artifacts(result, case, ledger, plan['spec'], validate_trace)
                durable(result.artifact_dir / 'strict_prefix.json', report)
            opts = build_options(options, repo, out, ledger)
            tests = [testcase(RUNTIME_ID, 'app', '', Path(case['elf']), RUNTIME_ID, TIMEOUT)]
            results = checked_runner(parent, abort, check, admission)(opts, tests, sys.argv).run()
            terminal['results'] = [dict(asdict(r), artifact_dir=str(r.artifact_dir)) for r in results]
            terminal_gate(results, read(out / 'replay/run.json'), abort, ledger)
            require(read(out / 'replay/summary.json') == terminal['results'], 'Summary mismatch')
            terminal_plan_gate(out, digest, image)
            common.image_context(image)
            common.base.verify_pins(approvals)
            child = read(root / 'child_outcome.unvalidated.json')
            require(child['name'] == RUNTIME_ID and child['source_label'] == SOURCE_LABEL and
                    type(child['returncode']) is int and child['returncode'] == 0 and
                    child['timed_out'] is False and child['failure_seen'] is False,
                    'Durable child result not exact runtime rc0')
            files = [out / 'launch.json', out / 'replay/run.json', out / 'replay/summary.json']
            files += [root / n for n in ('input.elf', 'inputs.json', 'command.json', 'console.log',
                      'work/run.vcs.log', 'commit_trace.csv', 'trace_summary.json', 'strict_prefix.json',
                      'child_outcome.unvalidated.json', 'runner_result.unvalidated.json',
                      'child_command.provenance.json')]
            terminal.update(status=PASS, pins_unchanged=True, evidence_pins={str(p): sha(p) for p in files},
                            full_child_acceptance=False, Linux_execution=False)
        except BaseException as error:
            abort.set()
            cause_path = root / 'first_cause.json'
            cause = read(cause_path) if cause_path.is_file() else dict(
                kind='WORKER_EXCEPTION', error=f'{type(error).__name__}: {error}')
            first_cause(out, cause)
            terminal.update(status='NOT_PASS', error=f'{type(error).__name__}: {error}')
            # A failed checker can prevent Runner.run() from publishing summary; retain the direct child record.
            child = out / 'replay/tests' / RUNTIME_ID / 'child_outcome.unvalidated.json'
            if child.is_file():
                terminal['unvalidated_child_outcome'] = read(child)
        finally:
            terminal['finished'] = time.time()
            common.publish(out, terminal, abort)
    print(terminal['status'], flush=True)
    return int(terminal['status'] != PASS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'dryrun', 'run'))
    parser.add_argument('--image', type=Path, default=Path(IMAGE))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--reserved-slots', type=int, default=0)
    for name in ('authorize-prepare', 'authorize-run'):
        parser.add_argument('--'+name, action='store_true')
    for name in ('plan-sha256', 'reference-ready-sha256', 'independent-audit-sha256', 'parent-review-sha256'):
        parser.add_argument('--'+name)
    for name in ('reference-ready', 'independent-audit', 'parent-review'):
        parser.add_argument('--'+name, type=Path)
    args = parser.parse_args()
    image, out = args.image.resolve(), args.out.resolve()
    require(out.parent == HERE, 'Only owned direct output directory allowed')
    if args.mode == 'prepare':
        require(args.authorize_prepare, 'Explicit prepare gate required')
        durable(HERE / 'prepare_attempt01.json', dict(command=sys.argv, cwd=str(Path.cwd()),
                started=time.time(), out=str(out), no_DUT=True, parent_run_approval='UNRESOLVED'))
        try:
            prepare(image, out, args.reserved_slots, args.reference_ready, args.reference_ready_sha256,
                    args.independent_audit, args.independent_audit_sha256)
        except BaseException as error:
            durable(HERE / 'prepare_rejected01.json', dict(status='PREFLIGHT_REJECTED_NO_DUT',
                    error=f'{type(error).__name__}: {error}', no_retry=True, time=time.time()))
            raise
        return 0
    if args.mode == 'dryrun':
        dryrun(image, out, args.plan_sha256)
        return 0
    env = common.base.shared.environment()
    os.environ.clear()
    os.environ.update(env)
    return run(image, out, args.plan_sha256, args.authorize_run, args.parent_review, args.parent_review_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
