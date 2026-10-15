#!/usr/bin/env python3
"""One offline e8 audit and the still-unexecuted e64 reference; no rebuild or retry."""
import argparse
import importlib.util
import resource
import subprocess
import sys
import time
from pathlib import Path
sys.dont_write_bytecode=True
import observer as corrected
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
spec=importlib.util.spec_from_file_location('fof_original_preparation',ROOT/'prepare.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

def execute(sew):
    out=HERE/('audit_e8_01' if sew==8 else 'reference_e64_01')
    p.require(not out.exists(),'No offline retry/reference retry')
    software=ROOT/'software01'/f'e{sew}'
    b=p.read(ROOT/'STATIC_BOUND.json');p.verify(b['pins'])
    p.require(b['admit_once'] and b['instruction_limit']==1500000 and b['timeout_s']==120 and b['raw_bytes']==256*1024**2,'Fixed original bounds')
    p.require(p.read(HERE/'host01/execution.json')['actual_wait_returncode']==0,'Correction Host not passed')
    pins=dict(b['pins']);pins[str(ROOT/'STATIC_BOUND.json')]=p.sha(ROOT/'STATIC_BOUND.json')
    pins.update(p.read(software/'input_pins.json'))
    pins.update({str(f):p.sha(f) for f in HERE.iterdir() if f.is_file()})
    pins.update({str(f):p.sha(f) for f in (HERE/'host01').rglob('*') if f.is_file()})
    if sew==8:
        source=ROOT/'reference_e8_01'
        pins.update({str(f):p.sha(f) for f in source.iterdir() if f.is_file()})
        raw=source/'spike.trace';execution=p.read(source/'execution.json')
    else:
        p.require(not (ROOT/'reference_e64_01').exists(),'No prior e64 reference')
        p.require(p.read(HERE/'audit_e8_01/status.json')['status']=='REFERENCE_CHECKER_PASS_NOT_DUT','Shared checker not validated against retained e8')
        pins[str(HERE/'audit_e8_01/status.json')]=p.sha(HERE/'audit_e8_01/status.json')
        raw=out/'spike.trace'
    p.verify(pins);out.mkdir();p.save(out/'input_pins.json',pins)
    if sew==64:
        cmd=[str(p.SPIKE),'--isa='+p.ISA,'--priv=msu','--pmpregions=0','-m2','--instructions=1500000','-l','--log-commits',str(software/'spike.elf')]
        p.save(out/'attempt.json',dict(command=cmd,started=time.time(),one_attempt=True,sew=64))
        def limit():resource.setrlimit(resource.RLIMIT_FSIZE,(256*1024**2,256*1024**2))
        start=time.monotonic();timeout=False
        with (out/'stdout.log').open('x') as stdout,raw.open('x') as stderr:
            child=subprocess.Popen(cmd,stdout=stdout,stderr=stderr,preexec_fn=limit)
            try:rc=child.wait(timeout=120)
            except subprocess.TimeoutExpired:timeout=True;child.kill();rc=child.wait()
        execution=dict(actual_wait_returncode=rc,timeout=timeout,elapsed_s=time.monotonic()-start,
                       raw_bytes=raw.stat().st_size,command=cmd)
        p.save(out/'execution.json',execution)
    start=time.monotonic()
    try:
        p.require(type(execution['actual_wait_returncode']) is int and execution['actual_wait_returncode']==0 and not execution['timeout'],'Actual reference exit')
        result=corrected.analyze(raw,p.read(software/'spike.symbols.json'),corrected.disassemble((software/'spike.dis').read_text()),software/'spike.elf',sew)
        p.verify(pins)
        result.update(execution=execution,raw_path=str(raw),raw_sha256=p.sha(raw),pins_unchanged=True,
                      checker_sha256=p.sha(HERE/'observer.py'),offline_check_elapsed_s=time.monotonic()-start,
                      reference_invocations=1,old_e8_rejection_preserved=True)
        p.save(out/'status.json',result)
        print({k:result[k] for k in ('status','commits','firmware_commits','scalar_checks')},flush=True)
    except BaseException as error:
        p.save(out/'not_completed.json',dict(status='REFERENCE_NOT_ACCEPTED_NO_RETRY',error=f'{type(error).__name__}: {error}',execution=execution));raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--sew',type=int,choices=[8,64],required=True);execute(parser.parse_args().sew)
