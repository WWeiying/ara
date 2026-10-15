#!/usr/bin/env python3
"""M9 alignment4 only; reuse accepted controls16 without scheduling them."""
import argparse
from dataclasses import asdict
import importlib.util
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
HERE = Path(__file__).resolve().parent
G = HERE.parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


BASE = G/'unmasked_strided_alignment_soc_m9_prepare01'
old = module('m9_sealed_preparation', BASE/'vcs.py')
m = old.m
require, read, save = old.require, old.read, old.save


def sha(path):
    return old.sha(Path(path))
CHECK = G/'unmasked_strided_alignment_soc_m9_checker_successor01'
CHECK_SHA = '797d0f0457110ae2b0e9c91b09ff81e7f1d0adf4762fbfc2c01a74c725170092'
READY_SHA = 'bd37b47445dcd99565055ead9f7d8f1303beecd700f7bfdd83284816025f171a'
CONTROLS = G/'memory_candidate09_controls16'
AUDIT_SHA = '1e8a3e7ccfd3ae5a0b384be80c5a00285921aebd94dea6ccd0cc3d5bcc32db4d'
TERM = G/'arithmetic_restart_original/macc_disjoint482/full482_optimized_prepare01/vcs_m8_plan03/terminal_publish.py'
TERM_SHA = '495a2f91dde233c040eea231531d414b734184100b7c33a88dda98b6070ec718'
require(sha(TERM) == TERM_SHA, 'Reviewed terminal implementation')
terminal = module('m9_alignment_terminal', TERM)
UNIT = 'ara-strided-alignment4-m9-02.service'
PASS = 'PASS_M9_ALIGNMENT4_SUCCESSOR_CHECKER'
OUT = HERE/'prepared01'


def controls_reuse():
    audit = CONTROLS/'audit_resume01.json'
    require(sha(audit) == AUDIT_SHA, 'Independent controls16 audit identity')
    a = read(audit)
    cp, ct = CONTROLS/'prepared01/plan.json', CONTROLS/'prepared01/complete.json'
    require(a['status'] == 'PASS_INDEPENDENT_M9_CONTROLS16_AUDIT' and a['cases'] == 16
            and a['compared_rows'] == 310350 and sha(cp) == a['plan_sha256']
            and sha(ct) == a['complete_sha256'], 'Accepted controls audit/terminal binding')
    p, t = read(cp), read(ct)
    require(t['status'] == 'PASS_M9_CONTROLS16_ARCHITECTURAL' and t['aborted'] is False
            and t['pins_unchanged'] is True and type(t['retries']) is int and t['retries'] == 0
            and t['cycle_changed_rows'] == 0 and t['compared_rows'] == 310350
            and p['image_sha256'] == old.IMAGE_SHA, 'Controls16 exact M9 acceptance')
    require(len(t['results']) == 16 and {r['name'] for r in t['results']} == {c['id'] for c in p['cases']}
            and all(r['status'] == 'PASS' and type(r['returncode']) is int and r['returncode'] == 0
                    for r in t['results']), 'Controls16 actual numeric outcomes')
    pins = dict(p['pins'])
    pins.update(t['evidence_pins'])
    for f in (audit, cp, ct, CONTROLS/'audit_resume01.py'):
        pins[str(f)] = sha(f)
    return dict(audit=str(audit), audit_sha256=AUDIT_SHA, complete=str(ct),
                complete_sha256=a['complete_sha256'], cases=16, compared_rows=310350,
                reexecuted=False), pins


def contract(p):
    original = read(BASE/'vcs_m9_prepared01/plan.json')
    cases = [c for c in original['cases'] if c['kind'] == 'directed']
    require(len(cases) == 4 and p['cases'] == cases and p['unit'] == UNIT and p['jobs'] == 2
            and p['service_s'] == 4200 and p['worker_s'] == 4000 and p['checker_s'] == 60
            and p['reserved_margin'] == 2 and p['no_build'] is True and type(p['retries']) is int
            and p['retries'] == 0 and p['image'] == str(old.IMAGE) and p['image_sha256'] == old.IMAGE_SHA
            and p['checker'] == str(CHECK/'checker.py') and p['checker_sha256'] == CHECK_SHA
            and all(c['timeout_s'] == 900 and c['stage'] == 'alignment4' for c in cases),
            'Exact alignment4-only contract')


