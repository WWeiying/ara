#!/usr/bin/env python3
"""Freeze completed software and reference入口 without executing a reference."""
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
import prepare as p
HERE=Path(__file__).resolve().parent

def main():
    pins=json.loads((HERE/'pins.json').read_text())
    for name,digest in pins.items():p.old.require(p.sha(Path(name))==digest,'Prepared drift '+name)
    receipt=json.loads((HERE/'host_entry_receipt.json').read_text())
    p.old.require(receipt['prepare_actual_exit_code']==receipt['entry_test_actual_exit_code']==0,'Actual Host exit')
    for variant in ('host_original','host_packed'):
        for mutation in range(9):
            exitdata=json.loads((HERE/variant/f'case{mutation}.log.exit.json').read_text())
            expected=-4 if mutation==8 else 0 if mutation==0 else 1
            p.old.require(type(exitdata['returncode']) is int and exitdata['returncode']==expected,'Full Host receipt')
    for path in HERE.rglob('*'):
        if path.is_file() and path.suffix!='.pyc':pins[str(path)]=p.sha(path)
    for path in (Path(sys.executable).resolve(),Path('/usr/bin/cc').resolve(),
                 p.old.CC.with_name('riscv64-unknown-elf-objdump'),p.old.CC.with_name('riscv64-unknown-elf-nm'),
                 HERE.parent/'m8_block64_feasibility01/host_result01.json'):
        pins[str(path)]=p.sha(path)
    for module in list(sys.modules.values()):
        name=getattr(module,'__file__',None)
        if name and str(HERE.parent.parent) in name and Path(name).is_file():pins[str(Path(name).resolve())]=p.sha(Path(name))
    entry=dict(status='HOST_COMPILED_CODE_REVIEW_READY_PENDING_INDEPENDENT_REFERENCE_ENTRY',
        pins=pins,pin_count=len(pins),proof_sha256=p.sha(HERE/'proof.json'),
        software_status_sha256=p.sha(HERE/'software_status.json'),source_pins_sha256=p.sha(HERE/'pins.json'),
        scope=dict(shape='e8_m8',cap=1024,calls=4095,results=4193280,guards=8190,vstarts=4095,helper_instructions=53235),
        bounds=dict(hard_steps=4000000,host_seconds=120,raw_file_bytes=768*1024**2,cost_target=3000000,
                    attempts=1,DUT_authorized=False),
        independent_review_schema=dict(status='NO_BLOCKER_SOURCE_SOFTWARE_FOR_ONE_BOUNDED_REFERENCE_NOT_DUT',
            entry_sha256='actual SHA of this entry.json',one_attempt=True,DUT_authorized=False),
        invocation='python3 -B reference.py execute --review ABSOLUTE_REVIEW_JSON --review-sha ACTUAL_REVIEW_SHA')
    p.save(HERE/'entry.json',entry)
    print(json.dumps(dict(entry=str(HERE/'entry.json'),sha256=p.sha(HERE/'entry.json'),pin_count=len(pins))))

if __name__=='__main__':main()
