#!/usr/bin/env python3
"""One observer-only Host pass and immutable finite reference entry."""
from context import *
import subprocess
import sys
import time
sys.dont_write_bytecode=True
def main():
    pins=read(SOFT/'pins.json')
    for p,h in pins.items():require(sha(p)==h,'Software pin drift '+p)
    review=HERE.parents[1]/'e32_m1_packed_source_review01/SOFTWARE02_ARTIFACT_COST_REVIEW.md'
    require(sha(review)=='69db13da4235c12bac4a4b3c4ee4e90e369e8025839ea921ecd8b74ed7e1d6c3','Independent actual artifact acceptance')
    pins[str(review)]=sha(review)
    for p in (HERE.parent/'compiled_audit02/RESULT.json',HERE.parent/'compiled_audit02/inspect.py',
              HERE.parent/'compiled_audit02/actual_inspection_receipt.json',SOFT/'proof.json',SOFT/'software_status.json',
              SOFT/'execution_receipt.json',Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')):
        pins[str(p)]=sha(p)
    require(read(HERE.parent/'compiled_audit02/RESULT.json')['positive_path_upper']<=3000000,'Actual static cost gate')
    command=[sys.executable,'-B','-m','unittest','-v','test_observer','test_boundary']
    save(HERE/'host_command.json',dict(command=command,timeout_s=90,scope='Only new observer constructed full5985+focused negatives; no compiler/reference/DUT'))
    started=time.monotonic();timedout=False
    with (HERE/'host.log').open('x') as f:
        child=subprocess.Popen(command,cwd=HERE,stdout=f,stderr=subprocess.STDOUT)
        print('observer Host PID',child.pid,flush=True)
        try:rc=child.wait(timeout=90)
        except subprocess.TimeoutExpired:timedout=True;child.kill();rc=child.wait()
    save(HERE/'host_receipt.json',dict(returncode=rc,pid=child.pid,timeout=timedout,elapsed_s=time.monotonic()-started,attempts=1))
    require(rc==0 and not timedout,'Observer Host failed; evidence retained, no reference')
    for p in HERE.rglob('*'):
        if p.is_file() and p.suffix!='.pyc':pins[str(p)]=sha(p)
    for p,h in pins.items():require(sha(p)==h,'Pre/post pin drift '+p)
    save(HERE/'entry.json',dict(status='PENDING_INDEPENDENT_FINAL_REFERENCE_REVIEW_NOT_DUT',pins=pins,
        scope=dict(cap=32,sew=32,lmul='m1',ops=35,calls=5985,results=191520,guards=11970,vstart=5985,
            helpers=77805,output_reads=101745,output_bytes=136,read_width=8,read_words=17,short_tail=False,
            FP_calls=1890,FP_input_stores=120960,seed_input_stores=276,mask_groups=2205,mask_clear_SD=35280,
            mask_bitset_SB=38955,physical_registers=1,physical_bytes=128,physical_mask=128,vlm_bytes=4,fflags_oracle=False),
        budget=dict(finite_debug_command='rs 4000000\nquit\n',hard_steps_including_boot=4000000,
            firmware_to_HTIF_accept_limit=3000000,wall_s=120,raw_bytes=768*1024**2,audit_wall_s=600),
        one_attempt=True,DUT_authorized=False,
        review_schema=dict(status='NO_BLOCKER_SOURCE_SOFTWARE_FOR_ONE_BOUNDED_REFERENCE_NOT_DUT',
            entry_sha256='exact SHA256 of this entry.json',one_attempt=True,DUT_authorized=False)))
    print('SEALED_REFERENCE_ENTRY',sha(HERE/'entry.json'),flush=True)
if __name__=='__main__':main()
