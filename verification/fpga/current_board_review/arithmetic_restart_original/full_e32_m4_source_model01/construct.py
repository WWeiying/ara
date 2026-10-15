"""One bounded Python source/math construction; no compiler or simulator."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    command = [sys.executable, '-B', str(HERE / 'model.py')]
    invocation = dict(command=command, cwd=str(HERE), wrapper_pid=os.getpid(),
                      start_utc=datetime.now(timezone.utc).isoformat(), timeout_seconds=120,
                      model_sha256=digest(HERE / 'model.py'), wrapper_sha256=digest(Path(__file__)),
                      scope='Authorized source/math model only; no compiled Host/Spike/DUT')
    save(HERE / 'invocation.json', invocation)
    start = time.monotonic()
    timed_out = False
    with (HERE / 'stdout.log').open('xb') as stdout, (HERE / 'stderr.log').open('xb') as stderr:
        child = subprocess.Popen(command, cwd=HERE, stdout=stdout, stderr=stderr)
        save(HERE / 'child.json', dict(pid=child.pid, command=command))
        try:
            rc = child.wait(timeout=120)
        except subprocess.TimeoutExpired:
            timed_out = True
            child.kill()
            rc = child.wait()
    result = HERE / 'generated01/result.json'
    unchanged = digest(HERE / 'model.py') == invocation['model_sha256']
    accepted = rc == 0 and not timed_out and unchanged and result.is_file()
    save(HERE / 'execution.json', dict(actual_child_returncode=rc, timed_out=timed_out,
                                     elapsed_seconds=time.monotonic() - start,
                                     model_unchanged=unchanged, result_sha256=digest(result) if result.exists() else None,
                                     status='SOURCE_MODEL_COMPLETE' if accepted else 'NOT_ACCEPTED'))
    return 0 if accepted else 1


if __name__ == '__main__':
    raise SystemExit(main())
