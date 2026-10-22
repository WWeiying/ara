"""One bounded filesystem-event wait and one conditionally authorized offline audit."""
import argparse
import ast
import ctypes
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
P = HERE.parent/'fp_compare_unboxed_prefix265_vcs_m6_plan01/prepared01'
PLAN_SHA = 'e3bbb288f69f8f0cc0a24491125e0bb327e04d3edbaa3eb46837bb2c153e0940'
PREPARED_SHA = 'ff5f57910afda05b9eb34ca8551459523fffa952b0282cb4563d1f9a9a9af444'
PASS = 'PASS_M6_ORIGINAL_UNBOXED265_NOT_FULL_PARENT'
NAME = 'fp_compare_unboxed_e16_mf4_prefix265'
UNIT = 'ara-fp-unboxed-original265-m6-01.service'
OUT = HERE/'wait01'


def read(p): return json.loads(Path(p).read_text())


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''): h.update(b)
    return h.hexdigest()


def save(p, value):
    with Path(p).open('x') as f:
        json.dump(value, f, indent=2); f.write('\n')


def verify(pins):
    for p, h in pins.items(): assert sha(p) == h, ('pin drift', p)


def prepare():
    assert not OUT.exists() and sha(HERE/'prepared.json') == PREPARED_SHA
    prepared = read(HERE/'prepared.json'); verify(prepared['static_pins'])
    pins = dict(prepared['static_pins'])
    for name in ('prepared.json', 'CONDITIONAL_AUTHORIZATION.md', 'wait_terminal.py'):
        p = HERE/name
        if p.suffix == '.py': ast.parse(p.read_text(), filename=str(p))
        pins[str(p)] = sha(p)
    OUT.mkdir()
    save(OUT/'plan.json', dict(status='PREPARED_CONDITIONAL_OFFLINE_ONLY', pins=pins,
        plan_sha256=PLAN_SHA, prepared_sha256=PREPARED_SHA, event_wait_seconds=7200,
        audit_timeout_seconds=1200, service_timeout_seconds=8500, audit_attempts=1,
        output=str(HERE/'terminal01'), no_DUT=True, no_reference=True, no_retry=True))
    print(sha(OUT/'plan.json'), flush=True)


def terminal_gate():
    assert sha(P/'plan.json') == PLAN_SHA
    digest = sha(P/'complete.json'); done = read(P/'complete.json'); plan = read(P/'plan.json')
    assert done['status'] == PASS and done['plan_sha256'] == PLAN_SHA
    assert done['aborted'] is False and done['pins_unchanged'] is True
    assert type(done['retries']) is int and done['retries'] == 0 and not done.get('error')
    assert done['full_child_acceptance'] is False and plan['full_parent_acceptance'] is False
    assert len(done['results']) == 1
    r = done['results'][0]
    assert r['name'] == NAME and r['kind'] == 'app' and r['status'] == 'PASS'
    assert type(r['returncode']) is int and r['returncode'] == 0 and not r['reason']
    assert 0 < r['elapsed_s'] <= 5400 and r['artifact_dir'] == str(P/'replay/tests'/NAME)
    run, summary = read(P/'replay/run.json'), read(P/'replay/summary.json')
    assert summary == done['results'] and run['status'] == 'COMPLETE'
    assert run['status_counts'] == {'PASS': 1} and run['tests'] == [NAME] and run['completed_at']
    assert plan['case']['id'] == NAME and plan['spec']['spike'] is False
    strict = read(P/'replay/tests'/NAME/'strict_prefix.json')['strict']
    for key, value in dict(target_calls=265, full_result_bit_checks=4240, guard_checks=530,
                           returned_vstart_zero=265, returned_flags_checked=265,
                           helper_instructions=4587, unused_helper_retirements=0,
                           actual_initialization_stores=76850).items():
        assert strict[key] == value, ('missing full scope', key)
    assert strict['full_reference_vectors'] is False and len(strict['calls']) == 265
    assert [c['ordinal'] for c in strict['calls']] == list(range(1, 266))
    verify(plan['pins']); verify(done['evidence_pins'])
    launch = read(P/'launch.json'); verify(launch['approval_pins'])
    assert launch['plan_sha256'] == PLAN_SHA
    assert sha(P/'complete.json') == digest
    return digest


