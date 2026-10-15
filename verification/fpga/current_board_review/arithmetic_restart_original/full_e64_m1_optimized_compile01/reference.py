#!/usr/bin/env python3
"""One bounded reference attempt per final ELF; no retry, build or DUT path."""
import argparse
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time
sys.dont_write_bytecode=True
from prepare import HERE,SHAPES,SPIKE,ISA,read,save,sha,require
from reference_check import audit

def bound():
    require(read(HERE/'software_status.json')['status']=='HOST_COMPILED_NOT_REFERENCE_NOT_DUT','Software gates required')
    records=[]
    for p in SHAPES:
        root=HERE/p['id'];proof=read(root/'sourceproof.json')
        # Conservative successful-path charges include both reduction and packing
        # work for every operation, and FP setup even for the integer-only shape.
        groups=3*(25 if p['sew']<32 else 35)*7*3
        percall=16*160+16*50+16*32+18*8+160+13
        ceiling=500000+groups*(128*4+16*32+80)+p['calls']*percall
        require(ceiling<p['steps'],'Static successful-path cost exceeds fixed step ceiling')
        records.append(dict(**p,group_iterations=groups,per_call_upper_charge=percall,
            charged_successful_steps=ceiling,seconds=120,attempts=1,
            spike_elf=proof['backends']['spike']['elf'],spike_sha256=proof['backends']['spike']['sha256'],
            soc_sha256=proof['backends']['soc']['sha256']))
    pins=read(HERE/'input_pins.json')
    for path,digest in pins.items():require(sha(path)==digest,'Source/reference input drift '+path)
    for path in HERE.rglob('*'):
        if path.is_file() and not any(part=='reference01' for part in path.parts) and path.name!='bound02.json':pins[str(path)]=sha(path)
    save(HERE/'bound02.json',dict(status='STATIC_REVIEWED_BOUND_NOT_EXECUTED',records=records,pins=pins,
        profile=ISA,raw_policy='Full log-commits, RLIMIT_FSIZE per raw/stdout file; no tail-only reduction',
        success_bound_not_correctness_proof=True,step_limit_includes_boot_and_parking=True,
        no_automatic_retry=True,no_DUT=True))
    print([(r['id'],r['charged_successful_steps'],r['steps']) for r in records])

def execute(name,bound_sha):
    require(sha(HERE/'bound02.json')==bound_sha,'Pinned pre-execution static review required')
    b=read(HERE/'bound02.json');p=next(r for r in b['records'] if r['id']==name)
    for path,digest in b['pins'].items():require(sha(path)==digest,'Input drift before sole reference '+path)
    root=HERE/name;out=root/'reference01';out.mkdir(exist_ok=False)
    symbols=read(root/'spike/symbols.json')
    (out/'spike.cmd').write_text(f'rs {p["steps"]}\nreg 0 minstret\nstr {symbols["replay_log"]:x}\nquit\n')
    command=[str(SPIKE),'-d','--debug-cmd='+str(out/'spike.cmd'),'--isa='+ISA,'-m2',
             '--log-commits','--log='+str(out/'commits.log'),p['spike_elf']]
    save(out/'command.json',dict(command=command,cwd=str(HERE),seconds=120,steps=p['steps'],file_bytes=p['raw_bytes'],
        bound_sha256=bound_sha,spike_sha256=sha(SPIKE),elf_sha256=p['spike_sha256'],attempt=1))
    def limit():resource.setrlimit(resource.RLIMIT_FSIZE,(p['raw_bytes'],p['raw_bytes']))
    start=time.monotonic();timedout=False
    with (out/'spike.stdout').open('x') as stdout:
        proc=subprocess.Popen(command,cwd=HERE,stdout=stdout,stderr=subprocess.STDOUT,preexec_fn=limit,start_new_session=True)
        try:rc=proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            timedout=True;os.killpg(proc.pid,signal.SIGKILL);rc=proc.wait()
    save(out/'execution.json',dict(returncode=rc,elapsed_s=time.monotonic()-start,timeout=timedout,
        pid=proc.pid,raw_bytes=(out/'commits.log').stat().st_size if (out/'commits.log').exists() else 0))
    try:
        require(rc==0 and not timedout,'Actual bounded child did not return zero')
        command=[sys.executable,'-B',str(HERE/'reference.py'),'audit','--case',name,'--bound-sha256',bound_sha]
        save(out/'audit_command.json',dict(command=command,timeout_s=600,attempt=1))
        began=time.monotonic();timed=False
        with (out/'audit.log').open('x') as log:
            child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
            try:audit_rc=child.wait(timeout=600)
            except subprocess.TimeoutExpired:
                timed=True;child.kill();audit_rc=child.wait()
        save(out/'audit_process_exit.json',dict(returncode=audit_rc,timeout=timed,pid=child.pid,
             elapsed_s=time.monotonic()-began,attempt=1))
        require(audit_rc==0 and not timed,'Actual bounded reference audit failed')
        result=read(out/'reference.json')
        for path,digest in b['pins'].items():require(sha(path)==digest,'Input drift after sole reference '+path)
        print(name,result['status'],result['firmware_through_htif'],flush=True)
    except Exception as error:
        save(out/'not_completed.json',dict(status='NOT_ACCEPTED_NO_RETRY',reason=str(error),returncode=rc,
            timeout=timedout,attempt=1,raw_unmodified=True));raise

def offline(name,bound_sha):
    require(sha(HERE/'bound02.json')==bound_sha,'Offline input bound identity')
    b=read(HERE/'bound02.json');p=next(r for r in b['records'] if r['id']==name)
    root=HERE/name;out=root/'reference01';raw=out/'commits.log'
    for path,digest in b['pins'].items():require(sha(path)==digest,'Pre-audit drift '+path)
    before=raw.stat();digest=sha(raw);start=time.monotonic()
    result=audit(root,raw)
    after=raw.stat()
    require((before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==
            (after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns) and sha(raw)==digest,'Reference raw drift')
    result.update(raw_sha256=digest,raw_bytes=after.st_size,stdout_sha256=sha(out/'spike.stdout'),
        bound_sha256=bound_sha,spike_elf_sha256=p['spike_sha256'],actual_execution=read(out/'execution.json'),
        full_raw_parses=1,offline_elapsed_s=time.monotonic()-start)
    save(out/'reference.json',result)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['bound','execute','audit']);parser.add_argument('--case')
    parser.add_argument('--bound-sha256');args=parser.parse_args()
    if args.mode=='bound':bound()
    elif args.mode=='execute':execute(args.case,args.bound_sha256)
    else:offline(args.case,args.bound_sha256)
