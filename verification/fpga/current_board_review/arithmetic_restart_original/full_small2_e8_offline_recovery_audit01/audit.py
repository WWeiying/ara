#!/usr/bin/env python3
"""One authorized e8 recovery traversal; never repairs historical whole2 status."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parent
RECOVERY = BASE/'full_small2_reset_gpr_recovery01'
REVIEW = BASE/'full_small2_reset_gpr_entry_review01'
WORK = BASE/'full_small2_vcs_m6_plan01'
RUN = WORK/'prepared01'
ROOT = RUN/'replay/tests/arithmetic_full_e8_mf8'
RAW = ROOT/'commit_trace.csv'
OUT = HERE/'run01'
OBSERVER = BASE/'full_small2_terminal_audit01/terminal.py'
GENERIC = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/verification/ara_verify/trace.py')
ANCHORS = {
    RECOVERY/'READY.json': '7d2dfe7a3fd630befa53c487749a477a6aae26ea28011215653b7c65d66e3af9',
    RECOVERY/'checker.py': '95f811703a8f13b75fc176cdc599ee30c7ead3007d54ed9ccf872c87b431478f',
    RECOVERY/'reset_profile.json': '308784d27eaf81e2a608cd7cd37a9ac61a22a58ce9eda994715cec58dcd682a4',
    RECOVERY/'pins.json': 'f7c81ea3f40aa2ccb059dce38579463cd151fb93321710d6b588efc648f8e1eb',
    REVIEW/'REVIEW.md': '513d669a21d26a8bae0443edbf4bd08c5fe32c991fc3cd2237487ea4d1c82360',
    RUN/'plan.json': '7ec58e3f38f5877838c7edf898d4b85d4872437dcdc54e7542357e8f2736f9ee',
    OBSERVER: 'bc06b0c5768d68e78f178a6dc044c4906f5204d14c33538aa49fa252520c7161',
    GENERIC: 'b5751d25426ba78893c52359519d3b6f1df6bc9c77eb341c91cdca1ff75b506a',
}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def identity(path):
    s = Path(path).stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def verify(pins):
    for path, digest in pins.items():
        need(Path(path) != RAW, 'Raw CSV must only be hashed during traversal')
        need(sha(path) == digest, 'Pin drift: '+str(path))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def freeze():
    verify(ANCHORS)
    pins = dict(read(RUN/'plan.json')['pins'])
    pins.update(read(RECOVERY/'pins.json'))
    for path, digest in ANCHORS.items():
        need(str(path) not in pins or pins[str(path)] == digest, 'Anchor conflict')
        pins[str(path)] = digest
    paths = [Path(__file__).resolve(), REVIEW/'decision01.json', RUN/'complete.json',
             RUN/'launch.json', RUN/'replay/run.json', RUN/'replay/summary.json',
             WORK/'parent_review.json', BASE/'full_small2_entry_review01/ENTRY.json']
    paths += [ROOT/n for n in ('input.elf', 'inputs.json', 'command.json', 'console.log',
              'work/run.vcs.log', 'child_outcome.unvalidated.json', 'trace_summary.json')]
    for path in paths:
        actual = sha(path)
        need(str(path) not in pins or pins[str(path)] == actual, 'Captured pin conflict')
        pins[str(path)] = actual
    verify(pins)
    save(HERE/'pins.json', pins)
    save(HERE/'authorization.json', dict(scope='e8 only, one full CSV traversal',
         main_authorized=True, audit_timeout_s=900, no_retry=True,
         pins_sha256=sha(HERE/'pins.json'), raw_path=str(RAW), raw_identity=identity(RAW),
         raw_digest_policy='SHA256 during sole authorized traversal, not pre-read',
         preserved=['old e8 ERROR', 'whole2 NOT_PASS/aborted', 'e32 CANCELLED'],
         no_DUT_reference_build=True))
    print('FROZEN', sha(HERE/'pins.json'), sha(HERE/'authorization.json'), flush=True)


def check_inputs(pin_sha, auth_sha):
    need(sha(HERE/'pins.json') == pin_sha and sha(HERE/'authorization.json') == auth_sha,
         'Exact frozen audit authorization required')
    verify(ANCHORS)
    verify(read(HERE/'pins.json'))
    auth = read(HERE/'authorization.json')
    need(auth['pins_sha256'] == pin_sha and identity(RAW) == auth['raw_identity'], 'Raw/input drift')


def audit(pin_sha, auth_sha):
    start = time.monotonic()
    check_inputs(pin_sha, auth_sha)
    observer = load('e8_recovery_observer', OBSERVER)
    module = load('e8_reviewed_reset_successor', RECOVERY/'checker.py')
    old = module.legacy
    plan = read(RUN/'plan.json')
    complete = read(RUN/'complete.json')
    result, cancelled = complete['results']
    need(complete['status'] == 'NOT_PASS' and complete['aborted'] is True and complete['retries'] == 0,
         'Historical whole2 identity changed')
    need(result['name'] == 'arithmetic_full_e8_mf8' and result['status'] == 'ERROR' and
         result['reason'] == 'Postcheck ValueError: Scalar store enables/value/register' and
         cancelled['name'] == 'arithmetic_full_e32_mf2' and cancelled['status'] == 'CANCELLED',
         'Exact authorized historical checker-failure recovery only')
    need(read(RUN/'replay/summary.json') == complete['results'], 'Historical summary mismatch')
    case = plan['cases'][0]
    need(case['id'] == result['name'] and case['shape'] == module.SHAPE and
         result['artifact_dir'] == str(ROOT), 'Exact e8 case required')
    command = read(ROOT/'command.json')
    outcome = read(ROOT/'child_outcome.unvalidated.json')
    observer.outcome_gate(outcome, result, command)
    need(outcome['command_sha256'] == sha(ROOT/'command.json'), 'Monitor command binding')
    ledger = read(Path(plan['image'])/'image.json')
    old.common.check_artifacts(SimpleNamespace(**dict(result, artifact_dir=ROOT)),
                              dict(case, original_name=case['id']), ledger)
    spec = plan['specs'][module.SHAPE]
    old.console_gate((ROOT/'console.log').read_text(), spec['config'])
    need(not old.VETO.search((ROOT/'work/run.vcs.log').read_text()), 'VCS fatal/failure veto')
    decision = read(REVIEW/'decision01.json')
    need(decision['status'] == 'APPROVED_STATIC_E8_RESET_PROFILE_SUCCESSOR_ONLY' and
         decision['review_sha256'] == ANCHORS[REVIEW/'REVIEW.md'], 'Independent approval binding')
    state = module.Strict(spec, read(module.REF/module.SHAPE/'model.json'))
    generic = load('e8_recovery_frozen_generic', GENERIC)
    streams = []
    class HashLines(observer.HashLines):
        def __init__(self, path):
            super().__init__(path)
            streams.append(self)
            s = os.fstat(self.file.fileno())
            need([s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns] == identity(RAW),
                 'Opened raw file identity mismatch')
    observer.HashLines = HashLines
    class Diagnostic:
        def __init__(self):
            self.last_row = None
            self.events = Counter()
        def consume(self, row):
            self.last_row = dict(row)
            self.events[row['event']] += 1
            state.consume(row)
        def finish(self):
            return state.finish()
    wrapped = Diagnostic()
    def checkpoint():
        need(time.monotonic()-start < 885, 'Offline audit deadline')
    save(OUT/'parse_started.json', dict(path=str(RAW), identity=identity(RAW),
         time=time.time(), attempt=1, full_raw_parses_authorized=1))
    try:
        general, specific, digest, stat = observer.one_pass(RAW, wrapped, generic, checkpoint)
        need(dict(status='VALID', **general) == read(ROOT/'trace_summary.json'), 'Generic ledger differs')
        need(general['cvx_exception_count'] == 0 and general['architecture_request_count'] > 0 and
             general['backend_uop_alloc_count'] == general['backend_uop_done_count'] > 0 and
             general['cvx_request_count'] == general['cvx_response_count'] > 0, 'Transport ledgers incomplete')
        need(set(wrapped.events) == {'retire','cvx_req','cvx_resp','arch_start','uop_alloc','uop_done'},
             'Full six-event trace required')
        need([specific[k] for k in ('calls','results','guards','vstart_checks','helper_instructions')] ==
             [4095,65520,8190,4095,53235] and specific['full_order'] and not specific['partitioned'],
             'Full original e8 oracle totals')
        save(OUT/'strict.json', specific)
        check_inputs(pin_sha, auth_sha)
        checkpoint()
        save(OUT/'candidate.json', dict(status='E8_OFFLINE_CHECKS_COMPLETE_PENDING_PROCESS_EXIT',
             raw_sha256=digest, raw_identity=stat, raw_parses=1, generic=general,
             events=dict(wrapped.events), strict_sha256=sha(OUT/'strict.json'),
             pins_unchanged=True, elapsed_s=time.monotonic()-start,
             historical_whole2_status='NOT_PASS', historical_e8_status='ERROR', e32_status='CANCELLED',
             old_monitor_numeric_exit=outcome['returncode'], service_exit='UNCONFIRMED_NOT_INFERRED'))
    except BaseException as error:
        active = None if state.active is None else dict(state.active, reads=sorted(state.active['reads']))
        save(OUT/'first_row_failure.json', dict(error=repr(error), row=wrapped.last_row,
             data_rows=state.rows, cycle=state.cycle, retired=state.retired, calls=len(state.calls),
             active=active, helper=state.helper, helper_index=state.index, regs=state.regs,
             capacity=state.capacity, csr_count=state.csr_count, exited=state.exited,
             prefix_sha256=streams[0].digest.hexdigest() if streams else None,
             reached_EOF=bool(streams and streams[0].eof), no_retry=True))
        raise


def interrupted(*_):
    raise InterruptedError('Offline auditor signal/timeout')


def supervisor(pin_sha, auth_sha):
    OUT.mkdir()
    command = [sys.executable, '-B', str(Path(__file__).resolve()), '--child',
               '--pins-sha', pin_sha, '--authorization-sha', auth_sha]
    save(OUT/'command.json', dict(command=command, timeout_s=900, attempt=1))
    started = time.monotonic()
    rc, timed_out, error = None, False, None
    with (OUT/'audit.log').open('x') as log:
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            rc = child.wait(timeout=895)
        except BaseException as exc:
            error = repr(exc)
            timed_out = isinstance(exc, subprocess.TimeoutExpired)
            child.terminate()
            try:
                rc = child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
                rc = child.wait()
        # Persist actual numeric wait before any acceptance/postchecks.
        save(OUT/'process_exit.json', dict(returncode=rc, timed_out=timed_out, error=error,
             elapsed_s=time.monotonic()-started, pid=child.pid, attempt=1))
    try:
        need(type(rc) is int and rc == 0 and not timed_out and error is None, 'Audit child unsuccessful')
        check_inputs(pin_sha, auth_sha)
        candidate = read(OUT/'candidate.json')
        need(candidate['status'] == 'E8_OFFLINE_CHECKS_COMPLETE_PENDING_PROCESS_EXIT', 'Missing candidate')
        observer = load('e8_atomic_publisher', OBSERVER)
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, observer.signal_abort)
        observer.publish_success(OUT, dict(status='INDEPENDENT_E8_FULL_ORIGINAL_OFFLINE_RECOVERY_ACCEPTED',
             candidate_sha256=sha(OUT/'candidate.json'), process_exit_sha256=sha(OUT/'process_exit.json'),
             pins_sha256=pin_sha, authorization_sha256=auth_sha, raw_sha256=candidate['raw_sha256'],
             raw_parses=1, e8_calls=4095, results=65520, guards=8190, vstarts=4095,
             original_helper_instructions=53235, whole2_accepted=False, e32_status='CANCELLED',
             historical_statuses_unchanged=True, historical_service_exit_confirmed=False))
        return 0
    except BaseException as exc:
        save(OUT/'FIRST_ERROR.json', dict(status='NOT_ACCEPTED_NO_RETRY', error=repr(exc)))
        return 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    m = p.add_mutually_exclusive_group(required=True)
    m.add_argument('--freeze', action='store_true')
    m.add_argument('--run', action='store_true')
    m.add_argument('--child', action='store_true')
    p.add_argument('--pins-sha')
    p.add_argument('--authorization-sha')
    a = p.parse_args()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, interrupted)
    if a.freeze:
        freeze()
        return 0
    need(a.pins_sha and a.authorization_sha, 'Frozen identities required')
    if a.child:
        signal.signal(signal.SIGALRM, interrupted)
        signal.alarm(890)
        audit(a.pins_sha, a.authorization_sha)
        return 0
    return supervisor(a.pins_sha, a.authorization_sha)


if __name__ == '__main__':
    sys.exit(main())
