#!/usr/bin/env python3
"""One bounded reference, durable actual child wait before one offline parse."""
import argparse
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path
sys.dont_write_bytecode=True
import model as m
import prepare as p
import reference_check as check

LIMIT=8000000
RAW_BYTES=1536*1024*1024
REF=m.HERE/'reference01'

def verify(pins):
    for f,h in pins.items():m.require(m.sha(f)==h,'Pinned reference input drift '+f)

def bound():
    s=json.loads((p.OUT/'spike.symbols.json').read_text());c=p.code((p.OUT/'spike.dis').read_text())
    # Count the actual emitted loop paths, not source-level statement counts.
    init=[pc for pc in c if 0x80000100<=pc<=0x80000146]
    compare=[pc for pc in c if 0x8000024c<=pc<=0x80000272]+[0x800002b8,0x800002ba]
    m.require(c[init[-1]]&127==0x63 and c[compare[-1]]&127==0x63,'Compiled loops differ: re-audit bound')
    loops=144*1024*(len(init)+len(compare))
    # At most 4000 other scalar retirements per original call plus startup/exit.
    # Reset mask/record loops, eight <=35-insn helpers, S transitions, trap CSR
    # capture and outer-loop accounting are included; failure terminates early.
    upper=loops+144*4000+150000
    m.require(upper<LIMIT,'Static reference upper does not fit')
    record=dict(status='STATIC_REFERENCE_BOUND_NOT_DUT',cases=144,
        reset_max_instructions_per_word=len(init),compare_equal_instructions_per_word=len(compare),
        loop_upper_instructions=loops,other_per_case_reserve=4000,startup_exit_reserve=150000,
        static_success_upper_instructions=upper,instruction_limit=LIMIT,timeout_s=120,
        raw_bytes=RAW_BYTES,offline_timeout_s=600,one_reference_attempt=True,no_retry=True,
        isa=p.ISA,spike_elf_sha256=m.sha(p.OUT/'spike.elf'),soc_elf_sha256=m.sha(p.OUT/'soc.elf'),
        linked_bss_end=s['__bss_end'],stack_top=s['__stack_top'],stack_margin=s['__stack_top']-s['__bss_end'],
        note='All144 retained; raw cap finite; time/file bound triggers preserve failure, no increase. '+
             'Mismatch byte slow path may terminate earlier; bounds are a success-path admission, not proof of success.')
    p.save(p.OUT/'bound.json',record)
    print(json.dumps(record))

def audit():
    pins=json.loads((REF/'input_pins.json').read_text());verify(pins)
    result=check.analyze(REF/'spike.trace',p.OUT)
    exe=json.loads((REF/'execution.json').read_text())
    m.require(exe['returncode']==result['source_exit'] and not exe['timeout'],'Actual process outcome vs HTIF/source status')
    m.require(result['firmware_commits']<LIMIT,'Reference instruction limit')
    verify(pins)
    result.update(raw_sha256=m.sha(REF/'spike.trace'),execution=exe,pins_unchanged=True)
    p.save(REF/'status.json',result)
    print(json.dumps({k:result[k] for k in ('status','firmware_commits','cases','numerical','capability','oracle_bytes')}))

def run():
    m.require(not REF.exists(),'Single reference execution; no retry')
    b=json.loads((p.OUT/'bound.json').read_text())
    m.require(b['instruction_limit']==LIMIT and b['timeout_s']==120 and b['raw_bytes']==RAW_BYTES and
              b['static_success_upper_instructions']<LIMIT,'Exact pre-execution bounds')
    m.require(b['spike_elf_sha256']==m.sha(p.OUT/'spike.elf'),'Pinned final ELF')
    pins=json.loads((p.OUT/'input_pins.json').read_text());verify(pins)
    pins.update({str(f):m.sha(f) for f in p.OUT.rglob('*') if f.is_file()})
    pins.update({str(f):m.sha(f) for f in (m.HERE/'reference.py',m.HERE/'reference_check.py',check.DECODER)})
    REF.mkdir();p.save(REF/'input_pins.json',pins);verify(pins)
    cmd=[str(p.SPIKE),'--isa='+p.ISA,'--priv=msu','--pmpregions=0','-m2',
         '--instructions='+str(LIMIT),'-l','--log-commits',str(p.OUT/'spike.elf')]
    p.save(REF/'attempt.json',dict(command=cmd,started=time.time(),bound_sha256=m.sha(p.OUT/'bound.json'),one_attempt=True))
    def limits():resource.setrlimit(resource.RLIMIT_FSIZE,(RAW_BYTES,RAW_BYTES))
    start=time.monotonic();timed=False
    with (REF/'stdout.log').open('x') as stdout,(REF/'spike.trace').open('x') as stderr:
        child=subprocess.Popen(cmd,stdout=stdout,stderr=stderr,preexec_fn=limits)
        try:rc=child.wait(timeout=120)
        except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
    execution=dict(returncode=rc,timeout=timed,elapsed_s=time.monotonic()-start,
                   raw_bytes=(REF/'spike.trace').stat().st_size,command=cmd)
    p.save(REF/'execution.json',execution)
    verify(pins)
    if timed or rc not in (0,77):
        p.save(REF/'not_completed.json',dict(status='REFERENCE_NOT_ACCEPTED_NO_RETRY',execution=execution))
        return 1
    start=time.monotonic();timed=False
    with (REF/'audit.log').open('x') as f:
        child=subprocess.Popen([sys.executable,'-B',str(m.HERE/'reference.py'),'audit'],stdout=f,stderr=subprocess.STDOUT)
        try:rc=child.wait(timeout=600)
        except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
    p.save(REF/'audit_wait.json',dict(returncode=rc,timeout=timed,elapsed_s=time.monotonic()-start))
    if rc or timed:
        p.save(REF/'not_completed.json',dict(status='REFERENCE_RAW_AUDIT_REJECTED_NO_RETRY',
                    execution=execution,audit_returncode=rc,audit_timeout=timed))
    print(json.dumps(dict(reference_returncode=execution['returncode'],audit_returncode=rc,audit_timeout=timed)))
    return int(rc!=0 or timed)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('bound','run','audit'))
    args=parser.parse_args()
    raise SystemExit({'bound':bound,'run':run,'audit':audit}[args.mode]() or 0)
