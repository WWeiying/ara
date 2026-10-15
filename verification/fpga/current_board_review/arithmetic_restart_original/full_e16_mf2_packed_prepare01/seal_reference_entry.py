"""One focused observer Host and exact software-only reference entry."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import prepare as p
HERE=Path(__file__).resolve().parent
def durable(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def main():
    pins=p.old.read(HERE/'software_terminal_pins.json')
    for path,digest in pins.items():p.old.require(p.sha(path)==digest,'Actual software pin drift '+path)
    command=[sys.executable,'-B','-m','unittest','-v','test_reference_entry','test_boundary']
    before=dict(pins)
    for path in HERE.iterdir():
        if path.is_file():before[str(path)]=p.sha(path)
    durable(HERE/'reference_host_preflight.json',dict(pins=before,CSV_reads=0,reference_runs=0,DUT_runs=0))
    durable(HERE/'reference_host_command.json',dict(command=command,timeout_s=90,attempt=1))
    start=time.monotonic();timed=False
    with (HERE/'reference_host.log').open('x') as log:
        child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
        try:rc=child.wait(timeout=90)
        except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
        durable(HERE/'reference_host_execution.json',dict(actual_wait_returncode=rc,pid=child.pid,
            elapsed_s=time.monotonic()-start,timed_out=timed,retries=0,validated=False))
    for path,digest in before.items():p.old.require(p.sha(path)==digest,'Focused Host pin drift '+path)
    p.old.require(rc==0 and not timed,'Focused observer Host failed; no automatic retry')
    for path in HERE.iterdir():
        if path.is_file():pins[str(path)]=p.sha(path)
    durable(HERE/'reference_entry.json',dict(status='PENDING_EXACT_INDEPENDENT_REFERENCE_ENTRY_NOT_DUT',
        pins=pins,scope=dict(SEW=16,LMUL='mf2',CAP=32,vtype=15,calls=4095,results=131040,guards=8190,
            vstart=4095,helpers=53235,output_reads=36855,checked_bytes=68,tail_bytes=4,
            physical_registers=1,observed_register_bytes=64,physical_mask_bytes=128,vlm_read_bytes=4),
        bounds=dict(finite_debug_script='rs 4000000\nquit\n',hard_steps=4000000,
            wall_s=120,raw_bytes=768*1024**2,cost_target=3000000,audit_wall_s=600),
        one_attempt=True,DUT_authorized=False,Host_scope='Constructed exact-site lifecycle boundaries; not a captured full raw trace',
        review_schema=dict(status='NO_BLOCKER_SOURCE_SOFTWARE_FOR_ONE_BOUNDED_REFERENCE_NOT_DUT',
            entry_sha256='Exact SHA256 of this file',one_attempt=True,DUT_authorized=False)))
    print('PENDING_EXACT_REFERENCE_ENTRY',p.sha(HERE/'reference_entry.json'),flush=True)
if __name__=='__main__':main()
