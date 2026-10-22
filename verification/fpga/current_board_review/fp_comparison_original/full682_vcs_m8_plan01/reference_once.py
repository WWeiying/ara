#!/usr/bin/env python3
"""One bounded full-commit reference for unchanged packed ELF, never DUT."""
import hashlib
import json
import resource
import subprocess
import sys
import time
from pathlib import Path
sys.dont_write_bytecode=True
from newscope import HERE, PREP, READY, READY_SHA, MARKER
from model import require
import strict
SPIKE=Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def save(p,d):
    with Path(p).open('x') as f:json.dump(d,f,indent=2)
def main():
    out=HERE/'reference01';require(not out.exists(),'One attempt only')
    require(sha(READY)==READY_SHA,'Source READY identity')
    ready=read(READY);require(sha(PREP/'pins.json')==ready['pins_sha256'],'Source pins')
    pins=read(PREP/'pins.json')
    host=read(HERE/'host_strict02.json');require(host['status']=='PASS_HOST_ONLY','Strict Host required')
    pins.update(host['pins'])
    for p in [HERE/'reference_once.py',HERE/'host_strict02.json',READY,PREP/'pins.json',SPIKE]:pins[str(p)]=sha(p)
    require(all(sha(p)==h for p,h in pins.items()),'Pre-reference input drift')
    elf=PREP/'run01/spike.elf';s=strict.specification(elf,True)
    out.mkdir();save(out/'input_pins.json',pins)
    debug=out/'spike.cmd'
    with debug.open('x') as f:f.write('rs 3000000\nquit\n')
    command=[str(SPIKE),'-d','--debug-cmd='+str(debug),'--isa=rv64gcv_zvfh_zvl1024b','-m2',
             '--log-commits','--log='+str(out/'commits.log'),str(elf)]
    save(out/'command.json',dict(command=command,timeout_s=180,max_steps=3000000,max_bytes=768*1024**2,retry=False))
    def limits():resource.setrlimit(resource.RLIMIT_FSIZE,(768*1024**2,768*1024**2))
    start=time.monotonic()
    try:
        with (out/'spike.log').open('x') as f:
            proc=subprocess.Popen(command,stdout=f,stderr=subprocess.STDOUT,preexec_fn=limits)
            timeout=False
            try:rc=proc.wait(timeout=180)
            except subprocess.TimeoutExpired:timeout=True;proc.kill();rc=proc.wait()
        save(out/'execution.json',dict(pid=proc.pid,returncode=rc,timed_out=timeout,elapsed_s=time.monotonic()-start))
        require(rc==0 and not timeout,'Actual reference process outcome')
        start=time.monotonic()
        result=strict.audit(strict.spike_rows(out/'commits.log'),s,True)
        require(MARKER in result['reconstructed_console'] and not strict.VETO.search(result['reconstructed_console']),'Original complete console')
        require(all(sha(p)==h for p,h in pins.items()),'Post-reference pins')
        save(out/'result.json',dict(**result,raw_sha256=sha(out/'commits.log'),raw_bytes=(out/'commits.log').stat().st_size,
            actual_process=read(out/'execution.json'),pins_unchanged=True,audit_s=time.monotonic()-start))
        print('FULL_DYNAMIC_REFERENCE_ACCEPTED_NOT_DUT',result['target_calls'],result['firmware_retired_to_exit'])
    except BaseException as e:
        save(out/'first_failure.json',dict(error=repr(e),no_retry=True));raise
if __name__=='__main__':main()
