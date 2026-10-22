#!/usr/bin/env python3
"""One reviewed recovery parse of the existing raw; no simulator launch path."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time
sys.dont_write_bytecode=True
from context import HERE,SOFT,read,save,require,artifacts,sha
from lifecycle import Lifecycle
import reference_check

OLD=HERE.parent/'reference_entry02'
RAW=OLD/'reference01/commits.log'
RAW_SHA='4c570d9e9a24d3b0dd2a50dd865c999ac017a8d918efd17b190c30acc941ceee'
OUT=HERE/'closed01'

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def verify(pins):
    for path,want in pins.items():require(digest(path)==want,'Pinned identity drift '+path)

def old_outcome():
    x=read(OLD/'reference01/execution.json');bad=read(OLD/'reference01/audit_execution.json')
    require(type(x['returncode']) is int and x['returncode']==0 and x['timeout'] is False and
        type(x['retries']) is int and x['retries']==0,'Original actual Spike numeric0/no retry')
    require(type(bad['returncode']) is int and bad['returncode']==1 and bad['timeout'] is False and
        bad['retries']==0,'Preserve original actual audit1')
    require(read(OLD/'reference01/STOPPED.json')['status']=='NOT_ACCEPTED_NO_RETRY','Old STOPPED preserved')
    require(read(OLD/'reference01/firstfailure.json')['raw_sha256']==RAW_SHA,'Exact failed raw identity')
    command=read(OLD/'reference01/command.json')
    require(command['command']==[
        '/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike','-d',
        '--debug-cmd='+str(OLD/'reference01/spike.cmd'),'--isa=rv64gcv_zvl1024b','-m2',
        '--log-commits','--log='+str(RAW),str(SOFT/'spike/program.elf')], 'Original exact command/backend ELF')
    require((OLD/'reference01/spike.cmd').read_text()=='rs 4000000\nquit\n','Original finite reference command')
    require(RAW.stat().st_size<=768*1024**2,'Original raw bound')
    return x

def prepare():
    old_outcome()
    pins=read(OLD/'reference01/preflight_pins.json')
    for file in ('execution.json','audit_execution.json','firstfailure.json','STOPPED.json',
        'command.json','spike.cmd','audit.log','spike.log','preflight_pins.json'):
        path=OLD/'reference01'/file;pins[str(path)]=digest(path)
    pins[str(RAW)]=RAW_SHA
    for name in ('context.py','reference_check.py','raw_boundary.py'):
        require(sha(HERE/name)==sha(OLD/name),'Unchanged full checker component '+name)
    for p in HERE.iterdir():
        if p.is_file():pins[str(p)]=digest(p)
    verify(pins)
    host=HERE/'host01';host.mkdir()
    save(host/'pins_before.json',pins)
    s,c,h,rows=artifacts();q=Lifecycle(s,c,[h[f'op_{i}'][0]['pc'] for i in range(35)],rows)
    pcs=lambda events,kind:sorted(int(e['pc'],16) for e in events if e['kind'] in kind)
    store={str(seed):pcs(events,('A','B')) for seed,events in q.fp.items()}
    loads={str(seed):pcs(events,('FP',)) for seed,events in q.fp.items()}
    save(host/'static_paths.json',dict(FP_store_union=sorted(q.fp_store_pcs),per_seed_store_PCs=store,
        per_seed_load_PCs=loads,load_classification='Address range fp_inputs[0:32], then exact current-seed event; no seed0 PC whitelist',
        load_PC_sets_equal=loads['0']==loads['1']==loads['2'],
        RNG_store_PCs=sorted({e[1] for e in q.seed}),RNG_FP_disjoint=True,
        positive_source_ordinals=[{key:rows[i-1][key] for key in ('ordinal','seed','op','vl','mode','start')} for i in (1366,3361,5356)],
        delta='Only store classifier union across all actual seed paths; exact current-row event match inherited'))
    command=[sys.executable,'-B','-m','unittest','-v','test_recovery']
    save(host/'command.json',dict(command=command,timeout_s=90,scope='Only focused three-seed successor tests'))
    began=time.monotonic();timeout=False
    with (host/'stdout.log').open('x') as log:
        p=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
        try:rc=p.wait(timeout=90)
        except subprocess.TimeoutExpired:timeout=True;p.kill();rc=p.wait()
    save(host/'receipt.json',dict(pid=p.pid,returncode=rc,timeout=timeout,elapsed_s=time.monotonic()-began,retries=0))
    require(type(rc) is int and rc==0 and not timeout,'Focused recovery Host failed; no offline execution')
    verify(pins)
    for path in host.iterdir():pins[str(path)]=digest(path)
    save(HERE/'entry.json',dict(status='PENDING_INDEPENDENT_ONE_CLOSED_RAW_RECOVERY_REVIEW',pins=pins,
        original_entry_sha256=sha(OLD/'entry.json'),raw=str(RAW),raw_sha256=RAW_SHA,
        scope=read(OLD/'entry.json')['scope'],audit_wall_s=600,firmware_limit=3000000,
        preserve_old_audit_rc=1,original_Spike_runs=1,new_Spike_runs=0,DUT_authorized=False,
        review_schema=dict(status='NO_BLOCKER_ONE_CLOSED_RAW_RECOVERY_NOT_DUT',
            entry_sha256='exact entry.json SHA256',one_offline_attempt=True,Spike_authorized=False,DUT_authorized=False)))
    print('RECOVERY_ENTRY',sha(HERE/'entry.json'),flush=True)

def audit():
    admission=read(OUT/'admission.json');pins=admission['pins'];verify(pins);actual=old_outcome()
    save(OUT/'audit_started.json',dict(pid=os.getpid(),attempt=1,raw_parse_count=1,raw=str(RAW)))
    before=RAW.stat()
    try:
        result=reference_check.audit(RAW)
        after=RAW.stat()
        require((before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns),'Closed raw mutated')
        verify(pins)
        result.update(raw_sha256=RAW_SHA,raw_bytes=after.st_size,actual_original_reference=actual,
            original_failed_audit_preserved=True,recovery_raw_parse_count=1,pins_unchanged=True)
        save(OUT/'result.json',result)
    except BaseException as e:
        save(OUT/'firstfailure.json',dict(firstcause=repr(e),context=reference_check.LAST_CONTEXT,
            raw_sha256=RAW_SHA,automatic_retry=False));raise

def execute(review_path,review_sha):
    require(digest(review_path)==review_sha,'Exact independent recovery review')
    review=read(review_path);entry=read(HERE/'entry.json')
    require(review['status']=='NO_BLOCKER_ONE_CLOSED_RAW_RECOVERY_NOT_DUT' and
        review['entry_sha256']==sha(HERE/'entry.json') and review['one_offline_attempt'] is True and
        review['Spike_authorized'] is False and review['DUT_authorized'] is False,'Independent exact recovery admission')
    pins=dict(entry['pins']);pins[str(HERE/'entry.json')]=sha(HERE/'entry.json');pins[str(review_path)]=review_sha
    verify(pins);old_outcome();OUT.mkdir()
    command=[sys.executable,'-B',str(Path(__file__).resolve()),'audit']
    save(OUT/'admission.json',dict(pins=pins,command=command,timeout_s=600,attempt=1,
        review=str(review_path),review_sha256=review_sha,original_failed_audit_preserved=True))
    began=time.monotonic();timeout=False
    with (OUT/'audit.log').open('x') as log:
        p=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
        print('RECOVERY_AUDIT_PID',p.pid,flush=True)
        try:rc=p.wait(timeout=600)
        except subprocess.TimeoutExpired:timeout=True;p.kill();rc=p.wait()
    save(OUT/'audit_execution.json',dict(pid=p.pid,returncode=rc,timeout=timeout,elapsed_s=time.monotonic()-began,retries=0))
    try:
        require(type(rc) is int and rc==0 and not timeout,'Actual recovery audit failed')
        verify(pins);old_outcome();r=read(OUT/'result.json');within=r['firmware_to_HTIF']<=3000000
        save(OUT/'complete.json',dict(status='RECOVERY_COMPLETE_REFERENCE_FULL5985_PASS_SOFTWARE_ONLY_NOT_DUT' if within else 'RECOVERY_FULL5985_HOLD_COST_OVER_3M',
            actual_recovery_audit_rc=rc,original_reference_rc=0,original_audit_rc=1,
            original_STOPPED_preserved=True,pins_unchanged=True,firmware=r['firmware_to_HTIF'],
            result_sha256=sha(OUT/'result.json'),entry_sha256=sha(HERE/'entry.json'),
            review_sha256=review_sha,original_Spike_runs=1,new_Spike_runs=0,DUT_runs=0))
        print('RECOVERY_PASS' if within else 'COST_HOLD',r['firmware_to_HTIF'],flush=True)
    except BaseException as e:
        save(OUT/'complete.json',dict(status='RECOVERY_NOT_ACCEPTED',firstcause=repr(e),
            actual_recovery_audit_rc=rc,timeout=timeout,automatic_retry=False));raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','execute','audit'])
    p.add_argument('--review',type=Path);p.add_argument('--review-sha');a=p.parse_args()
    if a.mode=='prepare':prepare()
    elif a.mode=='audit':audit()
    else:execute(a.review,a.review_sha)
