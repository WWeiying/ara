"""POSTPROCESS_ONLY numeric-first host/scan driver; old failures stay sealed."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
PYTHON = '/usr/bin/python3'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def seal():
    import diagnostic_scan as d
    b = HERE.parent
    a = b.parent
    review = a / 'm8_sentinel_mask_static_review_hilbert01'
    prior = read(b / 'verification_performance02/ENTRY.json')
    pins = dict(prior['pins'])
    profile = read(b / 'soc_profile.json')
    pins.update(profile['source_inputs'])
    reset = read(b / 'reset_profile.json')
    pins.update(reset['rtl_pins'])
    paths = [b / 'diagnostic02_parent_authorization.json',
        b / 'diagnostic01/ENTRY.json', b / 'diagnostic01/diagnose_wait.json',
        b / 'diagnostic01/run01/firstcause.json',
        b / 'verification_performance02/ENTRY.json',
        b / 'verification_performance02/execution_binding.json',
        b / 'verification_performance02/RESULT.md',
        a / 'full_e8_mf4_o2_vcs_m9_successor02/reset_profile.json',
        Path(reset['image']),
        a / 'full_e16_m8_sentinel_mask_reference_entry01/READY.json',
        Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/scoped_rv64c_memory.py'),
        Path(PYTHON)]
    for name in ('DIAGNOSTIC_TERMINAL01', 'PERFORMANCE_ENTRY02', 'PERFORMANCE_TERMINAL02'):
        paths += [review / (name+'.json'), review / (name+'.md')]
    for name in ('python39', 'python311'):
        paths += [b / 'verification_performance02' / name / 'result.json',
                  b / 'verification_performance02' / (name+'_actual_wait.json')]
    paths += list(HERE.glob('*.py')) + [HERE / 'README.md', HERE / 'host_wait.json', HERE / 'host.log']
    root = Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
    frozen = d.old.FROZEN
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path:
            path = Path(path).resolve()
            if path.suffix == '.py' and (root in path.parents or frozen in path.parents):
                paths.append(path)
    for path in paths:
        path = path.resolve()
        assert path != d.old.TRACE.resolve() and path.name != 'runner.py', 'Raw/runner excluded'
        digest = sha(path)
        if str(path) in pins:
            assert pins[str(path)] == digest, 'Inherited pin drift ' + str(path)
        pins[str(path)] = digest
    for path, digest in pins.items():
        assert sha(path) == digest, 'Consumed pin drift ' + path
    assert read(HERE / 'host_wait.json')['actual_wait_returncode'] == 0
    assert read(review / 'PERFORMANCE_TERMINAL02.json')['status'] == 'ACCEPTED_SHORT_DIFFERENTIAL_ONLY'
    parent = b / 'diagnostic02_parent_authorization.json'
    authorization = read(parent)
    assert authorization['status'] == 'CONDITIONAL_APPROVAL_ONE_REVIEWED_CLOSED_TRACE_POSTPROCESS_ONLY'
    assert authorization['plan_sha256'] == d.old.PLAN_SHA
    assert authorization['closed_trace_bytes'] == d.EXPECTED_BYTES
    assert authorization['successor_directory'] == 'diagnostic02' and authorization['max_attempts'] == 1
    assert authorization['interpreter'] == PYTHON and authorization['hard_postprocess_timeout_s'] == 1800
    assert authorization['projected_total_stop_threshold_s'] == 1650
    assert authorization['projection_minimum_processed_bytes'] == 32*1024*1024
    assert authorization['projection_consecutive_excess_checkpoints'] == 2
    assert authorization['DUT_execution_authorized'] is False
    assert authorization['reference_execution_authorized'] is False
    assert authorization['automatic_retry_authorized'] is False
    save(HERE / 'ENTRY.json', dict(status='POSTPROCESS_ONLY_DIAGNOSTIC02_PREPARED_NOT_EXECUTED',
        pins=pins, pin_count=len(pins), full_consumed_local_code_closure=True,
        inherited_producer_plan_sha256=d.old.PLAN_SHA, inherited_checker_sha256=d.old.CHECKER_SHA,
        csv_path=str(d.old.TRACE), expected_csv_bytes=d.EXPECTED_BYTES,
        actual_parent_path=str(parent), actual_parent_sha256=sha(parent),
        hard_seconds=1800, internal_seconds=1790, scope='POSTPROCESS_ONLY',
        interpreter=PYTHON, interpreter_resolved=str(Path(PYTHON).resolve()),
        interpreter_sha256=sha(PYTHON), max_scans=1, semantic_passes=1, same_pass_hash=True,
        row_interval=65536, warmup_bytes=32*1024*1024,
        early_stop='two consecutive post-warmup predicted total finish>1650s',
        raw_preflight_reads=0, old_failures_preserved=True, DUT_authorized=False,
        e8_runtime_authorized=False, no_retry=True,
        required_review_status='NO_BLOCKER_POSTPROCESS_DIAGNOSTIC02_ONCE'))
    print('ENTRY', sha(HERE / 'ENTRY.json'), 'pins', len(pins), flush=True)


mode = sys.argv[1]
if mode == 'seal':
    seal()
    raise SystemExit(0)
assert mode in ('host', 'execute')
if mode == 'execute':
    assert len(sys.argv) == 4
    path = Path(sys.argv[2]).resolve()
    assert sha(path) == sys.argv[3]
    review = read(path)
    entry = read(HERE / 'ENTRY.json')
    assert review['status'] == entry['required_review_status']
    assert review['entry_sha256'] == sha(HERE / 'ENTRY.json')
    assert review['scope'] == 'POSTPROCESS_ONLY' and review['hard_seconds'] == 1800
    assert review['max_scans'] == 1 and review['DUT_authorized'] is False
    assert str(Path(PYTHON).resolve()) == entry['interpreter_resolved']
    assert sha(PYTHON) == entry['interpreter_sha256']
    for name, digest in entry['pins'].items():
        assert sha(name) == digest, 'Pre-pin drift '+name
    assert not (HERE / 'run01').exists()
    save(HERE / 'review_binding.json', dict(path=str(path), sha256=sys.argv[3],
        entry_sha256=sha(HERE / 'ENTRY.json'), scope='POSTPROCESS_ONLY', budget_s=1800))
target = HERE / ('test_budget.py' if mode == 'host' else 'diagnostic_scan.py')
bound = 120 if mode == 'host' else 1800
command = [PYTHON, '-B', str(target)]
save(HERE / (mode+'_command.json'), dict(command=command, cwd=str(HERE),
    budget_s=bound, scope='HOST_ONLY' if mode == 'host' else 'POSTPROCESS_ONLY',
    attempt=1, retry=False, target_sha256=sha(target), driver_sha256=sha(Path(__file__))))
started = time.monotonic()
timed_out = False
with (HERE / (mode+'.log')).open('x') as log:
    child = subprocess.Popen(command, cwd=HERE, stdout=log, stderr=subprocess.STDOUT,
                             start_new_session=True)
    try:
        rc = child.wait(timeout=bound)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(child.pid, signal.SIGKILL)
        rc = child.wait()
    save(HERE / (mode+'_wait.json'), dict(actual_wait_returncode=rc,
        elapsed_s=time.monotonic()-started, timed_out=timed_out, pid=child.pid,
        retries=0, validated=False, scope='POSTPROCESS_ONLY' if mode == 'execute' else 'HOST_ONLY'))
print(mode, 'ACTUAL_WAIT', rc, timed_out, flush=True)
raise SystemExit(124 if timed_out else rc)
