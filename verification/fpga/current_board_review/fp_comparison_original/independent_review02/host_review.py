"""Isolated host review: real signals and JSON publication, no DUT/prepare/work."""
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
sys.path.insert(0, str(ROOT))
import replay_restart_abort as r

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def main():
    plan_path = ROOT / 'candidate04_restart_plan06/plan.json'
    plan = r.read(plan_path)
    before = {p: sha(p) for p in plan['pins']}
    assert before == plan['pins']
    assert sha(plan_path) == r.read(ROOT / 'candidate04_restart_plan06/preflight.json')['plan_sha256']
    r.old.contract(plan)
    assert plan['cases'] == r.read(r.old.PLAN / 'plan.json')['cases']
    assert plan['held_cases'] == r.read(r.old.PLAN / 'plan.json')['held_cases']
    assert str(r.HELPER) in plan['pins']
    inherited = r.prior.self_test()
    modules = [importlib.import_module(n) for n in ('test_restart_abort', 'test_restart_successor')]
    counts = [unittest.defaultTestLoader.loadTestsFromModule(m).countTestCases() for m in modules]
    log = io.StringIO()
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(m) for m in modules)
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    (OUT / 'host_tests.log').write_text(log.getvalue())
    assert result.wasSuccessful() and counts == [26, 15] and len(inherited) == 27

    reproductions = []
    # Queue real process-directed signals both before the documented eligibility
    # decision and before os.replace. No publication/abort/sigpending mock.
    for sig, boundary in ((s, line) for s in (signal.SIGINT, signal.SIGTERM) for line in (84, 85)):
        abort = r.AbortLatch()
        with tempfile.TemporaryDirectory(prefix='fp-review02-') as temp:
            path = Path(temp) / 'complete.json'
            observations = {}
            def trace(frame, event, arg):
                if (event == 'line' and frame.f_code is r.AbortLatch.publish.__code__
                        and frame.f_lineno == boundary and not observations):
                    observations['terminal_file_existed_at_signal'] = path.exists()
                    os.kill(os.getpid(), sig)
                    observations['pending_before_rename'] = sig in signal.sigpending()
                return trace
            with abort.signals():
                sys.settrace(trace)
                try:
                    accepted = abort.publish(path, {'test': sig.name}, True)
                finally:
                    sys.settrace(None)
                record = r.read(path)
                reproductions.append(dict(signal=sig.name, before_line=boundary, **observations, publish_returned=accepted,
                    abort_latched_on_return=abort.is_set(), terminal=abort.terminal, record=record))
        assert observations['pending_before_rename'] and not observations['terminal_file_existed_at_signal']
        assert accepted and abort.is_set() and record['status'].startswith('PASS_') and record['aborted'] is False

    # Review harness itself is intentionally not a production dependency.
    loaded = {p: digest for p, digest in r.local_modules().items() if Path(p) != Path(__file__).resolve()}
    assert all(plan['pins'].get(p) == digest for p, digest in loaded.items())
    after = {p: sha(p) for p in plan['pins']}
    assert after == before
    evidence = dict(status='BLOCKER_SIGNAL_PUBLICATION_RACE', plan_sha256=sha(plan_path),
        predecessor05_sha256=sha(r.old.PLAN / 'plan.json'), pins_checked=len(before), pins_unchanged=True,
        inherited=27, new_tests=counts[0], old_tests=counts[1], supplied_host_tests_pass=True,
        loaded_production_modules=loaded, race_reproductions=reproductions,
        dut_run=False, prepare_or_work_called=False)
    (OUT / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({k: v for k, v in evidence.items() if k != 'loaded_production_modules'}))

if __name__ == '__main__':
    main()
