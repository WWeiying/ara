#!/usr/bin/env python3
"""Exactly one reviewed bounded full reference, with durable numeric outcomes."""
import argparse
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time
sys.dont_write_bytecode=True
import prepare as p
from reference_check02 import audit
REVIEW_ROOT=Path(__file__).resolve().parent
HERE=REVIEW_ROOT

def read(path):return json.loads(path.read_text())
def check_pins(pins):
    for path,digest in pins.items():p.old.require(p.sha(Path(path))==digest,'Pin drift '+path)

def offline(folder):
    pins=read(folder/'preflight_pins.json');check_pins(pins)
    execution=read(folder/'execution.json')
    p.old.require(type(execution['returncode']) is int and execution['returncode']==0 and
                  execution['timeout'] is False and execution['retries']==0,'Actual reference outcome')
    p.save(folder/'audit_started.json',dict(pid=os.getpid(),attempt=1,raw_parse_count=1))
    raw=folder/'commits.log';before=raw.stat();digest=p.sha(raw)
    try:report=audit(raw)
    except BaseException as error:
        p.save(folder/'firstfailure.json',dict(firstcause=repr(error),raw_sha256=digest,
            actual_execution=execution,no_retry=True))
        raise
    after=raw.stat()
    p.old.require((before.st_ino,before.st_size,before.st_mtime_ns)==
        (after.st_ino,after.st_size,after.st_mtime_ns) and digest==p.sha(raw),'Raw changed during audit')
    check_pins(pins)
    report.update(raw_sha256=digest,raw_bytes=after.st_size,actual_execution=read(folder/'execution.json'),
                  pins_unchanged=True,raw_parse_count=1)
    p.save(folder/'result.json',report)

def execute(review_path,review_sha):
    require=p.old.require
    require(p.sha(review_path)==review_sha,'Review SHA')
    review=read(review_path);entry=read(REVIEW_ROOT/'entry02.json')
    require(review['status']=='NO_BLOCKER_SOURCE_SOFTWARE_FOR_ONE_BOUNDED_REFERENCE_NOT_DUT' and
            review['entry_sha256']==p.sha(REVIEW_ROOT/'entry02.json') and review['one_attempt'] is True and
            review['DUT_authorized'] is False,'Actual independent entry review')
    require(read(HERE/'compiled_review.json')['estimate']['conservative_firmware_envelope']<=3000000,'Reviewed static positive cost envelope')
    pins=dict(entry['pins']);pins[str(REVIEW_ROOT/'entry02.json')]=p.sha(REVIEW_ROOT/'entry02.json')
    pins[str(review_path)]=review_sha;check_pins(pins)
    folder=REVIEW_ROOT/'reference01';folder.mkdir()
    p.save(folder/'preflight_pins.json',pins)
    p.emit(folder/'spike.cmd','rs 4000000\nquit\n')
    command=[str(p.old.SPIKE),'-d','--debug-cmd='+str(folder/'spike.cmd'),
             '--isa=rv64gcv_zvl1024b','-m2','--log-commits','--log='+str(folder/'commits.log'),
             str(HERE/'spike/program.elf')]
    p.save(folder/'command.json',dict(command=command,hard_steps_including_boot=4000000,
        timeout_s=120,max_raw_bytes=768*1024**2,cost_target=3000000,attempt=1,review=str(review_path),review_sha256=review_sha))
    def limits():resource.setrlimit(resource.RLIMIT_FSIZE,(768*1024**2,768*1024**2))
    began=time.monotonic();timedout=False
    with (folder/'spike.log').open('x') as log:
        child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT,
                               preexec_fn=limits,start_new_session=True)
        try:rc=child.wait(timeout=120)
        except subprocess.TimeoutExpired:
            timedout=True;os.killpg(child.pid,signal.SIGKILL);rc=child.wait()
    p.save(folder/'execution.json',dict(returncode=rc,pid=child.pid,timeout=timedout,
        elapsed_s=time.monotonic()-began,retries=0,validated=False))
    try:
        require(type(rc) is int and rc==0 and not timedout,'Reference actual child not zero')
        check_pins(pins)
        command=[sys.executable,'-B',str(Path(__file__).resolve()),'audit']
        p.save(folder/'audit_command.json',dict(command=command,timeout_s=600,attempt=1))
        began=time.monotonic();timedout=False
        with (folder/'audit.log').open('x') as log:
            child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
            try:audit_rc=child.wait(timeout=600)
            except subprocess.TimeoutExpired:timedout=True;child.kill();audit_rc=child.wait()
        p.save(folder/'audit_execution.json',dict(returncode=audit_rc,pid=child.pid,
            timeout=timedout,elapsed_s=time.monotonic()-began,retries=0))
        require(type(audit_rc) is int and audit_rc==0 and not timedout,'Fullraw audit failure')
        report=read(folder/'result.json');check_pins(pins)
        within=report['firmware_to_HTIF']<=3000000
        p.save(HERE/('READY.json' if within else 'HOLD.json'),dict(
            status='REFERENCE_FULL4095_PASS_SOFTWARE_ONLY_NOT_DUT' if within else 'REFERENCE_FULL4095_PASS_HOLD_COST_OVER_3M',
            reference_sha256=p.sha(folder/'result.json'),entry_sha256=p.sha(REVIEW_ROOT/'entry02.json'),
            actual_reference_rc=rc,actual_audit_rc=audit_rc,firmware=report['firmware_to_HTIF'],
            calls=4095,results=262080,guards=8190,returned_vstart_zero=4095,
            helper_instructions=53235,source_pins_unchanged=True,reference_attempts=1,DUT_runs=0,
            projected_seconds_20percent_margin=report['firmware_to_HTIF']/403.97*1.2,
            projection_not_guarantee=True))
        print('READY' if within else 'HOLD',report['firmware_to_HTIF'],flush=True)
    except BaseException as error:
        p.save(folder/'STOPPED.json',dict(status='NOT_ACCEPTED_NO_RETRY',firstcause=repr(error),
            actual_reference_returncode=rc,reference_attempts=1,DUT_runs=0))
        raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['execute','audit'])
    parser.add_argument('--review',type=Path);parser.add_argument('--review-sha');args=parser.parse_args()
    if args.mode=='audit':offline(REVIEW_ROOT/'reference01')
    else:execute(args.review,args.review_sha)
