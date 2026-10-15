#!/usr/bin/env python3
"""Prepare actual linked reference spec and bounded checker-only Host tests."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def require(ok,msg):
    if not ok:raise ValueError(msg)
def main():
    require(not (HERE/'spec.json').exists(),'One fresh entry preparation')
    review=ROOT.parent/'fp_compare_unboxed_full17920_source_review01/COMPILED_REVIEW01.json'
    require(sha(review)=='12b54242c48aa088ae3211ff902b125dcb49a99604ab4b64775bdc7377ddd753','Actual compiled review')
    modspec=importlib.util.spec_from_file_location('linked_inspect',ROOT/'compile01/inspect_linked.py')
    mod=importlib.util.module_from_spec(modspec);modspec.loader.exec_module(mod)
    d,code,func,symbols,sizes=mod.parse('spike')
    require(sha(d/'program.elf')=='0ecbd714c95e1aed2b1a6586cebdd7953e090d2da6d8c6521ee1101c2aec9671','Actual Spike ELF')
    lower=json.loads((ROOT/'compile01/linked_audit02/spike.json').read_text())
    bss_start=symbols['__bss_start'];bss_end=symbols['__bss_end']
    opaque=[]
    for name in (mod.NAME,'main'):
        for row in func[name]:
            if row['op']=='jal':break
            if row['op']=='sd' and '(sp)' in row['args'] and row['args'].split(',')[0] not in ('ra','zero'):
                opaque.append(row['pc'])
    failures=[]
    for lo,hi in [(0x80000054,0x80000064),(0x80000108,0x80000114),(0x800002ae,0x80000368),
                  (0x80000386,0x8000038e),(0x80000422,0x80000426),(0x8000073c,0x80000748),
                  (0x8000076a,0x80000778),(0x80000828,0x8000083c)]:
        failures.extend(p for p in code if lo<=p<=hi)
    spec=dict(elf=str(d/'program.elf'),elf_sha256=sha(d/'program.elf'),symbols=symbols,sizes=sizes,
              code=code,helpers=[func['op_'+str(i)] for i in range(10)],capacity=func['capacity'],
              stores=lower['fresh_store_sites'],input_loads=lower['input_LD_sites'],
              record_load=0x800003c8,output_read=0x80000244,exit_store=0x8000007a,park=0x8000007e,
              prelude=[0x80000010,0x8000001c,0x80000026,0x8000002a,0x8000002e,0x80000730],
              opaque_initial_spills=opaque,failure_pcs=failures,BSS_bytes=bss_end-bss_start)
    from checker import elf_image,word,DECODER
    image=elf_image(d/'program.elf')
    for pc,row in code.items():require(word(image,pc,len(row['insn'])//2)==int(row['insn'],16),'Actual ELF code bytes')
    save(HERE/'spec.json',spec)
    pins={}
    for p,h in json.loads((ROOT/'compile01/linked_audit02/inputs_after.json').read_text()).items():
        require(sha(Path(p))==h,'Compiled input drift '+p);pins[p]=h
    for p,h in json.loads((ROOT/'source_model02/artifact_pins.json').read_text()).items():
        require(sha(Path(p))==h,'Source model drift '+p);pins[p]=h
    for p in [review,ROOT/'compile01/inspect_linked.py',DECODER,HERE/'spec.json',*HERE.glob('*.py')]:pins[str(p)]=sha(p)
    spike=Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
    pins[str(spike)]=sha(spike)
    save(HERE/'input_pins.json',pins)
    command=[sys.executable,'-B',str(HERE/'test_checker.py')]
    save(HERE/'host.command.json',command);t=time.monotonic()
    with (HERE/'host.log').open('x') as log:
        proc=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        try:rc=proc.wait(timeout=60);timed=False
        except subprocess.TimeoutExpired:proc.kill();rc=proc.wait();timed=True
    save(HERE/'host.wait.json',dict(actual_wait_exit=rc,timed_out=timed,elapsed_seconds=time.monotonic()-t,log_sha256=sha(HERE/'host.log')))
    require(rc==0 and not timed,'Checker Host failed; preserve and stop')
    require(all(sha(Path(p))==h for p,h in pins.items()),'Preparation input drift')
    save(HERE/'ENTRY.json',dict(status='PREPARED_PENDING_INDEPENDENT_ENTRY_NOT_EXECUTED',input_pins_sha256=sha(HERE/'input_pins.json'),
        spec_sha256=sha(HERE/'spec.json'),checker_sha256=sha(HERE/'checker.py'),host_wait_sha256=sha(HERE/'host.wait.json'),
        reference_executor_sha256=sha(HERE/'execute_once.py'),spike=str(spike),isa='rv64gcv_zfh_zvfh_zvl1024b',
        debug_command='rs 4000000\nquit\n',reference_seconds=120,raw_limit_bytes=768*1024*1024,audit_seconds=600,
        firmware_limit=3000000,unique_reference_attempt=True,unique_closed_raw_audit=True,retry=False,automatic_VCS=False,
        launch_gate='Aquinas independent ENTRY NO_BLOCKER pins exact ENTRY/input_pins; parent conditional authorization',
        command='python3 -B '+str(HERE/'execute_once.py')+' --review ACTUAL_REVIEW_JSON --review-sha256 ACTUAL_SHA'))
    print('ENTRY_PREPARED_CHECKER_HOST_PASS_NOT_EXECUTED')
if __name__=='__main__':main()
