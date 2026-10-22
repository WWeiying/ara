"""Prepare and verify cached R1 old-image runner; run needs separate parent review."""
import argparse
import json
from pathlib import Path
import subprocess

import build_narrow_reject_r1_cached_preflight as preflight

life, require = preflight.life, preflight.require
PRE = life.OUT / 'narrow-reject-r1-cached-preflight-719-20261006-01'
BUDGET = 1800


def validate(pre):
    require(pre['status']==preflight.STATUS and pre['case']==preflight.NAME and pre['baseline_tests']==719 and
            not pre['vcs_started'] and not pre['rtl_changed'] and not pre['coverage_admitted'], 'Cached preflight contract')
    v=pre['validation']
    for k,n in dict(checks=15489,illegal_traps=24,trap_vstart=1,post_mret_vstart=1,handler_store_words=312,
                   observed_vrf_bytes=106496,guard_bytes=13312,vector_write_instructions=33,illegal_vector_writes=0).items():
        require(v[k]==n,'Required full oracle gate differs: '+k)
    require(pre['instruction_reduction']['new']==pre['reference_counts']['matched_instructions'] and
            pre['instruction_reduction']['new']<1049731,'No measured cached reduction')
    require(pre['symbols']['tohost']==0x80001000 and pre['input_elf']==str(PRE/'input.elf') and
            pre['old_image_files_checked']==66 and len(pre['targets'])==45,'Input/target binding differs')
    old=life.read_bound(preflight.OLD/'preflight-manifest.json',preflight.OLD_SEAL)
    require(pre['targets']==old['targets'],'719 native compiled target identity differs')


def command(out):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
        '+PRELOAD='+str(PRE/'input.elf'),'+TESTCASE='+preflight.NAME,'+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(out/'commit_trace.csv'),'+VECTOR_TRACE='+str(out/'vector_trace.csv'),
        '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(out/'code.vdb'),'-cm_name',preflight.NAME]


def prepare(out,seal):
    out=out.absolute()
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh independent run output required')
    pre=life.read_bound(PRE/'preflight-manifest.json',seal);validate(pre);life.check(pre['pins'])
    plan=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(plan['simv']==str(life.IMAGE) and len(plan['image'])==66 and plan['image'][str(life.IMAGE)]==
        '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3','Frozen simv66 differs')
    pins=life.merge_pins(pre['pins'],plan['image'])
    pins=life.merge_pins(pins,{str(PRE/'preflight-manifest.json'):seal,str(life.PLAN):life.PLAN_SEAL,
        str(Path(__file__).resolve()):life.digest(Path(__file__).resolve()),
        str(Path(__file__).with_name('test_run_narrow_reject_r1_cached_simulation.py')):
            life.digest(Path(__file__).with_name('test_run_narrow_reject_r1_cached_simulation.py'))})
    life.check(pins)
    return out,dict(case=preflight.NAME,preflight=str(PRE/'preflight-manifest.json'),preflight_seal=seal,
        output=str(out),command=command(out),pins=pins,timeout_s=BUDGET,baseline_tests=719,targets=pre['targets'],
        authorization_source='SEPARATE_PARENT_AGENT_REVIEW_REQUIRED_BEFORE_RUN',old_image_files_checked=66,
        scalar_reference_instructions=pre['reference_counts']['matched_instructions'],coverage_admitted=False,
        admission_performed=False,rtl_changed=False,new_RTL_signoff=False,dut_self_check_verified=False)


def run(out,manifest):
    require(manifest['timeout_s']==1800,'Wall budget differs');life.check(manifest['pins'])
    out.mkdir();life.save(out/'manifest.json',manifest)
    try:
        with (out/'console.log').open('x') as log:
            result=subprocess.run(manifest['command'],cwd=out,stdout=log,stderr=subprocess.STDOUT,
                                  timeout=manifest['timeout_s'],check=True)
        life.check(manifest['pins'])
        life.save(out/'simulation-status.json',dict(status='SIMULATION_EXITED_NOT_ADMITTED',
            returncode=result.returncode,case=preflight.NAME,coverage_admitted=False,admission_performed=False))
    except Exception as error:
        drift=None
        try:life.check(manifest['pins'])
        except Exception as e:drift=str(e)
        life.save(out/'simulation-status.json',dict(status='SIMULATION_FAILED_OR_TIMEOUT_NOT_ADMITTED',
            reason=type(error).__name__+': '+str(error),post_failure_pin_error=drift,
            case=preflight.NAME,coverage_admitted=False,admission_performed=False))
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','verify','run'));p.add_argument('--output',type=Path,required=True)
    p.add_argument('--preflight-seal',required=True);p.add_argument('--prepared-seal');a=p.parse_args()
    require((a.mode!='prepare')==bool(a.prepared_seal),'Replay requires prepared seal')
    out,manifest=prepare(a.output,a.preflight_seal);record=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':
        life.save(record,manifest);print(json.dumps(dict(status='RUN_PREPARED_NO_VCS',prepared=str(record),
            seal=life.digest(record),pins=len(manifest['pins']),timeout_s=BUDGET)))
    else:
        require(life.read_bound(record,a.prepared_seal)==manifest,'Prepared runner changed')
        if a.mode=='verify':print('VERIFY_PASS cached R1/simv66/719targets/pins/1800wall NO_VCS admitted0')
        else:run(out,manifest)


if __name__=='__main__':main()
