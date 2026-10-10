"""Prepare frozen721 R2 old-image command; separate parent authorization required to run."""
import argparse
import json
from pathlib import Path
import subprocess

import build_memory_emul_r2_preflight as preflight

life, require = preflight.life, preflight.require
PRE = life.OUT/'memory-emul-r2-preflight-721-20261006-01'
BUDGET = 1200


def validate(pre):
    require(pre['status']==preflight.STATUS and pre['case']==preflight.NAME and pre['baseline_tests']==721 and
            not pre['vcs_started'] and not pre['rtl_changed'] and not pre['coverage_admitted'],'R2 contract differs')
    v=pre['validation']
    for k,n in dict(checks=4229,snapshots=7,illegal_traps=3,handler_store_words=39,observed_vrf_bytes=28672,
                   vrf_guard_bytes=3584,memory_buffer_bytes=864,vector_write_instructions=35,illegal_vector_writes=0,
                   VILL_diagnostics_not_lower_EMUL_evidence=2,valid_vtype_EMUL_overflow_rejection=1).items():
        require(v[k]==n,'Full R2 oracle gate differs: '+k)
    require(v['actual_prefault_vtypes']==preflight.VTYPES and v['actual_prefault_vls']==preflight.VLS and
            v['legal_EMUL_boundaries']==['1/8','8'] and v['context_restored'] is True,'R2 actual config differs')
    require(pre['reference_counts']['matched_instructions']==218111 and pre['symbols']['tohost']==0x80001000 and
            pre['input_elf']==str(PRE/'input.elf') and pre['old_image_files_checked']==66 and
            pre['lower_EMUL_targets_qualified'] is False,'Image/ELF/lower-HOLD differs')
    bits=json.loads((preflight.BASE/'combined-bits.json').read_text())
    original=life.read_bound(preflight.old.REVIEW,preflight.old.REVIEW_SEAL)
    require(pre['targets']==preflight.reconcile(bits,original['candidates'][1]['zero_targets']), '721 exact targets differ')


def command(out):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
            '+PRELOAD='+str(PRE/'input.elf'),'+TESTCASE='+preflight.NAME,'+COMMIT_TOHOST=80001000',
            '+COMMIT_TRACE='+str(out/'commit_trace.csv'),'+VECTOR_TRACE='+str(out/'vector_trace.csv'),
            '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(out/'code.vdb'),'-cm_name',preflight.NAME]


def prepare(out,seal):
    out=out.absolute();require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh run directory required')
    pre=life.read_bound(PRE/'preflight-manifest.json',seal);validate(pre);life.check(pre['pins'])
    plan=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(plan['simv']==str(life.IMAGE) and len(plan['image'])==66 and plan['image'][str(life.IMAGE)]==
            '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3','Frozen simv66 differs')
    pins=life.merge_pins(pre['pins'],plan['image'])
    paths=[Path(__file__).resolve(),Path(__file__).with_name('test_run_memory_emul_r2_simulation.py')]
    pins=life.merge_pins(pins,{str(PRE/'preflight-manifest.json'):seal,str(life.PLAN):life.PLAN_SEAL})
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in paths});life.check(pins)
    return out,dict(case=preflight.NAME,preflight=str(PRE/'preflight-manifest.json'),preflight_seal=seal,
                   output=str(out),command=command(out),pins=pins,timeout_s=BUDGET,baseline_tests=721,
                   targets=pre['targets'],old_image_files_checked=66,scalar_reference_instructions=218111,
                   lower_targets_status='HOLD_NOT_QUALIFIED',upper_targets=[['line',1308],['branch',362]],
                   authorization_source='SEPARATE_PARENT_AGENT_REVIEW_REQUIRED_BEFORE_RUN',
                   coverage_admitted=False,admission_performed=False,rtl_changed=False,new_RTL_signoff=False)


def run(out,manifest):
    require(manifest['timeout_s']==BUDGET,'Budget drift');life.check(manifest['pins'])
    out.mkdir();life.save(out/'manifest.json',manifest)
    try:
        with (out/'console.log').open('x') as log:
            result=subprocess.run(manifest['command'],cwd=out,stdout=log,stderr=subprocess.STDOUT,
                                  timeout=manifest['timeout_s'],check=True)
        life.check(manifest['pins'])
        life.save(out/'simulation-status.json',dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=result.returncode,
                  case=preflight.NAME,coverage_admitted=False,admission_performed=False))
    except Exception as error:
        drift=None
        try:life.check(manifest['pins'])
        except Exception as e:drift=str(e)
        life.save(out/'simulation-status.json',dict(status='SIMULATION_FAILED_OR_TIMEOUT_NOT_ADMITTED',
                  reason=type(error).__name__+': '+str(error),post_failure_pin_error=drift,
                  case=preflight.NAME,coverage_admitted=False,admission_performed=False))
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','verify','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--preflight-seal',required=True)
    p.add_argument('--prepared-seal');a=p.parse_args();require((a.mode!='prepare')==bool(a.prepared_seal),'Fixed prepared seal required')
    out,manifest=prepare(a.output,a.preflight_seal);record=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':
        life.save(record,manifest);print(json.dumps(dict(prepared=str(record),seal=life.digest(record),pins=len(manifest['pins']),timeout_s=BUDGET)))
    else:
        require(life.read_bound(record,a.prepared_seal)==manifest,'Prepared command/pins drift')
        if a.mode=='verify':print('VERIFY_PASS R2/simv66/721/1200wall/lowerHOLD NO_VCS admitted0')
        else:run(out,manifest)


if __name__=='__main__':main()