def prepare():
    require(not OUT.exists(), 'Fresh output only')
    require(sha(CHECK/'READY.json') == READY_SHA and sha(CHECK/'checker.py') == CHECK_SHA,
            'Reviewed successor checker')
    ready = read(CHECK/'READY.json')
    require(ready['status'] == 'CHECKER_PREPARED_HOST_PASS_NOT_DUT', 'Checker Host gate')
    host = read(HERE/'host01.json')
    require(host['status'] == 'HOST_WORKER_PASS_NOT_DUT' and host['worker_sha256'] == sha(__file__)
            and host['test_sha256'] == sha(HERE/'test_worker.py'), 'Actual Host binding')
    pins = dict(ready['pins'])
    reuse, control_pins = controls_reuse()
    for path, digest in control_pins.items():
        require(path not in pins or pins[path] == digest, 'Conflicting inherited pin')
        pins[path] = digest
    ledger, repo, _ = old.image_context()
    pins.update(m.image_pins(old.IMAGE, ledger, repo))
    for f in (Path(__file__), HERE/'test_worker.py', HERE/'host01.json', HERE/'AUTHORIZATION.md',
              CHECK/'READY.json', CHECK/'REVIEW.md', TERM):
        pins[str(f)] = sha(f)
    m.base.verify_pins(pins)
    p = dict(status='PREPARED_NOT_RUN', cases=[c for c in read(BASE/'vcs_m9_prepared01/plan.json')['cases']
                                            if c['kind'] == 'directed'],
             pins=pins, image=str(old.IMAGE), image_sha256=old.IMAGE_SHA, unit=UNIT, jobs=2,
             service_s=4200, worker_s=4000, checker_s=60, reserved_margin=2, retries=0, no_build=True,
             checker=str(CHECK/'checker.py'), checker_sha256=CHECK_SHA, controls_reuse=reuse,
             scope='Only new alignment4; already independently accepted M9 controls16 reused, not rerun')
    contract(p)
    OUT.mkdir()
    save(OUT/'plan.json', p)
    print('PREPARED', sha(OUT/'plan.json'), 'pins', len(pins), flush=True)


def review_gate(p, digest, path, expected):
    require(sha(path) == expected, 'Actual independent review hash')
    r = read(path)
    require(r['decision'] == 'ADMIT_ALIGNMENT4_M9' and r['no_blocker'] is True
            and r['plan_sha256'] == digest and r['worker_sha256'] == sha(__file__)
            and r['checker_sha256'] == p['checker_sha256'], 'Concrete independent admission')


def checker_command(case, root):
    return [sys.executable, '-B', str(CHECK/'checker.py'), case['member'],
            str(root/'commit_trace.csv'), case['spec'], str(root/'csv.json')]


def checker_result(v, case):
    require(v['status'] == 'STRIDED_ALIGNMENT_DUT_CSV_PASS'
            and v['lifecycle_successor'] == 'source-bound-nonempty-memory-owners01'
            and v['checks'] == (698 if case['member'].startswith('store') else 697)
            and v['restore_readback_checks'] == 14 and v['memory_owner_count'] == 9
            and v['helper_owner_count'] == 7 and v['target_requests'] == 2
            and len(v['target_owners']) == 2 and len(v['cvx_fault_cycles']) == 1,
            'Full original oracle plus actual nonempty owner gate')


def monitored(original, abort):
    def wrapped(command, cwd, console, timeout_s, cancel_event=None):
        rc, elapsed, timeout, failed = original(command, cwd, console, timeout_s, cancel_event)
        record = dict(returncode=rc, elapsed_s=elapsed, timed_out=timeout, failure_seen=failed,
                      abort_set=abort.is_set() or bool(cancel_event and cancel_event.is_set()),
                      command=list(map(str, command)), cwd=str(cwd))
        # Persist actual child outcome before the runner can fail any postcheck.
        save(Path(console).parent/'child_exit.json', record)
        try:
            old.receipt_ok(record, timeout_s)
        except BaseException:
            abort.set()
            raise
        return rc, elapsed, timeout, failed
    return wrapped


def result_gate(results, metadata, cases, abort):
    m.check_stage(results, metadata, cases, abort)
    require(all(type(r.returncode) is int and r.returncode == 0 for r in results), 'Numeric actual outcomes')


