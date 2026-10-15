#!/usr/bin/env python3
"""One offline child; numeric wait persists before reading its report."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import observer
HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--review',type=Path,required=True)
    parser.add_argument('--review-sha',required=True);args=parser.parse_args()
    if observer.sha(args.review)!=args.review_sha:raise ValueError('Actual successor review hash differs')
    paths=[Path(__file__).resolve(),HERE/'observer.py',HERE/'host_result.json',HERE/'host_execution.json',
        args.review,SOURCE/'reference01/STOPPED.json',SOURCE/'reference01/execution.json']
    pins={str(p):observer.sha(p) for p in paths}
    command=[sys.executable,'-B',str(HERE/'observer.py')]
    observer.save(HERE/'audit_command.json',dict(command=command,timeout_s=600,pins=pins,Spike_runs=0,DUT_runs=0))
    started=time.monotonic();timed_out=False
    with (HERE/'audit.log').open('x') as stream:
        child=subprocess.Popen(command,cwd=HERE,stdout=stream,stderr=subprocess.STDOUT)
        try:rc=child.wait(timeout=600)
        except subprocess.TimeoutExpired:
            timed_out=True;child.kill();rc=child.wait()
        observer.save(HERE/'audit_execution.json',dict(actual_wait_returncode=rc,pid=child.pid,
            elapsed_s=time.monotonic()-started,timed_out=timed_out,retries=0,validated=False))
    if rc or timed_out:raise ValueError('Offline observer child failed; no retry')
    report=json.loads((HERE/'result.json').read_text())
    if report['status']!='ARCHITECTURAL_SOURCE_REFERENCE_ACCEPTED_OLD_OBSERVER_NOT_ACCEPTED':
        raise ValueError('No architectural acceptance')
    if not all(observer.sha(p)==digest for p,digest in pins.items()):raise ValueError('Offline outer post-pin drift')
    within=report['cost_within_target']
    ready=dict(status='READY_SOFTWARE_REFERENCE_ONLY_NOT_DUT' if within else 'HOLD_ACTUAL_COST_OVER_3M',
        actual_Spike_execution_sha256=observer.sha(SOURCE/'reference01/execution.json'),
        actual_offline_execution_sha256=observer.sha(HERE/'audit_execution.json'),
        reference_result_sha256=observer.sha(HERE/'result.json'),
        actual_source_review_sha256='ad414d879181c2a85d74acdb1db4c6d99523e80e545f4a0b12f9f9e7875378dc',
        actual_reference_executor_sha256=observer.sha(SOURCE/'reference.py'),
        actual_successor_review=str(args.review),actual_successor_review_sha256=args.review_sha,
        old_STOPPED_sha256=observer.sha(SOURCE/'reference01/STOPPED.json'),old_STOPPED_preserved=True,
        original_source_pins_sha256=observer.sha(SOURCE/'pins.json'),full_calls=4095,results=2096640,
        guards=8190,returned_vstart_zero=4095,helper_instructions=53235,
        firmware=report['firmware_to_exit'],dictionary_words=10172,ROM_bytes=614110,
        actual_reference_qualified_only=True,original_Linux_historical_stall_closed=False,
        projection_s_with_20_percent_margin=report['firmware_to_exit']/403.97*1.2,
        projection_not_DUT_guarantee=True,DUT_runs=0,Spike_invocations_total=1,pins_pre_post_unchanged=True)
    observer.save(SOURCE/('READY.json' if within else 'HOLD.json'),ready)
    print(json.dumps(ready),flush=True)

if __name__=='__main__':main()
