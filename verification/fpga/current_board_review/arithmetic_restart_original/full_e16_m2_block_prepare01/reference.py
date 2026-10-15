"""Exactly one independently reviewed finite full4095 Spike cost reference."""
import argparse
import hashlib
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
from reference_check import audit
HERE=Path(__file__).resolve().parent
def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def durable(path,value):
    with Path(path).open('x') as stream:
        json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
def check_pins(pins):
    for path,digest in pins.items():p.old.require(sha(path)==digest,'Pin drift '+path)
def offline(folder):
    pins=read(folder/'preflight_pins.json');check_pins(pins)
    execution=read(folder/'execution.json')
    p.old.require(type(execution['actual_wait_returncode'])is int and execution['actual_wait_returncode']==0 and
        not execution['timed_out'] and execution['retries']==0,'Actual reference numeric exit')
    durable(folder/'audit_started.json',dict(pid=os.getpid(),raw_parse_count=1,attempt=1))
    raw=folder/'commits.log';before=raw.stat();digest=sha(raw)
    try:report=audit(raw)
    except BaseException as error:
        durable(folder/'firstfailure.json',dict(firstcause=repr(error),raw_sha256=digest,
            actual_execution=execution,no_retry=True));raise
    after=raw.stat()
    p.old.require((before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns) and
        sha(raw)==digest,'Closed raw changed during audit')
    check_pins(pins)
    report.update(raw_sha256=digest,raw_bytes=after.st_size,actual_execution=execution,
        pins_pre_post_unchanged=True,raw_parse_count=1)
    durable(folder/'result.json',report)
def execute(review_path,review_sha):
    require=p.old.require
    require(sha(review_path)==review_sha,'Actual independent review SHA')
    review=read(review_path);entry=read(HERE/'reference_entry.json')
    require(review['status']=='NO_BLOCKER_SOURCE_SOFTWARE_FOR_ONE_BOUNDED_REFERENCE_NOT_DUT' and
        review['entry_sha256']==sha(HERE/'reference_entry.json') and review['one_attempt'] is True and
        review['DUT_authorized'] is False,'Exact independent finite reference admission')
    require(entry['scope']==dict(SEW=16,LMUL='m2',CAP=128,vtype=9,calls=4095,results=524160,guards=8190,
        vstart=4095,helpers=53235,output_reads=135135,checked_bytes=260,tail_bytes=4,
        physical_registers=2,observed_register_bytes=256,physical_mask_bytes=128,vlm_read_bytes=16),
        'Actual typed16 full4095 reference scope')
    require(read(HERE/'compiled_review.json')['estimate']['conservative_firmware_envelope']<=3000000,'Static bounded cost')
    pins=dict(entry['pins']);pins[str(HERE/'reference_entry.json')]=sha(HERE/'reference_entry.json')
    pins[str(review_path)]=review_sha;check_pins(pins)
    folder=HERE/'reference01';folder.mkdir()
    durable(folder/'preflight_pins.json',pins)
    with (folder/'spike.cmd').open('x') as f:f.write('rs 4000000\nquit\n');f.flush();os.fsync(f.fileno())
    command=[str(p.old.SPIKE),'-d','--debug-cmd='+str(folder/'spike.cmd'),
        '--isa=rv64gcv_zvl1024b','-m2','--log-commits','--log='+str(folder/'commits.log'),str(HERE/'spike/program.elf')]
    durable(folder/'command.json',dict(command=command,hard_steps_including_boot=4000000,
        timeout_s=120,max_raw_bytes=768*1024**2,cost_target=3000000,attempt=1,
        review=str(review_path),review_sha256=review_sha))
    def limit():resource.setrlimit(resource.RLIMIT_FSIZE,(768*1024**2,768*1024**2))
    began=time.monotonic();timed=False
    with (folder/'spike.log').open('x') as log:
        child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT,preexec_fn=limit,start_new_session=True)
        try:rc=child.wait(timeout=120)
        except subprocess.TimeoutExpired:timed=True;os.killpg(child.pid,signal.SIGKILL);rc=child.wait()
        durable(folder/'execution.json',dict(actual_wait_returncode=rc,pid=child.pid,elapsed_s=time.monotonic()-began,
            timed_out=timed,retries=0,validated=False))
    try:
        require(type(rc)is int and rc==0 and not timed,'Reference actual child failed')
        check_pins(pins)
        command=[sys.executable,'-B',str(Path(__file__).resolve()),'audit']
        durable(folder/'audit_command.json',dict(command=command,timeout_s=600,attempt=1))
        began=time.monotonic();timed=False
        with (folder/'audit.log').open('x') as log:
            child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
            try:audit_rc=child.wait(timeout=600)
            except subprocess.TimeoutExpired:timed=True;child.kill();audit_rc=child.wait()
            durable(folder/'audit_execution.json',dict(actual_wait_returncode=audit_rc,pid=child.pid,
                elapsed_s=time.monotonic()-began,timed_out=timed,retries=0,validated=False))
        require(type(audit_rc)is int and audit_rc==0 and not timed,'Full closed audit failed')
        report=read(folder/'result.json');check_pins(pins)
        fw=report['firmware_to_HTIF'];within=fw<=3000000
        durable(HERE/('READY.json' if within else 'HOLD.json'),dict(
            status='REFERENCE_FULL4095_PASS_SOFTWARE_ONLY_NOT_DUT' if within else 'REFERENCE_PASS_HOLD_COST_OVER_3M',
            SEW=16,LMUL='m2',CAP=128,vtype=9,calls=4095,results=524160,guards=8190,
            returned_vstart_zero=4095,helper_instructions=53235,packed_output_reads=135135,
            checked_bytes_each=260,tail_bytes=4,typed_sentinel='005b',physical_registers=2,vlm_read_bytes=16,
            physical_mask_bytes=128,firmware=fw,firmware_to_replay_exit=report['firmware_to_exit'],
            firmware_count_basis='ACTUAL_CLOSED_COMMIT_LEDGER_NOT_DEBUG_COUNTER',
            actual_reference_rc=rc,actual_audit_rc=audit_rc,reference_sha256=sha(folder/'result.json'),
            entry_sha256=sha(HERE/'reference_entry.json'),actual_review_sha256=review_sha,
            actual_reference_execution_sha256=sha(folder/'execution.json'),
            actual_audit_execution_sha256=sha(folder/'audit_execution.json'),
            source_pins_pre_post_unchanged=True,reference_attempts=1,EOF_checked=report['EOF_checked'],
            DUT_runs=0,original_Linux_historical_stall_closed=False,
            projected_seconds_20percent_margin=fw/403.97*1.2,projection_not_guarantee=True))
        print('READY' if within else 'HOLD',fw,flush=True)
    except BaseException as error:
        durable(folder/'STOPPED.json',dict(status='NOT_ACCEPTED_NO_RETRY',firstcause=repr(error),
            actual_reference_returncode=rc,reference_attempts=1,DUT_runs=0));raise
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('execute','audit'))
    parser.add_argument('--review',type=Path);parser.add_argument('--review-sha');args=parser.parse_args()
    if args.mode=='audit':offline(HERE/'reference01')
    else:execute(args.review,args.review_sha)