def run(digest, review, review_sha):
    require(sha(OUT/'plan.json') == digest and not (OUT/'launch.json').exists()
            and not (OUT/'alignment4').exists() and not (OUT/'complete.json').exists(), 'Once-only exact plan')
    p = read(OUT/'plan.json')
    contract(p)
    review_gate(p, digest, review, review_sha)
    pins = dict(p['pins'], **{str(review): review_sha})
    m.base.verify_pins(pins)
    ledger, repo, (parent, options, testcase, _) = old.image_context()
    owner = dict(line.split('=', 1) for line in subprocess.check_output(
        ['systemctl', '--user', 'show', UNIT, '-p', 'MainPID', '-p', 'ControlGroup',
         '-p', 'KillMode', '-p', 'Restart', '-p', 'RuntimeMaxUSec'], text=True, timeout=15).splitlines())
    require(owner['MainPID'] == str(os.getpid()) and owner['KillMode'] == 'control-group'
            and owner['Restart'] == 'no' and owner['RuntimeMaxUSec'] == '1h 10min'
            and Path('/proc/self/cgroup').read_text().strip() == '0::'+owner['ControlGroup'],
            'Actual direct bounded systemd owner')
    admission = m.resources(OUT, 2, p['reserved_margin'])
    save(OUT/'launch.json', dict(pid=os.getpid(), owner=owner, admission=admission,
                                plan_sha256=digest, review=str(review), review_sha256=review_sha))
    abort = terminal.TerminalAbort()
    started = time.monotonic()
    expires = started+p['worker_s']
    state = dict(status='NOT_PASS', results=[], retries=0, firstfailure=None,
                 pins_unchanged=False, plan_sha256=digest, review_sha256=review_sha,
                 image_sha256=p['image_sha256'], controls_reuse=p['controls_reuse'])
    failure_lock = threading.Lock()

    def failed(name, error):
        abort.set()
        with failure_lock:
            if state['firstfailure'] is None:
                state['firstfailure'] = dict(case=name, reason=repr(error))
                save(OUT/'firstfailure.json', state['firstfailure'])

    entries = {c['id']: c for c in p['cases']}
    import ara_verify.runner as engine
    original, old_re = engine._run_monitored, engine.FAIL_RE

    class Runner(parent):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.cancel_event = abort

        def _run_test(self, test, image):
            try:
                require(not abort.is_set() and time.monotonic() < expires, 'No dispatch after failure/deadline')
                case = entries[test.name]
                require(sha(case['elf']) == case['sha256'], 'Dispatch ELF drift')
                result = super()._run_test(test, image)
                root = result.artifact_dir
                old.receipt_ok(read(root/'child_exit.json'), 900)
                require(result.status == 'PASS' and type(result.returncode) is int
                        and result.returncode == 0 and not abort.is_set(), 'Actual runner acceptance')
                # The frozen runner already performs validate_trace; its saved
                # trace_summary wraps the count dictionary with status=VALID.
                m.check_artifacts(result, case, ledger)
                cmd = checker_command(case, root)
                save(root/'checker_invocation.json', dict(command=cmd, checker_sha256=CHECK_SHA))
                with (root/'checker.log').open('x') as stream:
                    child = subprocess.run(cmd, stdout=stream, stderr=subprocess.STDOUT, timeout=60)
                save(root/'checker_exit.json', dict(returncode=child.returncode))
                require(type(child.returncode) is int and child.returncode == 0, 'Successor actual checker0')
                checker_result(read(root/'csv.json'), case)
                require(not abort.is_set() and time.monotonic() < expires, 'Postcheck abort/deadline')
                return result
            except BaseException as error:
                failed(test.name, error)
                raise

    opts = options(repo, OUT/'alignment4', 'default', 2, 1, False, False, True,
                   Path(ledger['simv']), True, None)
    tests = [testcase(c['id'], 'app', '', Path(c['elf']), c['original_name'], 900) for c in p['cases']]
    engine._run_monitored = monitored(original, abort)
    engine.FAIL_RE = re.compile(old_re.pattern+'|STRIDED_ALIGNMENT_FAIL|'+m.BAD.pattern, old_re.flags)
    with m.abort_signals(abort):
        try:
            results = Runner(opts, tests, sys.argv).run()
            state['results'] = [dict(asdict(r), artifact_dir=str(r.artifact_dir)) for r in results]
            result_gate(results, read(OUT/'alignment4/run.json'), p['cases'], abort)
            require(read(OUT/'alignment4/summary.json') == state['results'], 'Actual summary membership')
            m.base.verify_pins(pins)
            old.image_context()
            require(not abort.is_set() and state['firstfailure'] is None and time.monotonic() < expires,
                    'No aggregate PASS after failure/deadline')
            state.update(status=PASS, pins_unchanged=True,
                         evidence_pins={str(f): sha(f) for f in (OUT/'alignment4').rglob('*') if f.is_file()})
        except BaseException as error:
            failed('campaign', error)
        finally:
            engine._run_monitored, engine.FAIL_RE = original, old_re
            state['elapsed_s'] = time.monotonic()-started
            terminal.publish(OUT, state, abort, expires)
    print(state['status'], flush=True)
    return int(state['status'] != PASS)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['prepare', 'run'])
    ap.add_argument('--plan-sha256')
    ap.add_argument('--review', type=Path)
    ap.add_argument('--review-sha256')
    args = ap.parse_args()
    env = m.base.shared.environment()
    env.update(XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}',
               DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
    os.environ.clear()
    os.environ.update(env)
    if args.mode == 'prepare':
        prepare()
    else:
        raise SystemExit(run(args.plan_sha256, args.review.resolve(), args.review_sha256))
