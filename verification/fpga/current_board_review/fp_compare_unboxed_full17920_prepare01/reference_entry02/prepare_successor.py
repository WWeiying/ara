#!/usr/bin/env python3
"""Narrow metadata gate successor; reuses unchanged22-test receipt, no reference."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;OLD=HERE.parent/'reference_entry01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def main():
    assert not (HERE/'ENTRY.json').exists() and not (HERE/'spec.json').exists()
    assert sha(OLD/'ENTRY.json')=='dc26b72f739b9170694379ccfc9bd525d309ed079faa5dd794380a600d65581a'
    pins=json.loads((OLD/'input_pins.json').read_text())
    for p,h in pins.items():assert sha(Path(p))==h,p
    for name in ('checker.py','audit_once.py','spec.json','host.wait.json','host.log','host.command.json','test_checker.py'):
        shutil.copyfile(OLD/name,HERE/name)
        pins[str(OLD/name)]=sha(OLD/name);pins[str(HERE/name)]=sha(HERE/name)
    entry=json.loads((OLD/'ENTRY.json').read_text())
    assert sha(HERE/'host.wait.json')==entry['host_wait_sha256']
    from execute_once import validate_host
    validate_host(entry,HERE/'host.wait.json',HERE/'host.log')
    command=[sys.executable,'-B',str(HERE/'test_gate.py')];save(HERE/'gate.command.json',command)
    t=time.monotonic()
    with (HERE/'gate.log').open('x') as log:
        p=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        try:rc=p.wait(timeout=30);timed=False
        except subprocess.TimeoutExpired:p.kill();rc=p.wait();timed=True
    save(HERE/'gate.wait.json',dict(actual_wait_exit=rc,timed_out=timed,elapsed_s=time.monotonic()-t,log_sha256=sha(HERE/'gate.log')))
    assert rc==0 and timed is False
    for p in [OLD/'ENTRY.json',OLD/'input_pins.json',*HERE.glob('*.py'),HERE/'gate.log',HERE/'gate.wait.json',HERE/'gate.command.json']:
        pins[str(p)]=sha(p)
    save(HERE/'input_pins.json',pins)
    entry.update(status='PREPARED_SUCCESSOR_HOST_RECEIPT_PIN_FIXED_PENDING_REVIEW',
                 input_pins_sha256=sha(HERE/'input_pins.json'),reference_executor_sha256=sha(HERE/'execute_once.py'),
                 inherited_host_receipt=str(OLD/'host.wait.json'),gate_wait_sha256=sha(HERE/'gate.wait.json'),
                 command='python3 -B '+str(HERE/'execute_once.py')+' --review ACTUAL_REVIEW_JSON --review-sha256 ACTUAL_SHA')
    save(HERE/'ENTRY.json',entry)
    print('SUCCESSOR_PREPARED_6_GATE_TESTS_PASS_REUSED22_NO_REFERENCE',sha(HERE/'ENTRY.json'))
if __name__=='__main__':main()
