#!/usr/bin/env python3
"""Bounded new-prologue tests only; no CSV auditor or simulator launcher."""
import json
from pathlib import Path
import subprocess
import sys
import time
HERE=Path(__file__).resolve().parent
command=[sys.executable,'-B',str(HERE/'test_prologue.py')]
with (HERE/'host_command.json').open('x') as stream:
    json.dump(dict(command=command,timeout_s=60),stream,indent=2);stream.write('\n')
start=time.monotonic()
with (HERE/'host01.log').open('x') as log:
    child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
    timeout=False
    try: rc=child.wait(timeout=60)
    except subprocess.TimeoutExpired:
        timeout=True;child.kill();rc=child.wait()
with (HERE/'host_exit.json').open('x') as stream:
    json.dump(dict(returncode=rc,timeout=timeout,elapsed_s=time.monotonic()-start,attempt=1),stream,indent=2);stream.write('\n')
print('prologue Host actual exit',rc,'timeout',timeout,flush=True)
sys.exit(int(timeout or rc!=0))
