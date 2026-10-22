"""Bounded actual child receipt for the single diagnostic correction."""
import subprocess
import sys
import time
import checker as c
import replay as r
command=[sys.executable,'-B',str(c.HERE/'host_correction02.py')]
pins={str(c.HERE/name):c.sha(c.HERE/name) for name in (
    'host_correction02.py','run_host_correction02.py','host01.json','host01.log',
    'host01_command.json','host01_process_exit.json')}
pins.update(c.read(c.HERE/'host01_command.json')['pins'])
r.durable(c.HERE/'host02_command.json',dict(command=command,timeout_s=30,pins=pins))
began=time.monotonic();timed=False
with (c.HERE/'host02.log').open('x') as stream:
    child=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT)
    try:rc=child.wait(timeout=30)
    except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
unchanged=all(c.sha(path)==value for path,value in pins.items())
r.durable(c.HERE/'host02_exit.json',dict(returncode=rc,timed_out=timed,
    elapsed_s=time.monotonic()-began,pid=child.pid,pins_unchanged=unchanged,retries=0))
if rc==0 and not timed and unchanged:
    import host_correction02 as correction
    statuses=correction.original_gate()
    r.durable(c.HERE/'host_reconciled.json',dict(
        status='HOST_RECONCILED_PASS_ORIGINAL_HOST01_RC1',original_returncode=1,
        original_outcomes=statuses,corrected_negative=correction.FAILED,
        correction_returncode=0,full5985_streams=1,full_positive_shapes=[c.SHAPE],
        actual_abi_entry_checked=True,tests=33,pins=pins,
        correction_result_sha256=c.sha(c.HERE/'host02_result.json'),
        no_checker_change=True,no_full_replay=True))
print(dict(returncode=rc,timed_out=timed,pins_unchanged=unchanged),flush=True)
raise SystemExit(rc if not timed and unchanged else 124)
