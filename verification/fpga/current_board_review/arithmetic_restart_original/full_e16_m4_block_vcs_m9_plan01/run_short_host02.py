"""One narrow supplemental owner/terminal Host, no full source rerun."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import checker as c
import replay as r
HERE=c.HERE
def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
pins={str(HERE/n):c.sha(HERE/n) for n in ('checker.py','replay.py','terminal_gate.py','reference_terminal_binding.json',
    'test_slidedown_short.py','test_terminal_gate.py','run_short_host02.py','host_records02.py')}
command=[sys.executable,'-B','-m','unittest','-v','test_slidedown_short','test_terminal_gate']
save(HERE/'short_host02_command.json',dict(command=command,timeout_s=30,pins=pins,fullstream_reruns=0))
start=time.monotonic();timed=False
with (HERE/'short_host02.log').open('x') as log:
    child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
    try:rc=child.wait(timeout=30)
    except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
    save(HERE/'short_host02_execution.json',dict(actual_wait_returncode=rc,pid=child.pid,
        elapsed_s=time.monotonic()-start,timed_out=timed,retries=0))
c.common.base.verify_pins(pins)
if rc==0 and not timed:
    save(HERE/'short_host02_result.json',dict(status='PASS_SHORT_OWNER_AND_TERMINAL_GATES',tests=3,
        pins=pins,pins_pre_post_unchanged=True,CSV_reads=0,DUT_runs=0,reference_runs=0,fullsource_reruns=0,
        boundary='Actual source op20/VL1 helper instruction protocol subset; not a full execution/ISA emulator'))
raise SystemExit(rc if not timed else 124)
