#!/usr/bin/env python3
"""Seal completed references and exact SoC program manifest; no simulator launch."""
import sys
from pathlib import Path
sys.dont_write_bytecode=True
from scope import HERE,read,save,sha,verify,require,inventory
import model

def main():
    require(not (HERE/'READY.json').exists(),'New seal only')
    inv=read(HERE/'source_manifest.json');require(inv==inventory(),'Source inventory drift')
    batch=read(HERE/'reference_batch.json')
    require(batch['status']=='PASS_REFERENCE9_NOT_DUT' and len(batch['results'])==9 and
            all(r['returncode']==0 for r in batch['results']) and batch['not_dispatched']==[],
            'Nine original references not complete')
    host=read(HERE/'host01/status.json');require(host['status']=='PASS_HOST_ONLY','Shared Host not PASS')
    verify(host['pins']);pins={**inv['pins'],**host['pins']};programs={};groups=[]
    for group in inv['groups']:
        root=HERE/group['id'];out=root/'reference02';model.configure(group['cases'])
        result=read(out/'status.json');proof=read(out/'source_proof.json')
        require(result['status']=='HOST_SPIKE_PASS_NOT_DUT' and result['process_returncode']==0 and
                result['cases']==list(model.NAMES) and result['checks']==model.TOTAL and
                result['case_checks']==list(model.COUNTS) and result['commits']<3000000,
                'Wrong reference completion/scope')
        input_pins=read(out/'input_pins.json');verify(input_pins);pins.update(input_pins)
        require(result['raw_sha256']==sha(out/'spike.trace'),'Raw trace drift')
        entry=proof['elfs']['soc'];require(entry['sha256']==sha(entry['path']),'Exact SoC ELF drift')
        programs[group['runtime_id']]=dict(path=entry['path'],sha256=entry['sha256'],
            runtime_name=group['runtime_id'],historical_names=[c['historical_name'] for c in group['cases']],
            original_case_sha256=[c['case_sha256'] for c in group['cases']],
            pass_markers=['NF2_REMAINING34_SV39_PASS'],checks=model.TOTAL,MX_N=model.N)
        groups.append(dict(id=group['id'],cases=list(model.NAMES),MX_N=model.N,
            parsed_spike_records=result['commits'],checks=result['checks'],reference_elapsed_s=result['reference_elapsed_s'],
            soc_elf=entry,raw_sha256=result['raw_sha256'],static_steps=read(out/'bound.json')['static_steps']))
        for p in root.rglob('*'):
            if p.is_file():pins[str(p)]=sha(p)
    require(sum(g['MX_N'] for g in groups)==34 and len(programs)==9,'Exact34/nine groups')
    save(HERE/'programs.json',dict(schema_version=1,backend='vcs-soc',programs=programs,
        scope='SOURCE_REFERENCE_ONLY_NOT_DUT',M6_admission_requires_pilot_pass_and_new_parent_review=True))
    for p in HERE.iterdir():
        if p.is_file() and p.name!='READY.json':pins[str(p)]=sha(p)
    for p in (HERE/'host01').rglob('*'):
        if p.is_file():pins[str(p)]=sha(p)
    verify(pins)
    save(HERE/'READY.json',dict(status='REFERENCE9_PASS_34_SOURCE_SINGLES_PENDING_INDEPENDENT_REVIEW_NOT_DUT',
        pins=pins,groups=groups,archive_distinct=40,excluded_J2=inv['excluded_J2'],excluded_pilot4=inv['excluded_pilot4'],
        exclusion_versions=inv['exclusion_versions'],current_M6_J2_accepted=False,
        current_M6_40_closure=False,reference_executions=9,host_executions=1,
        per_case_full_outputs=128,per_case_output_guards=2,per_case_fullmemory_bytes=8192,
        group_dimensions=[g['MX_N'] for g in groups],VCS_started=False,RTL_build=False,
        Linux_signalframe_proved=False,current_pilot_status='NOT_QUERIED'))
    print('SEALED_REFERENCE_ONLY',sha(HERE/'READY.json'),len(pins))

if __name__=='__main__':main()
