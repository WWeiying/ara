#!/usr/bin/env python3
"""Bound only new event/meta gate tests; no DUT/reference/build execution."""
import subprocess
import sys
import time
import terminal as t

command=[sys.executable,'-B',str(t.HERE/'test_gates.py')]
t.save(t.HERE/'host_command.json',dict(command=command,timeout_s=30))
start=time.monotonic()
with (t.HERE/'host01.log').open('x') as log:
    child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
    timeout=False
    try:
        rc=child.wait(timeout=30)
    except subprocess.TimeoutExpired:
        timeout=True
        child.kill()
        rc=child.wait()
t.save(t.HERE/'host_exit.json',dict(returncode=rc,timeout=timeout,elapsed_s=time.monotonic()-start,attempt=1))
print('new gate Host actual exit',rc,'timeout',timeout,flush=True)
sys.exit(int(timeout or rc != 0))
