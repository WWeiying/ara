#!/usr/bin/env python3
import sys
sys.dont_write_bytecode=True
from software_prepare import HERE,sha,read,save
from model import require
def main():
    require(not (HERE/'READY.json').exists(),'Immutable READY')
    r=read(HERE/'reference01/result.json');proof=read(HERE/'source_elf_proof.json')
    require(r['status']=='PASS_RAW_ORIGINAL265_NOT_FULL_PARENT' and r['target_calls']==265,'Reference incomplete')
    baseline=read(HERE/'baseline_pins.json')
    for p,h in baseline.items():require(sha(__import__('pathlib').Path(p))==h,'Baseline drift')
    pins={str(p):sha(p) for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    save(HERE/'READY.json',dict(status='REFERENCE_EXECUTOR_PASS_PENDING_INDEPENDENT_REVIEW_NOT_DUT',
        scope=dict(calls=265,predecessors=264,capacity=16,result_bits=4240,guards=530,vstart=265,flags=265),
        baseline_pins=baseline,owned_pins=pins,soc_elf=proof['soc_elf'],spike_elf=proof['spike_elf'],
        actual_isa=r['actual_isa'],firmware_retired=701895,attempts=1,retries=0,
        target_encoding='62805c57',reference_sha256=sha(HERE/'reference01/result.json'),
        raw_sha256=r['raw_sha256'],dut_pass=False,full_parent_pass=False))
    print('SEALED_REFERENCE_PENDING_INDEPENDENT_REVIEW',sha(HERE/'READY.json'))
if __name__=='__main__':main()
