#!/usr/bin/env python3
"""One new observer-only test pass and immutable reference admission snapshot."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
    with path.open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
def main():
    pins=json.loads((HERE/'pins.json').read_text())
    assert all(sha(path)==digest for path,digest in pins.items())
    source_review=HERE.parent/'e8_m1_packed_source_review01/REVIEW.md'
    assert sha(source_review)=='574feec6248a4912693fe507003cbf5688fbc31906d5726931d53fa8172743cf'
    pins[str(source_review)]=sha(source_review)
    command=[sys.executable,'-B','-m','unittest','-v','test_reference_entry','test_boundary']
    save(HERE/'reference_host_command.json',dict(command=command,timeout_s=60,
        scope='Only new full128 observer lifecycle and post-HTIF EOF; no original/packed Host, compile, Spike or DUT rerun'))
    began=time.monotonic()
    with (HERE/'reference_host.log').open('x') as log:
        child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
        try:rc=child.wait(timeout=60);timeout=False
        except subprocess.TimeoutExpired:child.kill();rc=child.wait();timeout=True
    save(HERE/'reference_host_receipt.json',dict(returncode=rc,pid=child.pid,timeout=timeout,
        elapsed_s=time.monotonic()-began,attempts=1))
    assert rc==0 and not timeout,'New observer host failure retained; no automatic retry'
    for path in HERE.rglob('*'):
        if path.is_file() and path.suffix!='.pyc':pins[str(path)]=sha(path)
    assert all(sha(path)==digest for path,digest in pins.items())
    save(HERE/'entry.json',dict(status='PENDING_INDEPENDENT_FINAL_REFERENCE_REVIEW_NOT_DUT',
        pins=pins,scope=dict(cap=128,sew=8,lmul='m1',calls=4095,results=524160,guards=8190,
            vstart=4095,helpers=53235,output_reads=69615,physical_registers=1,observed_register_bytes=128,
            physical_mask_bytes=128,vlm_read_bytes=16),
        budget=dict(finite_debug_command='rs 4000000\nquit\n',hard_steps_including_boot=4000000,
            firmware_to_HTIF_accept_limit=3000000,wall_s=120,raw_bytes=768*1024**2,audit_wall_s=600,
            explanation='Latest explicit parent authorization: finite4M termination distinct from full firmware3M cost gate; earlier proof3M proposal not an execution receipt'),
        one_attempt=True,DUT_authorized=False,
        review_schema=dict(status='NO_BLOCKER_SOURCE_SOFTWARE_FOR_ONE_BOUNDED_REFERENCE_NOT_DUT',
            entry_sha256='exact SHA256 of this entry.json',one_attempt=True,DUT_authorized=False)))
    print('PENDING_INDEPENDENT_FINAL_REFERENCE_REVIEW_NOT_DUT',sha(HERE/'entry.json'),flush=True)

if __name__=='__main__':main()
