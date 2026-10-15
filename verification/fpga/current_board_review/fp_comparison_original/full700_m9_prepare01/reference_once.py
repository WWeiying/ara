#!/usr/bin/env python3
"""One bounded Spike execution and one full audit, actual wait receipts first."""
import argparse
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from newscope import HERE, PREVIOUS, IMAGE, IMAGE_SHA, MARKER, BOUND
from model import require
from prepare import RUN, read, save, sha, verify_pins
import strict

SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
OUT = HERE/'reference01'


def wait_first(command, stem, timeout_s, file_limit=None):
    save(str(stem)+'.command.json', dict(command=list(map(str,command)),timeout_s=timeout_s,retries=0))
    def limits():
        if file_limit is not None:
            resource.setrlimit(resource.RLIMIT_FSIZE,(file_limit,file_limit))
    start = time.monotonic()
    with Path(str(stem)+'.log').open('xb') as stream:
        child = subprocess.Popen(list(map(str,command)),stdout=stream,stderr=subprocess.STDOUT,
                                 preexec_fn=limits if file_limit else None)
        timed_out = False
        try:
            rc = child.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            child.kill()
            rc = child.wait()
    save(str(stem)+'.exit.json',dict(returncode=rc,pid=child.pid,timed_out=timed_out,
                                   elapsed_s=time.monotonic()-start))
    require(type(rc) is int and rc==0 and not timed_out, 'Actual bounded child outcome')


def audit():
    result = strict.audit(strict.spike_rows(OUT/'commits.log'),strict.specification(RUN/'spike.elf',True),True)
    require(MARKER in result['reconstructed_console'] and not strict.VETO.search(result['reconstructed_console']), 'Original raw full700 marker')
    require(result['calls'][-1]['flags']==1 and result['calls'][-1]['vstart']==0, 'Actual endpoint700 flags/vstart')
    save(OUT/'strict_result.json',result)
    print('RAW700_ACCEPTED',result['target_calls'],result['firmware_retired_to_exit'],flush=True)


def main():
    require(not OUT.exists(),'Reference exactly once')
    prepared = read(RUN/'PREPARED.json')
    require(prepared['status']=='COMPILED_HOST_PASS_REFERENCE_NOT_RUN' and sha(RUN/'pins.json')==prepared['pins_sha256'], 'Closed Host/source preparation')
    pins = read(RUN/'pins.json')
    for path in (RUN/'pins.json',RUN/'PREPARED.json',SPIKE,Path(__file__)):
        pins[str(path)] = sha(path)
    verify_pins(pins)
    OUT.mkdir()
    save(OUT/'input_pins.json',pins)
    try:
        debug = OUT/'spike.cmd'
        with debug.open('x') as stream:
            stream.write('rs 3000000\nquit\n')
        cmd = [SPIKE,'-d','--debug-cmd='+str(debug),'--isa=rv64gcv_zvfh_zvl1024b','-m2',
               '--log-commits','--log='+str(OUT/'commits.log'),RUN/'spike.elf']
        save(OUT/'bounds.json',dict(max_instructions=3000000,process_timeout_s=180,
                                  max_log_bytes=768*1024**2,audit_timeout_s=180,retries=0))
        wait_first(cmd,OUT/'spike',180,768*1024**2)
        wait_first([sys.executable,'-B',Path(__file__),'audit'],OUT/'audit',180)
        verify_pins(pins)
        result = read(OUT/'strict_result.json')
        oldref = read(PREVIOUS/'reference01/result.json')
        prior = read(PREVIOUS/'prepared01/complete.json')
        ratio = result['firmware_retired_to_exit']/oldref['firmware_retired_to_exit']
        seconds = prior['results'][0]['elapsed_s']*ratio
        require(seconds*1.2 < 10800, 'Measured firmware budget projection exceeds3h')
        save(OUT/'result.json',dict(status='SOURCE700_FULL_DYNAMIC_REFERENCE_ACCEPTED_NOT_DUT',
             calls=BOUND,predecessors=BOUND-1,result_bits=358400,guards=1400,flags=700,vstarts=700,
             helper_instructions=result['helper_instructions'],firmware=result['firmware_retired_to_exit'],
             baseline_firmware=oldref['firmware_retired_to_exit'],baseline_actual_M8_s=prior['results'][0]['elapsed_s'],
             nominal_projection_s=seconds,margin20_projection_s=seconds*1.2,case_budget_s=10800,
             actual_reference=read(OUT/'spike.exit.json'),actual_audit=read(OUT/'audit.exit.json'),
             raw_sha256=sha(OUT/'commits.log'),raw_bytes=(OUT/'commits.log').stat().st_size,
             pins_pre_post_unchanged=True,endpoint_call=result['calls'][-1],
             limitation='M8 throughput projection onto frozenM9, not runtime guarantee or full17920 acceptance'))
        for path in OUT.iterdir():
            if path.is_file():pins[str(path)] = sha(path)
        save(HERE/'pins.json',pins)
        save(HERE/'READY.json',dict(status='SOURCE700_HOST_COMPILE_FULL_REFERENCE_READY_NOT_DUT',
             scope='Original first700/699 predecessors; retained1252 and1472 reports kept distinct',
             source_reports=str(RUN/'source_budget_gate.json'),pins_sha256=sha(HERE/'pins.json'),
             soc_elf=str(RUN/'soc.elf'),soc_elf_sha256=sha(RUN/'soc.elf'),
             spike_elf=str(RUN/'spike.elf'),spike_elf_sha256=sha(RUN/'spike.elf'),
             image=str(IMAGE),image_sha256=IMAGE_SHA,reference=str(OUT/'result.json'),
             calls=700,predecessors=699,result_bits=358400,guards=1400,flags=700,vstarts=700,
             helper_instructions=12880,case_budget_s=10800,nominal_projection_s=seconds,
             margin20_projection_s=seconds*1.2,no_DUT_execution=True))
        print('READY700',sha(HERE/'READY.json'),seconds,seconds*1.2,flush=True)
    except BaseException as error:
        save(OUT/'STOPPED.json',dict(firstcause=repr(error),no_retry=True))
        raise


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('mode',choices=['reference','audit'])
    args=ap.parse_args()
    audit() if args.mode=='audit' else main()
