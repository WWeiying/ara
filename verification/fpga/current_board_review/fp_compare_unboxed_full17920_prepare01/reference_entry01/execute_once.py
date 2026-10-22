#!/usr/bin/env python3
"""Conditional sole reference + sole closed audit. No automatic retry or DUT."""
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
HERE=Path(__file__).resolve().parent
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def require(ok,why):
    if not ok:raise ValueError(why)
def limited():
    resource.setrlimit(resource.RLIMIT_FSIZE,(768*1024*1024,768*1024*1024))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
def wait_child(argv,prefix,seconds,limits=None):
    save(prefix.with_suffix('.command.json'),argv)
    t=time.monotonic();timed=False
    with prefix.with_suffix('.log').open('x') as log:
        p=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=limits)
        save(prefix.with_suffix('.started.json'),dict(pid=p.pid,monotonic_start=t,timeout_s=seconds))
        try:rc=p.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            timed=True;os.killpg(p.pid,signal.SIGKILL);rc=p.wait()
    result=dict(actual_wait_exit=rc,timed_out=timed,elapsed_s=time.monotonic()-t,log_sha256=sha(prefix.with_suffix('.log')))
    save(prefix.with_suffix('.wait.json'),result)
    return result
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--review',type=Path,required=True);ap.add_argument('--review-sha256',required=True);args=ap.parse_args()
    require(sha(args.review)==args.review_sha256,'Actual independent review hash')
    review=json.loads(args.review.read_text());entry=json.loads((HERE/'ENTRY.json').read_text())
    require(review['status']=='NO_BLOCKER_REFERENCE_ENTRY' and review['entry_sha256']==sha(HERE/'ENTRY.json') and review['input_pins_sha256']==sha(HERE/'input_pins.json'),'Independent exact entry binding')
    require(entry['reference_executor_sha256']==sha(Path(__file__)) and entry['checker_sha256']==sha(HERE/'checker.py'),'Actual executor/checker identity')
    require(entry['reference_seconds']==120 and entry['audit_seconds']==600 and entry['firmware_limit']==3000000 and entry['raw_limit_bytes']==768*1024*1024 and entry['debug_command']=='rs 4000000\nquit\n','Fixed budget/config')
    pins=json.loads((HERE/'input_pins.json').read_text())
    for p in (args.review,HERE/'ENTRY.json',HERE/'host.wait.json',HERE/'host.log',HERE/'input_pins.json'):pins[str(p)]=sha(p)
    require(all(sha(Path(p))==h for p,h in pins.items()),'Fresh input identity')
    host=json.loads((HERE/'host.wait.json').read_text());require(host['actual_wait_exit']==0 and not host['timed_out'],'Actual short checker Host')
    spec=json.loads((HERE/'spec.json').read_text());out=HERE/'reference01';out.mkdir(exist_ok=False)
    save(out/'inputs_before.json',pins)
    debug=out/'spike.cmd';debug.write_text(entry['debug_command'])
    command=[entry['spike'],'-d','--debug-cmd='+str(debug),'--isa='+entry['isa'],'-m2','--log-commits','--log='+str(out/'commits.log'),spec['elf']]
    try:
        actual=wait_child(command,out/'spike',120,limited)
        require(actual['actual_wait_exit']==0 and not actual['timed_out'],'Actual Spike process outcome')
        raw=out/'commits.log';require(raw.is_file() and 0<raw.stat().st_size<=768*1024*1024,'Closed raw existence/size')
        rawpin=dict(path=str(raw),bytes=raw.stat().st_size,sha256=sha(raw));save(out/'raw_before.json',rawpin)
        require(all(sha(Path(p))==h for p,h in pins.items()),'Inputs drift before one audit')
        audited=wait_child([sys.executable,'-B',str(HERE/'audit_once.py'),str(raw),str(out/'audit01')],out/'audit',600)
        require(audited['actual_wait_exit']==0 and not audited['timed_out'],'Closed audit actual exit')
        result=json.loads((out/'audit01/result.json').read_text())
        require(result['status']=='REFERENCE_FULL17920_PASS_SOURCE_ONLY_NOT_DUT' and result['firmware_to_HTIF']<=3000000,'Full source firmware gate')
        require(sha(raw)==rawpin['sha256'],'Closed raw drift')
        require(all(sha(Path(p))==h for p,h in pins.items()),'Final input drift')
        save(out/'inputs_after.json',pins)
        save(out/'COMPLETE.json',dict(status='REFERENCE_EXECUTOR_PASS_PENDING_TERMINAL_REVIEW_NOT_DUT',result=result,
             actual_reference=actual,actual_audit=audited,raw=rawpin,entry_sha256=sha(HERE/'ENTRY.json'),review_sha256=args.review_sha256,
             result_sha256=sha(out/'audit01/result.json'),input_pins_unchanged=True,reference_attempts=1,closed_semantic_parses=1))
        print('FULL17920_REFERENCE_COMPLETE',result['firmware_to_HTIF'])
    except BaseException as e:
        save(out/'NOT_ACCEPTED.json',dict(status='NOT_ACCEPTED_NO_RETRY',error=repr(e)))
        raise
if __name__=='__main__':main()
