"""One bounded offline successor CFG audit, preserving the failed first receipt."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

here = Path(__file__).resolve().parent
out = here / 'cfg_receipt02'
out.mkdir(exist_ok=False)
command = [sys.executable, '-u', str(here / 'linked_cfg_successor02.py')]
def save(name, value):
    with (out / name).open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')
save('command.json', dict(argv=command, cwd=str(here), timeout_s=600,
                          kind='STATIC_LINKED_CFG_NOT_ISA_REFERENCE_OR_DUT',
                          predecessor='cfg_receipt01: startup AUIPC SP temporary-address auditor defect'))
t = time.monotonic()
rc, timed_out, error = None, False, None
with (out / 'audit.log').open('x') as log:
    try:
        child = subprocess.Popen(command, cwd=here, stdout=log, stderr=subprocess.STDOUT)
        save('child.json', dict(pid=child.pid, started_wall_ns=time.time_ns()))
        try:
            rc = child.wait(timeout=600)
        except subprocess.TimeoutExpired:
            timed_out = True
            child.kill()
            rc = child.wait()
    except Exception as exc:
        error = repr(exc)
receipt = dict(actual_wait_exit=rc, elapsed_s=time.monotonic()-t, timed_out=timed_out, error=error,
               log_sha256=hashlib.sha256((out/'audit.log').read_bytes()).hexdigest())
save('wait.json', receipt)
print(json.dumps(receipt), flush=True)
raise SystemExit(0 if type(rc) is int and rc == 0 and not timed_out and error is None else 1)
