#!/usr/bin/env python3
import json
from pathlib import Path
import subprocess
import sys
import time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import model as m
import prepare as p
import checker02 as checker

OUT=HERE/'fullparse02'
REF=HERE.parent/'reference01'

def verify(pins):
    for f,h in pins.items():m.require(m.sha(f)==h,'Input drift '+f)

def child():
    pins=json.loads((OUT/'input_pins.json').read_text());verify(pins)
    result=checker.analyze(REF/'spike.trace',p.OUT)
    exe=json.loads((REF/'execution.json').read_text())
    m.require(exe['returncode']==result['source_exit']==77 and not exe['timeout'],'Actual reference wait/HTIF/capability')
    m.require(result['firmware_commits']<8000000,'Original fixed reference instruction ceiling')
    verify(pins);result.update(execution=exe,pins_unchanged=True,raw_sha256=pins[str(REF/'spike.trace')])
    p.save(OUT/'result.json',result)
    print(json.dumps({k:result[k] for k in ('status','firmware_commits','cases','numerical','capability','oracle_bytes')}))

def run():
    m.require(not OUT.exists(),'No automatic reparse/error retry')
    host=json.loads((HERE/'host.stdout').read_text())
    host_exit=json.loads((HERE/'host.stdout.execution.json').read_text())
    m.require(host['status']=='HOST_SPILL_GUARD_PASS' and host['negatives']==12 and
              host_exit['returncode']==0 and not host_exit['timeout'],'Actual correction Host gate')
    fault_host=json.loads((HERE/'fault_host.stdout').read_text())
    fault_exit=json.loads((HERE/'fault_host.stdout.execution.json').read_text())
    m.require(fault_host['status']=='HOST_FAULT_STATUS_PASS' and fault_exit['returncode']==0, 'Fault status Host gate')
    pins=json.loads((REF/'input_pins.json').read_text());verify(pins)
    for f in [REF/'spike.trace',REF/'execution.json',REF/'audit.log',REF/'audit_wait.json',REF/'not_completed.json',
              *HERE.glob('*.py'),HERE/'ROOT.md',HERE/'ROOT02.md',HERE/'fault_host.stdout',HERE/'fault_host.stdout.execution.json',HERE/'host.stdout',HERE/'host.stdout.execution.json']:
        pins[str(f)]=m.sha(f)
    OUT.mkdir();p.save(OUT/'input_pins.json',pins)
    start=time.monotonic();timed=False
    with (OUT/'audit.log').open('x') as f:
        proc=subprocess.Popen([sys.executable,'-B',str(HERE/'audit02.py'),'child'],stdout=f,stderr=subprocess.STDOUT)
        try:rc=proc.wait(timeout=600)
        except subprocess.TimeoutExpired:timed=True;proc.kill();rc=proc.wait()
    p.save(OUT/'actual_wait.json',dict(returncode=rc,timeout=timed,elapsed_s=time.monotonic()-start))
    print(json.dumps(dict(returncode=rc,timeout=timed)))
    return int(rc!=0 or timed)

if __name__=='__main__':
    if sys.argv[1:] == ['child']:child()
    elif not sys.argv[1:]:raise SystemExit(run())
    else:raise SystemExit('No other modes')
