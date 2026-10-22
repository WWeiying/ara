#!/usr/bin/env python3
"""Bounded actual subprocess wait receipts, Host or once-only offline audit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path, value):
    with path.open('x') as fp:
        json.dump(value, fp, indent=2); fp.write('\n'); fp.flush(); os.fsync(fp.fileno())

def main():
    p = argparse.ArgumentParser(); p.add_argument('mode', choices=('host','audit')); args=p.parse_args()
    out = HERE/('host01' if args.mode=='host' else 'audit01')
    out.mkdir()
    scripts = {str(path):sha(path) for path in HERE.glob('*.py')}
    timeout = 120 if args.mode=='host' else 1800
    command = [sys.executable, '-B', str(HERE/('test_fatal_contract.py' if args.mode=='host' else 'offline.py'))]
    if args.mode=='audit': command += ['--out', str(out)]
    save(out/'invocation.json', dict(command=command, timeout_s=timeout, script_pins=scripts,
                                   once_only=True, retries=0, DUT_runs=0))
    start=time.monotonic(); timed=False
    with (out/'output.log').open('x') as log:
        proc=subprocess.Popen(command, cwd=HERE, stdout=log, stderr=subprocess.STDOUT,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), start_new_session=True)
        try: rc=proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            import signal
            timed=True; os.killpg(proc.pid, signal.SIGKILL); rc=proc.wait()
    # Persist actual numeric wait before any post-validation that could fail.
    save(out/'wait.json',dict(returncode=rc, timeout=timed, elapsed_s=time.monotonic()-start,
                             command=command, script_pins=scripts, output_sha256=sha(out/'output.log')))
    unchanged=all(sha(Path(path))==value for path,value in scripts.items())
    save(out/'closure.json', dict(actual_wait_rc=rc, timeout=timed, scripts_unchanged=unchanged,
         result_sha256=sha(out/'result.json') if (out/'result.json').is_file() else None,
         accepted=rc==0 and not timed and unchanged))
    print(json.dumps(dict(mode=args.mode, returncode=rc, timeout=timed, output=str(out))))
    return int(rc!=0 or timed or not unchanged)

if __name__ == '__main__': raise SystemExit(main())
