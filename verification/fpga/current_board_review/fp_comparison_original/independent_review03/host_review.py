"""Host-only independent review of final pending-snapshot publication boundary."""
import dis
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
sys.path.insert(0, str(ROOT))
import replay_restart_atomic as r

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def main():
    plan_path = r.PLAN / 'plan.json'
    plan = r.read(plan_path)
    initial = {p: sha(p) for p in plan['pins']}
    assert initial == plan['pins']
    assert sha(plan_path) == r.read(r.PLAN / 'preflight.json')['plan_sha256']
    predecessor = r.read(r.PREDECESSOR / 'plan.json')
    assert plan['cases'] == predecessor['cases'] and plan['held_cases'] == predecessor['held_cases']
    assert all(plan['pins'].get(p) == digest for p, digest in predecessor['pins'].items())
    r.old.contract(plan)
    inherited = r.prior.self_test()
    mods = [importlib.import_module(n) for n in ('test_restart_successor', 'test_restart_atomic')]
    counts = [unittest.defaultTestLoader.loadTestsFromModule(m).countTestCases() for m in mods]
    log = io.StringIO()
    tests = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(m) for m in mods)
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(tests)
    (OUT / 'host_tests.log').write_text(log.getvalue())
    assert result.wasSuccessful() and counts == [15, 32] and len(inherited) == 27

    code = r.AbortLatch.publish.__code__
    ops = list(dis.get_instructions(code))
    load = next(i for i, op in enumerate(ops) if op.argval == 'sigpending')
    call = next(i for i in range(load + 1, len(ops)) if ops[i].opname in ('CALL', 'CALL_FUNCTION', 'CALL_METHOD'))
    start = next(i for i, op in enumerate(ops) if op.starts_line == 87)
    observations = []
    # Independently sweep every opcode of the final expression up to the actual
    # pending-query CALL. Also characterize the first opcode after that CALL.
    for sig in (signal.SIGINT, signal.SIGTERM):
        for index in range(start, call + 2):
            offset = ops[index].offset
            injected = []
            abort = r.AbortLatch()
            with tempfile.TemporaryDirectory(prefix='fp-review03-') as tmp:
                path = Path(tmp) / 'complete.json'
                def trace(frame, event, arg):
                    if frame.f_code is code:
                        frame.f_trace_opcodes = True
                        if event == 'opcode' and frame.f_lasti == offset and not injected:
                            os.kill(os.getpid(), sig)
                            injected.append(dict(pending=sig in signal.sigpending(), file_exists=path.exists()))
                    return trace
                with abort.signals():
                    sys.settrace(trace)
                    try:
                        accepted = abort.publish(path, {}, True)
                    finally:
                        sys.settrace(None)
                    record = r.read(path)
                    assert abort.is_set()
                assert injected == [dict(pending=True, file_exists=False)]
                expected = index > call
                assert accepted == expected
                assert record['status'] == ('PASS_2_ORIGINAL_PREFIXES_260_CALLS_M4' if expected else 'NOT_PASS')
                observations.append(dict(signal=sig.name, opcode=ops[index].opname, offset=offset,
                                         before_or_at_final_call=index <= call, accepted=accepted, status=record['status']))

    extra = []
    with tempfile.TemporaryDirectory(prefix='fp-review03-guard-') as tmp:
        path = Path(tmp) / 'complete.json'
        release = threading.Event()
        worker = threading.Thread(target=release.wait)
        worker.start()
        try:
            try:
                r.AbortLatch().publish(path, {}, True)
            except ValueError:
                assert not path.exists()
                extra.append('live_python_worker_rejects_publication')
            else:
                raise AssertionError('Live worker accepted')
        finally:
            release.set()
            worker.join()
        errors = []
        def nonmain():
            try:
                r.AbortLatch().publish(path, {}, True)
            except ValueError as error:
                errors.append(str(error))
        thread = threading.Thread(target=nonmain)
        thread.start()
        thread.join()
        assert len(errors) == 1 and not path.exists()
        extra.append('nonmain_publication_rejected')
        for reason in ('ineligible', 'latched'):
            abort = r.AbortLatch()
            if reason == 'latched': abort.set()
            with patch.object(signal, 'sigpending', side_effect=AssertionError('Unexpected query on rejecting path')):
                assert not abort.publish(path, {}, reason != 'ineligible')
            assert r.read(path)['status'] == 'NOT_PASS'
            extra.append(reason + '_short_circuit_cannot_pass')

    loaded = {p: digest for p, digest in r.local_modules().items() if Path(p) != Path(__file__).resolve()}
    assert all(plan['pins'].get(p) == digest for p, digest in loaded.items())
    assert {p: sha(p) for p in plan['pins']} == initial
    evidence = dict(status='NO_BLOCKER_FOR_REVIEWED_SNAPSHOT_CONTRACT', plan_sha256=sha(plan_path),
        predecessor06_sha256=sha(r.PREDECESSOR / 'plan.json'), predecessor05_sha256=sha(r.old.PLAN / 'plan.json'),
        pins_checked=len(initial), pins_unchanged=True, inherited_checks=27, old_tests=15,
        atomic_tests=32, supplied_host_tests_pass=True, opcode_sweep=observations,
        extra_guard_checks=extra, loaded_production_modules=loaded,
        dut_run=False, producer_prepare_or_work_called=False, launch_authority=False)
    (OUT / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({k: v for k, v in evidence.items() if k not in ('loaded_production_modules', 'opcode_sweep')}))
    print('opcode_signal_cases', len(observations))

if __name__ == '__main__':
    main()