def process_handle(pid, kind, launch):
    # pidfd observes a specific process lifetime; no rc is inferred from absence.
    try: fd = os.pidfd_open(pid)
    except ProcessLookupError: return None, dict(pid=pid, kind=kind, state='ABSENT_EXIT_UNKNOWN')
    try:
        root = Path('/proc')/str(pid)
        cmd = (root/'cmdline').read_bytes().replace(b'\0', b' ').decode()
        cg = (root/'cgroup').read_text()
        assert any(l.split(':', 2)[-1] == launch['owner']['properties']['ControlGroup'] for l in cg.splitlines())
        if kind == 'simulator':
            assert 'simv' in (root/'comm').read_text() and str(P/'replay/tests'/NAME/'input.elf') in cmd
        else:
            assert str(P.parent/'replay.py') in cmd and str(P) in cmd
        return fd, dict(pid=pid, kind=kind, state='LIVE_IDENTITY_VERIFIED', argv=cmd, cgroup=cg)
    except FileNotFoundError:
        os.close(fd)
        return None, dict(pid=pid, kind=kind, state='DISAPPEARED_EXIT_UNKNOWN')
    except BaseException:
        os.close(fd); raise


def wait_complete(deadline):
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
    assert fd >= 0, ('inotify_init1', ctypes.get_errno())
    handles = []
    try:
        mask = 0x8 | 0x80 | 0x100 | 0x400 | 0x800  # close-write, moved-to, create, delete/move-self
        assert libc.inotify_add_watch(fd, os.fsencode(P), mask) >= 0
        launch = read(P/'launch.json')
        assert launch['plan_sha256'] == PLAN_SHA and launch['owner']['properties']['Id'] == UNIT
        identities = []
        for pid, kind in ((launch['owner']['pid'], 'worker'), (1418946, 'simulator')):
            handle, identity = process_handle(pid, kind, launch)
            identities.append(identity)
            if handle is not None: handles.append(handle)
        save(OUT/'wait_started.json', dict(pid=os.getpid(), started=time.time(), identities=identities,
                                          mechanism='inotify_then_pidfd_events_no_polling'))
        while not (P/'complete.json').is_file():
            remaining = deadline-time.monotonic()
            assert remaining > 0, 'Bounded wait expired without complete'
            ready, _, _ = select.select([fd], [], [], remaining)
            assert ready, 'Bounded wait expired without complete'
            data = os.read(fd, 65536)
            at = 0
            while at < len(data):
                _, event, _, size = struct.unpack_from('iIII', data, at); at += 16+size
                assert not event & (0x400 | 0x800 | 0x4000 | 0x8000), 'Directory/watch lost or event overflow'
        digest = terminal_gate()
        # Publication can precede the worker's final return; wait for observed lifetimes.
        for handle in handles:
            left = min(60.0, deadline-time.monotonic())
            assert left > 0 and select.select([handle], [], [], left)[0], 'Owned process not terminal after complete'
        save(OUT/'terminal_admission.json', dict(status='GATES_PASSED_NOT_AUDIT_ACCEPTANCE', complete_sha256=digest,
            plan_sha256=PLAN_SHA, observed_process_lifetimes_ended=True, process_returncodes_inferred=False,
            child_numeric_rc_source='pinned complete/summary', actual_child_returncode=0, admitted_at=time.time()))
        return digest
    finally:
        os.close(fd)
        for h in handles: os.close(h)


def report(result, complete_sha, rc):
    g, s, o = result['generated']['generic'], result['generated']['strict'], result['observer']
    lines = ['# Independent M6 Unboxed265 Terminal Review', '',
        'Accepted only the original natural265-call prefix, including264 predecessors.',
        f'Actual offline audit command return code: {rc}. No service GC return code inferred.',
        f'One full CSV parse: {g["rows"]} original rows, {g["retire_count"]} retired instructions.',
        f'Full original oracle: {s["full_result_bit_checks"]} result bits, {s["guard_checks"]} guards; '
        f'{s["returned_flags_checked"]} flags and {s["returned_vstart_zero"]} vstart reads.',
        f'Exact helper retirements: {s["helper_instructions"]}; five entire unused ranges: zero.',
        f'Rawft0: {len(o["rawft0_instruction_sources"])} actual fmv.d.x instructions with integer source0.',
        f'Pins unchanged pre/post: {result["pins_verified"]}; '
        f'plan pins {result["full_plan_pins"]}, terminal evidence pins {result["terminal_evidence_pins"]}.',
        f'Actual simulator child rc: {result["child_returncode"]}; elapsed {result["child_elapsed_s"]}s.',
        'No abort/retry; raw logs/firsterror veto, actual exit0 and parking checked.', '',
        'Both lossless row digests: `'+o['before_sha256']+'`.',
        'Result SHA256: `'+sha(HERE/'terminal01/result.json')+'`.',
        'Verified pins SHA256: `'+sha(HERE/'terminal01/verified_pins.json')+'`.',
        'Actual command exit evidence SHA256: `'+sha(OUT/'audit_exit.json')+'`.',
        'Complete SHA256: `'+complete_sha+'`.',
        'Prepared SHA256: `'+PREPARED_SHA+'`.',
        'Plan SHA256: `'+PLAN_SHA+'`.', '',
        'The CSV observes actual PC/code and integer source for rawft0, not direct FPR payload.',
        'Saved flags0/restoration instructions are checked, not post-restore CSR readback.',
        'Reference vector/CSR logs do not substitute for DUT measurements. No full17920 parent',
        'or Linux replay claim; accepted image is frozen M6, not newer workspace RTL.', '']
    with (HERE/'terminal01/REVIEW.md').open('x') as f: f.write('\n'.join(lines))


