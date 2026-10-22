"""Review-gated two-interpreter short bench; each child fixed120s, no retry."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
PYTHONS = ('/usr/bin/python3.9', '/usr/bin/python3.11')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(p, value):
    with p.open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


if sys.argv[1:] == ['seal']:
    paths = list(HERE.glob('*.py')) + [HERE / 'README.md']
    old = json.loads((HERE.parent / 'diagnostic01/ENTRY.json').read_text())
    pins = dict(old['pins'])
    for p in paths:
        pins[str(p)] = sha(p)
    for p, h in pins.items():
        assert sha(p) == h, 'Original/source pin drift ' + p
    save(HERE / 'ENTRY.json', dict(status='SHORT_PERFORMANCE_PREPARED_NOT_EXECUTED',
        pins=pins, interpreters=list(PYTHONS), per_child_timeout_s=120,
        max_children=2, captured_raw_authorized=False,
        expected_review_status='NO_BLOCKER_SHORT_PERFORMANCE_ONLY',
        old_entry_sha256=sha(HERE.parent / 'diagnostic01/ENTRY.json')))
    print('ENTRY', sha(HERE / 'ENTRY.json'), flush=True)
    raise SystemExit(0)

assert len(sys.argv) == 3, 'Actual independent review path and SHA required'
review_path = Path(sys.argv[1]).resolve()
assert sha(review_path) == sys.argv[2]
review = json.loads(review_path.read_text())
entry = json.loads((HERE / 'ENTRY.json').read_text())
assert review['status'] == entry['expected_review_status']
assert review['entry_sha256'] == sha(HERE / 'ENTRY.json')
assert review['captured_raw_authorized'] is False and review['per_child_timeout_s'] == 120
for p, h in entry['pins'].items():
    assert sha(p) == h, 'Pre-pin drift ' + p
save(HERE / 'execution_binding.json', dict(review_path=str(review_path),
    review_sha256=sys.argv[2], entry_sha256=sha(HERE / 'ENTRY.json'), retries=0))
for index, interpreter in enumerate(PYTHONS):
    label = 'python39' if index == 0 else 'python311'
    command = [interpreter, '-B', str(HERE / 'compare_short.py'), label]
    save(HERE / (label + '_command.json'), dict(command=command, cwd=str(HERE),
        executable_sha256=sha(interpreter), timeout_s=120, attempts=1))
    started = time.monotonic()
    timed_out = False
    with (HERE / (label + '.log')).open('x') as log:
        child = subprocess.Popen(command, cwd=HERE, stdout=log, stderr=subprocess.STDOUT,
                                 start_new_session=True)
        try:
            rc = child.wait(timeout=120)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(child.pid, signal.SIGKILL)
            rc = child.wait()
        save(HERE / (label + '_actual_wait.json'), dict(actual_wait_returncode=rc,
            elapsed_s=time.monotonic()-started, timed_out=timed_out, pid=child.pid,
            retries=0, validated=False))
    if rc or timed_out:
        raise SystemExit(124 if timed_out else rc)
for p, h in entry['pins'].items():
    assert sha(p) == h, 'Post-pin drift ' + p
print('TWO_SHORT_CHILDREN_EXIT0_NO_RAW', flush=True)
