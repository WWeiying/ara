#!/usr/bin/env python3
"""Finite rs4M executor successor only; original typed16 observer is unchanged."""
import argparse
import json
from pathlib import Path
import resource
import subprocess
import sys
import time
sys.dont_write_bytecode=True
import prepare as p
from reference_check import audit
HERE=p.HERE
ENTRY=HERE/'entry02.json'
def read(path):return json.loads(Path(path).read_text())
def verify(pins):
    for path,digest in pins.items():p.old.require(p.sha(path)==digest,'Actual input pin drift '+path)

def offline():
    folder=HERE/'reference01';pins=read(folder/'preflight_pins.json');verify(pins)
    raw=folder/'commits.log';before=raw.stat();digest=p.sha(raw)
    report=audit(raw)
    after=raw.stat()
    p.old.require((before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns) and
        digest==p.sha(raw),'Closed raw changed during full parse')
    verify(pins)
    report.update(raw_sha256=digest,raw_bytes=after.st_size,pins_pre_post_unchanged=True,
        actual_execution=read(folder/'execution.json'),source_SEW=16,source_LMUL='m8',source_CAP=512,
        vtype=11,physical_registers_each_group=8,checked_output_bytes=1028,tail_read_bytes=4,
        physical_input_bytes_each=2048,upper_predicate_bytes_zero=64,
        firmware_count_basis='EXACT_CLOSED_COMMIT_RETIREMENT_LEDGER_NOT_DEBUG_COUNTER',debug_counter_receipt_available=False)
    p.save(folder/'result.json',report)

def execute(review_path,review_sha):
    require=p.old.require
    require(p.sha(review_path)==review_sha,'Actual independent review SHA')
    entry,review=read(ENTRY),read(review_path)
    require(review['status']=='NO_BLOCKER_SOURCE_SOFTWARE_FOR_ONE_BOUNDED_REFERENCE_NOT_DUT' and
        review['entry_sha256']==p.sha(ENTRY) and review['one_attempt'] is True and review['DUT_authorized'] is False,
        'Actual independent successor entry, not blocked prior driver')
    pins=dict(entry['pins']);pins[str(ENTRY)]=p.sha(ENTRY);pins[str(review_path)]=review_sha
    verify(pins);folder=HERE/'reference01';folder.mkdir();p.save(folder/'preflight_pins.json',pins)
    p.emit(folder/'spike.cmd','rs 4000000\nquit\n')
    command=[str(p.old.SPIKE),'-d','--debug-cmd='+str(folder/'spike.cmd'),'--isa=rv64gcv_zvl1024b','-m2',
        '--log-commits','--log='+str(folder/'commits.log'),str(HERE/'spike/program.elf')]
    p.save(folder/'command.json',dict(command=command,debug_script='rs 4000000\nquit\n',hard_steps_including_boot=4000000,
        step_bound_basis='INSTALLED_INTERACTIVE_RUN_DECREMENTS_FINITE_RS_REMAINING_NOT_INSTRUCTION_LIMIT_DEBUG_UNTIL',
        timeout_s=120,max_raw_bytes=768*1024**2,cost_target=3000000,attempt=1,
        review=str(review_path),review_sha256=review_sha,executor_sha256=p.sha(__file__),original_blocked_driver_preserved=True))
    def limits():resource.setrlimit(resource.RLIMIT_FSIZE,(768*1024**2,768*1024**2))
    start=time.monotonic();timed=False
    with (folder/'spike.log').open('x') as log:
        child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT,preexec_fn=limits)
        try:rc=child.wait(timeout=120)
        except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
        p.save(folder/'execution.json',dict(actual_wait_returncode=rc,pid=child.pid,elapsed_s=time.monotonic()-start,
            timed_out=timed,retries=0,validated=False))
    try:
        require(type(rc)is int and rc==0 and not timed,'Actual reference child outcome')
        verify(pins);command=[sys.executable,'-B',str(Path(__file__).resolve()),'audit']
        p.save(folder/'audit_command.json',dict(command=command,timeout_s=600,attempt=1))
        start=time.monotonic();timed=False
        with (folder/'audit.log').open('x') as log:
            child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
            try:audit_rc=child.wait(timeout=600)
            except subprocess.TimeoutExpired:timed=True;child.kill();audit_rc=child.wait()
            p.save(folder/'audit_execution.json',dict(actual_wait_returncode=audit_rc,pid=child.pid,
                elapsed_s=time.monotonic()-start,timed_out=timed,retries=0,validated=False))
        require(type(audit_rc)is int and audit_rc==0 and not timed,'Full typed16 observer rejected; no retry')
        accepted=read(folder/'result.json');verify(pins);within=accepted['firmware_to_exit']<=3000000
        p.save(HERE/('READY.json' if within else 'HOLD.json'),dict(
            status='REFERENCE_FULL4095_PASS_SOFTWARE_ONLY_NOT_DUT' if within else 'REFERENCE_FULL4095_PASS_HOLD_COST_OVER_3M',
            SEW=16,LMUL='m8',CAP=512,vtype=11,firmware=accepted['firmware_to_exit'],calls=4095,results=2096640,
            guards=8190,returned_vstart_zero=4095,helper_instructions=53235,packed_output_reads=528255,checked_bytes_each=1028,
            actual_reference_rc=rc,actual_audit_rc=audit_rc,reference_sha256=p.sha(folder/'result.json'),entry_sha256=p.sha(ENTRY),
            original_blocked_entry_sha256=p.sha(HERE/'entry.json'),actual_reference_execution_sha256=p.sha(folder/'execution.json'),
            actual_audit_execution_sha256=p.sha(folder/'audit_execution.json'),source_pins_pre_post_unchanged=True,
            reference_attempts=1,actual_review_sha256=review_sha,DUT_runs=0,firmware_count_basis=accepted['firmware_count_basis'],
            debug_counter_receipt_available=False,projected_seconds_20percent_margin=accepted['firmware_to_exit']/403.97*1.2,
            projection_not_guarantee=True,original_Linux_historical_stall_closed=False))
        print('READY' if within else 'HOLD',accepted['firmware_to_exit'],flush=True)
    except BaseException as error:
        p.save(folder/'STOPPED.json',dict(status='NOT_ACCEPTED_NO_RETRY',firstcause=repr(error),
            actual_reference_returncode=rc,reference_attempts=1,DUT_runs=0));raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('execute','audit'))
    parser.add_argument('--review',type=Path);parser.add_argument('--review-sha');args=parser.parse_args()
    if args.mode=='audit':offline()
    else:execute(args.review,args.review_sha)
