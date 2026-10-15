#!/usr/bin/env python3
"""Exactly one2M/256MiB/120s raw reference, only after compiled static gate."""
import resource
import subprocess
import time
import sys
sys.dont_write_bytecode=True
from software_prepare import HERE,base,sha,save,read,ISA,NAME
from strict import specification,spike_rows,audit,VETO
from model import require
MAX_STEPS=2_000_000
MAX_BYTES=256*1024*1024
def main():
    out=HERE/'reference01';require(not out.exists(),'One attempt only, preserve old output')
    cost=read(HERE/'static_cost.json');proof=read(HERE/'source_elf_proof.json')
    require(cost['status']=='STATIC_COMPILED_BUDGET_FITS' and cost['upper_instructions']<MAX_STEPS,'Static budget gate')
    require(read(HERE/'host01/result.json')['status']=='PASS_HOST_2_POSITIVE_7_NEGATIVE','Host oracle not accepted')
    elf=__import__('pathlib').Path(proof['spike_elf']['path']);spec=specification(elf,True)
    pins=read(HERE/'baseline_pins.json')
    for p in [HERE/'source_elf_proof.json',HERE/'static_cost.json',HERE/'host01/result.json',HERE/'reference_once.py',HERE/'strict.py',elf]:pins[str(p)]=sha(p)
    for p,h in pins.items():require(sha(__import__('pathlib').Path(p))==h,'Reference input drift')
    require(sha(elf)==cost['spike_elf_sha256']==proof['spike_elf']['sha256'],'ELF budget drift')
    out.mkdir();save(out/'input_pins.json',pins)
    debug=out/'spike.cmd';debug.write_text(f'rs {MAX_STEPS}\nstr {spec["symbols"]["replay_log"]:x}\nquit\n')
    cmd=[str(base.SPIKE),'-d','--debug-cmd='+str(debug),'--isa='+ISA,'-m2','--log-commits','--log='+str(out/'commits.log'),str(elf)]
    save(out/'command.json',dict(command=cmd,actual_isa=ISA,max_steps=MAX_STEPS,max_bytes=MAX_BYTES,timeout_s=120,attempt=1,retry=False))
    def limits():resource.setrlimit(resource.RLIMIT_FSIZE,(MAX_BYTES,MAX_BYTES))
    t=time.monotonic()
    try:
        with (out/'spike.log').open('x') as stream:r=subprocess.run(cmd,stdout=stream,stderr=subprocess.STDOUT,timeout=120,preexec_fn=limits)
        elapsed=time.monotonic()-t;save(out/'execution.json',dict(returncode=r.returncode,elapsed_s=elapsed))
        require(r.returncode==0,'Spike process failure')
        result=audit(spike_rows(out/'commits.log'),spec,True)
        require(result['firmware_retired_to_exit']<=cost['upper_instructions'],'Compiled bound violated')
        text=result['reconstructed_console'];require(not VETO.search(text),'Raw oracle veto')
        for marker in proof['spike_elf']['pass_markers']:require(text.count(marker)==1,'Missing exact marker '+marker)
        for p,h in pins.items():require(sha(__import__('pathlib').Path(p))==h,'Post-reference drift')
        save(out/'result.json',dict(**result,elapsed_s=elapsed,returncode=r.returncode,raw_sha256=sha(out/'commits.log'),raw_bytes=(out/'commits.log').stat().st_size,actual_isa=ISA))
        print('REFERENCE_EXECUTOR_PASS_PENDING_INDEPENDENT_REVIEW_NOT_DUT',result['firmware_retired_to_exit'])
    except BaseException as e:
        save(out/'not_accepted.json',dict(status='REFERENCE_NOT_ACCEPTED_NO_RETRY',error=repr(e),elapsed_s=time.monotonic()-t));raise
if __name__=='__main__':main()
