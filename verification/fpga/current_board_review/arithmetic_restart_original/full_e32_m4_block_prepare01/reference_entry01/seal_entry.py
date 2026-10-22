#!/usr/bin/env python3
"""Focused observer tests and exact immutable reference admission, not compile."""
import sys
sys.dont_write_bytecode=True
from context import *
import subprocess
import time

def main():
    pins=read(SOFT/'artifact01/PINS.json')
    for p,h in read(SOFT/'READY.json')['pins'].items():
        require(p not in pins or pins[p]==h,'Conflicting accepted input pin');pins[p]=h
    require(sha(SOFT/'READY.json')=='408897aee9a25e6d50ebbab2b3e8fa318b6d6c1fc87e9f4993b8bc493720556c','Accepted software02 READY')
    review=A/'full_e32_m4_static_review01/SOFTWARE02_REVIEW.json'
    require(sha(review)=='bb79e93a9624bfe3cb0e9125f98b92b5172dc33f2d15d120eb78f4a9786397a9','Independent artifact/cost review')
    for p in (review,SOFT/'READY.json',SOFT/'artifact01/PINS.json',
        Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')):
        pins[str(p)]=sha(p)
    for p in HERE.iterdir():
        if p.is_file():pins[str(p)]=sha(p)
    for p,h in pins.items():require(sha(p)==h,'Pinned preparation input drift '+p)
    require(read(SOFT/'artifact01/spike.json')['whole_positive_upper']==2814407,'Actual reviewed static cost')
    save(HERE/'host_preflight_pins.json',pins)
    command=[sys.executable,'-B','-m','unittest','-v','test_entry']
    save(HERE/'host_command.json',dict(command=command,timeout_s=90,
        scope='New observer small synthetic tests only; no compiler/reference/DUT or repeat Host46'))
    began=time.monotonic();timedout=False
    with (HERE/'host.log').open('x') as log:
        child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
        print('observer Host PID',child.pid,flush=True)
        try:rc=child.wait(timeout=90)
        except subprocess.TimeoutExpired:timedout=True;child.kill();rc=child.wait()
    save(HERE/'host_receipt.json',dict(returncode=rc,pid=child.pid,timeout=timedout,
        elapsed_s=time.monotonic()-began,attempts=1))
    require(type(rc) is int and rc==0 and not timedout,'Observer Host failed; retain, no reference')
    for p,h in pins.items():require(sha(p)==h,'Pre/post input drift '+p)
    for p in HERE.iterdir():
        if p.is_file():pins[str(p)]=sha(p)
    save(HERE/'entry.json',dict(status='PENDING_INDEPENDENT_FINAL_REFERENCE_REVIEW_NOT_DUT',pins=pins,
        software_spike_elf_sha256=sha(SOFT/'spike/program.elf'),
        scope=dict(cap=128,sew=32,lmul='m4',vtype=18,ops=35,calls=5985,results=766080,
            guards=11970,vstart=5985,helpers=77805,original_helper_static_instructions=458,
            actual_output_LD=389025,output_bytes=520,read_width=8,read_words=65,short_tail=False,
            expected_LD=124041,ID_LHU=53865,cache_hits=33123,cache_misses_including_firstfill=14757,
            sticky_comparisons=389025,cache_reset_each_call=True,
            FP_calls=1890,FP_input_SW=483840,FP_source_LW=15120,seed_input_SW=1104,
            mask_groups=2205,mask_clear_SD=35280,mask_constant_SB=154350,mask_LBU_required=False,
            physical_registers=4,physical_bytes=512,physical_mask=128,vlm_bytes=16,
            fflags_oracle=False,ownership='Actual Spike source/helper lifecycle, not DUT CVX tokens',noop_waiver=False),
        budget=dict(finite_debug_command='rs 4000000\nquit\n',hard_steps_including_boot=4000000,
            firmware_to_HTIF_accept_limit=3000000,wall_s=120,raw_bytes=768*1024**2,audit_wall_s=600),
        one_attempt=True,DUT_authorized=False,
        review_schema=dict(status='NO_BLOCKER_SOURCE_SOFTWARE_FOR_ONE_BOUNDED_REFERENCE_NOT_DUT',
            entry_sha256='exact SHA256 of this entry.json',one_attempt=True,DUT_authorized=False)))
    print('SEALED_REFERENCE_ENTRY',sha(HERE/'entry.json'),flush=True)

if __name__=='__main__':main()
