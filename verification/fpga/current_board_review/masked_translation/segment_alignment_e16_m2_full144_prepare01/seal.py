#!/usr/bin/env python3
"""Freeze actual full144 preparation only after successful offline completion."""
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
import model as m
from prepare import save

def main():
    h=m.HERE;out=h/'software01';audit=h/'recovery01/fullparse02'
    require=m.require
    require(not (h/'READY.json').exists(),'Do not overwrite preparation seal')
    result=json.loads((audit/'result.json').read_text())
    wait=json.loads((audit/'actual_wait.json').read_text())
    execution=json.loads((h/'reference01/execution.json').read_text())
    host=json.loads((out/'host.json').read_text())
    require(wait['returncode']==0 and not wait['timeout'],'Actual offline wait0 required')
    require(result['status']=='REFERENCE_FULL144_CAPABILITY_COMPLETE' and result['cases']==144 and
            result['numerical']==120 and result['capability']==24 and result['no_active']==96 and
            result['oracle_bytes']==120*8192 and result['helpers']==list(range(144)) and
            result['checkpoints']==288 and result['pins_unchanged'],'Full original capability contract')
    require(execution['returncode']==77 and not execution['timeout'] and execution['elapsed_s']<120,
            'Actual reference capability return77, not numeric0')
    require(host['cases']==144 and host['negative_checks']==7776,'Actual complete Host gate')
    pins=json.loads((audit/'input_pins.json').read_text())
    for f,digest in pins.items():require(m.sha(f)==digest,'Preparation input drift '+f)
    for f in h.rglob('*'):
        if f.is_file() and '__pycache__' not in f.parts and f.name not in ('READY.json','evidence_pins.json'):
            pins[str(f)]=m.sha(f)
    save(h/'evidence_pins.json',pins)
    rate_zero=2165648/3143.888;rate_store=851704/1111.624555705
    cost=result['firmware_commits']
    ready=dict(status='FULL144_SOURCE_REFERENCE_CAPABILITY_READY_PENDING_INDEPENDENT_REVIEW_NOT_DUT',
        cases=144,original_name=m.NAME,scope='Complete original e16/m2 alignment configurations; scalar-cost-optimized Sv39 source port',
        original_linux_accepted=False,linux_clone_COW_signal_reproduced=False,original_historical_tuple_known=False,
        source_proof=str(out/'source_proof.json'),source_proof_sha256=m.sha(out/'source_proof.json'),
        host=str(out/'host.json'),host_sha256=m.sha(out/'host.json'),host_negative_checks=7776,
        soc_elf=str(out/'soc.elf'),soc_elf_sha256=m.sha(out/'soc.elf'),
        spike_elf=str(out/'spike.elf'),spike_elf_sha256=m.sha(out/'spike.elf'),reference_attempts=1,
        reference_actual_exit=77,reference_elapsed_s=execution['elapsed_s'],
        reference_raw_sha256=m.sha(h/'reference01/spike.trace'),reference_raw_bytes=execution['raw_bytes'],
        actual_audit_exit=0,actual_audit_elapsed_s=wait['elapsed_s'],
        result=str(audit/'result.json'),result_sha256=m.sha(audit/'result.json'),
        numerical_cases=120,allowed_capability_cases=24,no_active_numerical_cases=96,
        original_numerical_bytes=120*8192,initialized_bytes=144*4*8192,predicate_bytes=144*128,
        firmware_commit_status_records=cost,fault_partial_status_records=len(result['fault_partial_status_rows']),
        budget_estimates=dict(proxy_zero16_records_per_s=rate_zero,proxy_negative_store_records_per_s=rate_store,
            at_zero16_with20pct_s=cost/rate_zero*1.2,at_negative_store_with20pct_s=cost/rate_store*1.2,
            slower273_with20pct_s=cost/273*1.2,guarantee=False,
            observer_time_is_additional=True,M8_DUT_admission=False),
        pins=len(pins),evidence_pins=str(h/'evidence_pins.json'),evidence_pins_sha256=m.sha(h/'evidence_pins.json'),
        first_checker_failures_preserved=True,RTL_changed=False,DUT_started=False)
    save(h/'READY.json',ready)
    print(json.dumps({k:ready[k] for k in ('status','cases','reference_actual_exit','numerical_cases','allowed_capability_cases',
                                         'firmware_commit_status_records','budget_estimates','pins')}))
    print('READY_SHA256',m.sha(h/'READY.json'))

if __name__=='__main__':main()
