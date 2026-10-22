"""Sealed same-ELF 180s old-image runner. Prepare/verify never launch EDA."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import check_narrow_source_group_preflight_v2 as preflight
import run_pure_war_simulation as frozen

p=preflight.prior
life,require=preflight.life,preflight.require
NAME='vnarrow_source_group_illegal'
PRE=life.OUT/'narrow-source-group-preflight-v2-735-agent-20261006-01'
PRE_SEAL='d811770781aa9e838782ae6cf0a043d8d7c3ac0625d761ffc3ba24e8b078a58f'
ELF=preflight.FAILED/'input.elf'
ELF_SHA='b483f1616d5abdc1ff6ed8f32ad56160802abcc5ca3eac06764b1918ba456913'
BUDGET=180
LIFECYCLE_SHA='2e7ded5ac7c1caeff20a0d1febbb7123dbd30973a9fdef0435ad051673e11626'


def verify_preflight():
    pre=life.read_bound(PRE/'preflight-manifest.json',PRE_SEAL)
    require(pre['status']=='SAME_ELF_SOFTWARE_PREFLIGHT_PASS_NOT_DUT_NOT_ADMITTED' and
            pre['input_elf']==str(ELF) and pre['elf_sha256']==ELF_SHA and
            pre['baseline']==735 and pre['baseline_seal']==p.BASE_SEAL and
            pre['rebuild_performed'] is False and pre['VCS_started'] is False and
            pre['coverage_admitted'] is False,'Exact sealed same-ELF preflight required')
    life.check(pre['pins']);require(life.digest(ELF)==ELF_SHA,'Sealed ELF drift')
    require(pre['targets']==life.read_bound(preflight.FAILED/'target-receipt.json',
            preflight.FAILED_PINS[str(preflight.FAILED/'target-receipt.json')])['targets'],
            'Exact compiled/source targets differ')
    require(all(type(row) is list and len(row)==2 and all(type(v) is int for v in row)
                for row in pre['explicit_RVV']),'Serialized RVV inventory differs')
    preflight.verify_words([tuple(row) for row in pre['explicit_RVV']],pre['symbols'])
    result=p.validate(p.shared.parse_spike_commits(PRE/'spike.trace'),pre['symbols'],(PRE/'spike.trace').read_text())
    require(result==pre['validation'] and result['checks']==2130,'Full software oracle replay differs')
    return pre


def command(out):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
        '+PRELOAD='+str(ELF),'+TESTCASE='+NAME,'+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(out/'commit_trace.csv'),'+VECTOR_TRACE='+str(out/'vector_trace.csv'),
        '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(out/'code.vdb'),'-cm_name',NAME]


def check_runtime_inputs(inputs):
    plan=life.read_bound(life.PLAN,life.PLAN_SEAL)
    runtime=plan['image']
    require(plan['simv']==str(life.IMAGE) and len(runtime)==66 and
            runtime.get(str(life.IMAGE))==p.prior.IMAGE_SHA and
            all(inputs.get(path)==sha for path,sha in runtime.items()),
            'Frozen image66 differs')


def manifest(out):
    require(out.parent==life.OUT and out.resolve()==out,'Direct run directory required')
    pre=verify_preflight();image=p.prior.image_inputs()
    check_runtime_inputs(image)
    require(life.digest(Path(frozen.__file__))==LIFECYCLE_SHA,'Frozen lifecycle drift')
    deps=(Path(__file__).resolve(),Path(__file__).with_name('test_run_narrow_source_group_simulation.py'))
    pins=life.merge_pins(pre['pins'],image)
    pins=life.merge_pins(pins,{str(x):life.digest(x) for x in deps})
    pins=life.merge_pins(pins,{str(PRE/'preflight-manifest.json'):PRE_SEAL,
                             str(Path(frozen.__file__).resolve()):LIFECYCLE_SHA})
    life.check(pins)
    return dict(case=NAME,output=str(out),preflight=str(PRE/'preflight-manifest.json'),preflight_seal=PRE_SEAL,
        input_elf=str(ELF),elf_sha256=ELF_SHA,image_sha256=p.prior.IMAGE_SHA,pins=pins,
        command=command(out),timeout_s=BUDGET,old_image_files_checked=66,software_checks=2130,
        exact_illegal_traps=1,targets=pre['targets'],static_baseline=735,
        raw_gain_requires_latest_formal_population_at_least=735,
        foreground_lifetime=True,automatic_retry=False,coverage_admitted=False,admission_performed=False,
        native_cycle_qualified=False,terminal_oracle_verified=False,
        qualification_required='Full scalar/vector/CSR/trap/memory; rejected instruction zero backend/VRF',
        systemd_policy=dict(RuntimeMaxSec=240,TimeoutStopSec=10,KillMode='control-group'))


def prepare(out):
    require(not out.exists(),'Fresh run required')
    return manifest(out)


def verify_prepared(out,record):
    require(record==manifest(out),'Prepared pins/command/fields drift')
    return verify_preflight()


def invoke_run(out,record):
    require(prepare(out)==record,'Reviewed execution drift')
    bindings=dict(PRE=ELF.parent,ELF_SEAL=ELF_SHA,BUDGET=BUDGET,
                  preflight=SimpleNamespace(NAME=NAME),command=command)
    previous={k:getattr(frozen,k) for k in bindings}
    try:
        for k,v in bindings.items():setattr(frozen,k,v)
        frozen.run(out,record)
    finally:
        for k,v in previous.items():setattr(frozen,k,v)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','verify','run'));parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--prepared-seal');parser.add_argument('--parent-authorized',action='store_true')
    a=parser.parse_args(argv)
    require((a.mode!='prepare')==bool(a.prepared_seal),'Verify/run need reviewed sidecar seal')
    require((a.mode=='run')==a.parent_authorized,'Explicit separate parent run authorization required')
    out=a.output.absolute();record=prepare(out);sidecar=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':
        require(not sidecar.exists(),'Fresh sidecar required');life.save(sidecar,record)
        print(json.dumps(dict(prepared=str(sidecar),seal=life.digest(sidecar),timeout_s=BUDGET,VCS_started=False)))
    else:
        require(life.read_bound(sidecar,a.prepared_seal)==record,'Reviewed sidecar drift')
        if a.mode=='run':invoke_run(out,record)
        else:print('VERIFY_PASS NO_VCS')


if __name__=='__main__':main()
