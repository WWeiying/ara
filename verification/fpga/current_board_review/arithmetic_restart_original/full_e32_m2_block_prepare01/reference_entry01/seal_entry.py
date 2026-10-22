#!/usr/bin/env python3
"""One focused observer Host run and frozen finite reference admission."""
import sys
sys.dont_write_bytecode=True
from context import *
import subprocess
import time

def main():
    pins=read(SOFT/'pins.json')
    require(sha(HERE.parent/'READY.json')=='9e897752f52024d39adab69e8faaa7719230b57684c5a1f2e52c8167dcee982c','Accepted software READY')
    require(sha(SOFT/'spike/program.elf')=='cbe657411501c8cf974d3c6830caea39847563cfa5f6451ef335eca6e5e809e7','Actual reference ELF')
    require(sha(SOFT/'soc/program.elf')=='b9a09a69f9ae8d93b38f5a3f8de1049967a79127ebb473da7f321e73143039f6','Actual SoC ELF identity, not executed')
    review=HERE.parents[1]/'e32_m2_scalar_source_review01/COST_FINAL.md'
    require(sha(review)=='4e6927a67a56da4710e53078885db33f4d53fe76194d9ff192aba68dd62f179c','Independent artifact/cost review')
    for p in (review,HERE.parent/'READY.json',HERE.parent/'compiled_audit01/RESULT.json',HERE.parent/'compiled_audit01/inspect.py',
              SOFT/'proof.json',SOFT/'software_status.json',SOFT/'execution_receipt.json',SOFT/'pins.json',
              Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')):
        pins[str(p)]=sha(p)
    for p in HERE.rglob('*'):
        if p.is_file() and p.suffix!='.pyc':pins[str(p)]=sha(p)
    for p,h in pins.items():require(sha(p)==h,'Pinned preparation input drift '+p)
    require(read(HERE.parent/'compiled_audit01/RESULT.json')['positive_path_upper']<=3000000,'Actual static cost gate')
    save(HERE/'host_preflight_pins.json',pins)
    command=[sys.executable,'-B','-m','unittest','-v','test_observer','test_boundary']
    save(HERE/'host_command.json',dict(command=command,timeout_s=90,
        scope='Only new observer constructed lifecycle/focused negatives, no compiler/reference/DUT'))
    began=time.monotonic();timedout=False
    with (HERE/'host.log').open('x') as f:
        child=subprocess.Popen(command,cwd=HERE,stdout=f,stderr=subprocess.STDOUT)
        print('observer Host PID',child.pid,flush=True)
        try:rc=child.wait(timeout=90)
        except subprocess.TimeoutExpired:timedout=True;child.kill();rc=child.wait()
    save(HERE/'host_receipt.json',dict(returncode=rc,pid=child.pid,timeout=timedout,elapsed_s=time.monotonic()-began,attempts=1))
    require(type(rc) is int and rc==0 and not timedout,'Observer Host failed; retained, no reference')
    for p,h in pins.items():require(sha(p)==h,'Pre/post input drift '+p)
    for p in HERE.rglob('*'):
        if p.is_file() and p.suffix!='.pyc':pins[str(p)]=sha(p)
    save(HERE/'entry.json',dict(status='PENDING_INDEPENDENT_FINAL_REFERENCE_REVIEW_NOT_DUT',pins=pins,
        scope=dict(cap=64,sew=32,lmul='m2',ops=35,calls=5985,results=383040,guards=11970,vstart=5985,
            helpers=77805,output_reads=197505,output_bytes=264,read_width=8,read_words=33,short_tail=False,
            FP_calls=1890,FP_input_stores=241920,FP_cache_loads=241920,seed_input_stores=552,
            seed_cache_loads=24,seed_cache_stores=24,mask_groups=2205,mask_clear_SD=35280,mask_bitset_SB=77175,
            physical_registers=2,physical_bytes=256,physical_mask=128,vlm_bytes=8,fflags_oracle=False,
            ownership='Actual Spike helper/source lifecycle, not DUT CVX tokens',noop_waiver=False),
        budget=dict(finite_debug_command='rs 4000000\nquit\n',hard_steps_including_boot=4000000,
            firmware_to_HTIF_accept_limit=3000000,wall_s=120,raw_bytes=768*1024**2,audit_wall_s=600),
        one_attempt=True,DUT_authorized=False,
        review_schema=dict(status='NO_BLOCKER_SOURCE_SOFTWARE_FOR_ONE_BOUNDED_REFERENCE_NOT_DUT',
            entry_sha256='exact SHA256 of this entry.json',one_attempt=True,DUT_authorized=False)))
    print('SEALED_REFERENCE_ENTRY',sha(HERE/'entry.json'),flush=True)
if __name__=='__main__':main()
