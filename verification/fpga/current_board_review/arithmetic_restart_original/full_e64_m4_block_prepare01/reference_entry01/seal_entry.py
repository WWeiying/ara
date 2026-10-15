"""Seal exact one-attempt reference entry after small Host succeeds."""
from context import *

def main():
    require(not (HERE/'entry.json').exists(),'One exact entry seal')
    review=A/'e64_m4_source_review01/SOFTWARE02_ARTIFACT_REVIEW.md'
    require(sha(review)=='f0ce4352e238ddd7d7e0a6005a9e618e7b1952a7178c23bc63e7e3095c19d7c1','Actual independent artifact review')
    actual=read(HERE.parent/'compiled_audit03/RESULT.json')
    require(actual['all_equal_whole_CFG_upper']==2863981 and actual['pins_unchanged'],'Actual same-ELF CFG')
    host=read(HERE/'host03_receipt.json')
    require(type(host['actual_wait_exit']) is int and host['actual_wait_exit']==0 and not host['timed_out'] and host['input_pins_unchanged'],'Actual Host03 exit')
    for p,h in host['input_pins'].items():require(sha(p)==h,'Actual tested successor source '+p)
    require('Ran 26 tests' in (HERE/'host03.log').read_text() and (HERE/'host03.log').read_text().rstrip().endswith('OK'),'19 retained plus7 phase-order tests')
    pins=read(SOFT/'pins.json')
    for p,h in pins.items():require(sha(p)==h,'Unchanged software/source '+p)
    for backend in ('soc','spike'):
        spec=definition(backend);require(sha(spec['elf'])==spec['elf_sha256'],'Actual backend ELF pin')
    require(definition()['elf_sha256']=='42e53dc666391e88db7c2d436f7972cda362b575ca9e26806110841fecce51ae','Approved reference ELF')
    for p in [review,HERE.parent/'compiled_audit03/inspect.py',HERE.parent/'compiled_audit01/inspect.py',
              HERE.parent/'compiled_audit03/RESULT.json',HERE.parent/'compiled_audit03/execution_receipt.json',
              SOFT/'execution_receipt.json',SOFT/'pins.json',SOFT/'proof.json',
              Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')]:pins[str(p)]=sha(p)
    for p in HERE.rglob('*'):
        if p.is_file() and p.suffix!='.pyc':pins[str(p)]=sha(p)
    save(HERE/'entry.json',dict(status='SEALED_PENDING_EXACT_INDEPENDENT_ENTRY_REVIEW_NOT_EXECUTED',
        scope=dict(SEW=64,LMUL='m4',CAP=64,vtype=26,calls=5985,ops=35,seeds=3,results=383040,guards=11970,
            returned_vstart=5985,helper_instructions=77805,physical_registers=4,output_bytes=528,actual_LD=395010,
            expected_LD=395010,ID_LHU=53865,sticky_equal_BEQ=395010,FP_calls=1890,FP_SD=241920,mask_SD=35280,mask_SB=77175),
        limits=dict(rs=4000000,quit=True,reference_wall_s=120,raw_bytes=768*1024**2,offline_wall_s=600,firmware_target=3000000),
        profile='rv64gcv_zvl1024b',one_attempt=True,no_retry=True,DUT_authorized=False,source_reference_only=True,pins=pins))
    print(sha(HERE/'entry.json'),len(pins),flush=True)
if __name__=='__main__':main()