def run(digest):
    assert digest and sha(OUT/'plan.json') == digest
    waitplan = read(OUT/'plan.json'); verify(waitplan['pins'])
    # Exclusive marker makes any second watcher invocation fail before waiting/auditing.
    save(OUT/'invocation.json', dict(pid=os.getpid(), argv=sys.argv, started=time.time(), wait_plan_sha256=digest))
    child = None
    def cancel(signum, frame): raise RuntimeError('Watcher signal '+str(signum))
    signal.signal(signal.SIGTERM, cancel); signal.signal(signal.SIGINT, cancel)
    try:
        complete_sha = wait_complete(time.monotonic()+waitplan['event_wait_seconds'])
        verify(waitplan['pins'])
        assert not (HERE/'terminal01').exists()
        command = [sys.executable, '-B', str(HERE/'audit.py'), 'terminal', '--authorize-terminal-audit',
            '--prepared-sha256', PREPARED_SHA, '--complete-sha256', complete_sha, '--out', str(HERE/'terminal01')]
        with (OUT/'audit.stdout.log').open('x') as stdout, (OUT/'audit.stderr.log').open('x') as stderr:
            child = subprocess.Popen(command, cwd=HERE, stdout=stdout, stderr=stderr)
            save(OUT/'audit_invocation.json', dict(pid=child.pid, parent_pid=os.getpid(), command=command,
                started=time.time(), complete_sha256=complete_sha, prepared_sha256=PREPARED_SHA,
                authorization_path=str(HERE/'CONDITIONAL_AUTHORIZATION.md'),
                authorization_sha256=sha(HERE/'CONDITIONAL_AUTHORIZATION.md')))
            rc = child.wait(timeout=waitplan['audit_timeout_seconds'])
        save(OUT/'audit_exit.json', dict(pid=child.pid, actual_wait_returncode=rc, observed_at=time.time(),
            evidence='subprocess.Popen.wait of actual owned audit child', stdout_sha256=sha(OUT/'audit.stdout.log'),
            stderr_sha256=sha(OUT/'audit.stderr.log')))
        assert rc == 0, 'Offline audit failed; no retry'
        verify(waitplan['pins'])
        assert sha(P/'complete.json') == complete_sha
        result = read(HERE/'terminal01/result.json')
        assert result['accepted'] is True and result['complete_sha256'] == complete_sha
        assert result['status'] == 'INDEPENDENT_M6_UNBOXED265_FULL_ORACLE_ACCEPTED_NOT_FULL_PARENT'
        report(result, complete_sha, rc)
        save(OUT/'complete.json', dict(status='OFFLINE_AUDIT_ACCEPTED', actual_audit_returncode=rc,
            result_sha256=sha(HERE/'terminal01/result.json'), review_sha256=sha(HERE/'terminal01/REVIEW.md'),
            audit_exit_sha256=sha(OUT/'audit_exit.json'), complete_sha256=complete_sha, no_retry=True))
        print('OFFLINE_AUDIT_ACCEPTED', sha(OUT/'complete.json'), flush=True)
    except BaseException as error:
        if child is not None and child.poll() is None:
            child.kill(); child.wait()
        save(OUT/'not_accepted.json', dict(status='NOT_ACCEPTED_NO_RETRY', error=repr(error), time=time.time()))
        raise


if __name__ == '__main__':
    assert __debug__
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'run')); p.add_argument('--wait-plan-sha256')
    a = p.parse_args()
    if a.mode == 'prepare':
        assert not a.wait_plan_sha256
        prepare()
    else: run(a.wait_plan_sha256)
