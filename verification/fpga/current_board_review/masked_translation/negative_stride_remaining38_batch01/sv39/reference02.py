#!/usr/bin/env python3
"""Reuse the first raw capture offline; run each still-unrun group exactly once."""
import json
import sys
import time
from pathlib import Path
sys.dont_write_bytecode=True
import prepare_sv39 as p

if __name__=='__main__':
    r=p.HERE/'reference02';p.require(not r.exists(),'Fresh successor only')
    pins={**p.read(p.OUT/'input_pins.json'),**p.read(p.OUT/'artifact_pins.json')}
    p.verify(pins)
    for n in ('checker02.py','check_reference02.py','test_checker02.py','reference02.py'):
        pins[str(p.HERE/n)]=p.sha(p.HERE/n)
    old=p.HERE/'reference01/group00'
    wait=p.read(old/'spike.stdout.wait.json')
    p.require(type(wait['actual_wait_returncode']) is int and wait['actual_wait_returncode']==0 and not wait['timeout'],'Actual first Spike outcome')
    p.require(wait['command'][-1]==str(p.OUT/'group00/spike.elf'),'Original first ELF')
    for n in ('spike.trace','spike.stdout.wait.json','parser.stdout','parser.stdout.wait.json'):
        pins[str(old/n)]=p.sha(old/n)
    r.mkdir();p.save(r/'input_pins.json',pins)
    results=[]
    try:
        p.execute([sys.executable,'-B',p.HERE/'test_checker02.py'],r/'host.log',60)
        for group in p.read(p.OUT/'built.json')['groups']:
            label=group['group'];d=p.OUT/label;o=r/label;o.mkdir()
            if label=='group00':
                raw=old/'spike.trace';execution=wait
                p.save(o/'reused.json',dict(original_raw=str(raw),sha256=p.sha(raw),actual_spike_wait=str(old/'spike.stdout.wait.json'),no_reference_rerun=True))
            else:
                raw=o/'spike.trace'
                cmd=[p.SPIKE,'--isa='+p.ISA,'--priv=msu','--pmpregions=0','-m2',f'--instructions={p.LIMIT}','-l','--log-commits',d/'spike.elf']
                p.save(o/'attempt.json',dict(command=list(map(str,cmd)),started=time.time(),attempt=1,instruction_limit=p.LIMIT,timeout_s=180,raw_limit_bytes=1024**3))
                execution=p.execute(cmd,o/'spike.stdout',180,raw,1024**3)
            parse=p.execute([sys.executable,'-B',p.HERE/'check_reference02.py',d,raw,o],o/'parser.stdout',900)
            p.verify(pins);status=p.read(o/'status.json')
            p.save(o/'complete.json',dict(status='REFERENCE_ACCEPTED_NOT_DUT',spike_actual_wait=execution['actual_wait_returncode'],
                parser_actual_wait=parse['actual_wait_returncode'],result_sha256=p.sha(o/'status.json'),
                raw=str(raw),raw_sha256=p.sha(raw),raw_bytes=raw.stat().st_size,pins_unchanged=True))
            results.append(dict(group=label,cases=status['case_count'],firmware_records=status['firmware_records_through_htif'],
                scalar_checks=status['scalar_checks'],spike_elapsed_s=execution['elapsed_s'],parser_elapsed_s=parse['elapsed_s'],
                conservative_m6_estimate_s=status['firmware_records_through_htif']/(858371/1111.6245557051152)*1.2))
            print(json.dumps(results[-1]),flush=True)
        p.verify(pins);p.require(sum(g['cases'] for g in results)==38,'Exact38')
        p.save(r/'complete.json',dict(status='REFERENCE_38_PASS_NOT_DUT',groups=results,pins_unchanged=True,no_dut=True))
        p.save(r/'artifact_pins.json',{str(f):p.sha(f) for f in r.rglob('*') if f.is_file()})
    except BaseException as e:
        p.save(r/'NOT_ACCEPTED.json',dict(status='REFERENCE_INCOMPLETE_STOP_NO_RETRY',error=f'{type(e).__name__}: {e}',completed_groups=results))
        raise
