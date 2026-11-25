#!/usr/bin/env python3
"""Independent offline recovery of a missing-ROI bookkeeping failure; no GLS."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time

OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
PARENT = OUT/'power_gls_20261117_long_m1_01'
FROZEN = OUT/'power_dc_20261117_q8_matmul_subwindow_03/native/inputs'


def module(path):
    spec = importlib.util.spec_from_file_location('m1_frozen_capture_audit',path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def prepare(out):
    assert out.parent == OUT and not out.exists(), 'Fresh audit output required'
    (out/'inputs').mkdir(parents=True)
    for name in ('q8_matmul_post_v1.py','dc_power.py','convert.py','reference-pair.json'):
        shutil.copyfile(FROZEN/name,out/'inputs'/name)
    shutil.copyfile(__file__,out/'inputs/m1_long_eof_audit_v1.py')
    m = module(out/'inputs/q8_matmul_post_v1.py')
    unit = out.name.replace('_','-')+'.service'
    m.save(out/'plan.json',dict(parent=str(PARENT),service_unit=unit,minimum_cycles=20000,
        no_compile_GLS_or_input_changes=True,audit_seconds=2400,automatic_retry=False))
    paths = [*(out/'inputs').iterdir(),out/'plan.json',PARENT/'source-pins.json',
             PARENT/'plan.json',PARENT/'result.json',PARENT/'attempt.json',PARENT/'status.json',
             PARENT/'image-binding.json',PARENT/'image-pins.json']
    m.save(out/'source-pins.json',{str(p):m.sha(p) for p in paths})
    command = ['/usr/bin/systemd-run','--user','--unit='+unit,'--property=Type=exec',
        '--property=KillMode=control-group','--property=RuntimeMaxSec=7200','--property=TimeoutStopSec=30',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        '/usr/bin/python3','-B',str(out/'inputs/m1_long_eof_audit_v1.py'),
        'audit','--output',str(out),'--authorize-audit']
    m.save(out/'ready-command.json',dict(service=command,shell=shlex.join(command),launched=False))


def audit(out, authorized):
    m = module(out/'inputs/q8_matmul_post_v1.py')
    d = m.d
    d.require(authorized and Path(__file__).resolve()==out/'inputs/m1_long_eof_audit_v1.py',
              'Explicit frozen offline worker required')
    job = d.read(out/'plan.json')
    unit = job['service_unit']
    owner = subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','--value'],text=True).strip()
    d.require(owner == str(os.getpid()) and '/'+unit in Path('/proc/self/cgroup').read_text(),
              'Direct service ownership required')
    d.verify(d.read(out/'source-pins.json'))
    d.save(out/'attempt.json',dict(pid=os.getpid(),started_ns=time.time_ns()))
    def status(state):
        m.update_status(out/'status.json',dict(state=state,pid=os.getpid(),power_acceptance=False))
        print(state,flush=True)
    try:
        parent = Path(job['parent'])
        status('VERIFYING_IMMUTABLE_M1_IMAGE_ELF_AND_RTL_ADMISSION')
        plan,binding,ddc,pins,roles = d.activity_inputs(parent,'native','m1')
        d.require(plan['case_id']=='qwen3_real_decode_attn_q_m1_n64_native' and
                  plan['init_seed']==0 and not plan['environment_diagnostic'], 'Wrong M1 task/environment')
        cycles = plan['last_cycle']-plan['first_cycle']
        d.require(cycles >= job['minimum_cycles'], 'Formal minimum 20000 cycles not met')
        status('AUDITING_COMPLETE_INITIAL_STATE_AND_EOF_NO_GLS')
        capture = m.completed_parent(parent,out,plan,binding)
        evidence = capture['vcd_evidence']
        status('AUDITING_CRITICAL_CONTROLS_AND_ACTIVE_PAYLOADS')
        activity = d.scan_activity_vcd(Path(capture['vcd']),cycles,evidence['first_tick'],
                                      evidence['last_tick'],budget=job['audit_seconds'])
        activity.update(d.activity_policy(activity,'native','m1'))
        d.save(out/'activity-audit.json',activity)
        d.require(activity['state']=='ACTIVITY_WINDOW_ELIGIBLE_NOT_GLS_PASS',
                  'Activity rejected: '+'; '.join(activity['reasons']))
        d.verify(pins)
        pins.update(d.read(out/'source-pins.json'))
        for p in (parent/'result.json',parent/'run/window.vcd',parent/'run/run.vcs.log',
                  parent/'run/console.log',out/'parent-independent-audit.json',out/'activity-audit.json'):
            pins[str(p)] = d.sha(p)
        d.save(out/'checked-artifacts.json',pins)
        d.save(out/'result.json',dict(state='INDEPENDENT_LONG_CAPTURE_ELIGIBLE_NOT_TASK_PASS',
            original_state='FAIL',original_worker_reclassified=False,original_result_unchanged=True,
            original_result=dict(path=str(parent/'result.json'),sha256=d.sha(parent/'result.json')),
            vcd=capture['vcd'],vcd_sha256=capture['vcd_sha256'],log=capture['log'],
            log_sha256=capture['log_sha256'],first_cycle=plan['first_cycle'],last_cycle=plan['last_cycle'],
            cycles=cycles,clock_period_ns=1,vcd_evidence=evidence,
            elf_sha256=capture['elf_sha256'],simv_sha256=capture['simv_sha256'],
            source_pins=str(out/'checked-artifacts.json'),image_pins=str(parent/'image-pins.json'),
            parent_independent_audit=str(out/'parent-independent-audit.json'),
            activity_audit=str(out/'activity-audit.json'),proof_roles=roles,
            task_pass=False,gate_numeric_checked=False,gate_protocol_checked=False,power_acceptance=False,
            scope='Whole first timed call including quantize/packing/descriptor/matmul/waits, not matmul-only',
            SAIF_or_DC_launched=False,new_GLS_launched=False))
        status('INDEPENDENT_LONG_CAPTURE_ELIGIBLE_NOT_TASK_PASS')
        return 0
    except Exception as error:
        d.save(out/'result.json',dict(state='INDEPENDENT_AUDIT_FAIL',error=repr(error),
            original_result_unchanged=True,new_GLS_launched=False,power_acceptance=False))
        status('INDEPENDENT_AUDIT_FAIL_NO_AUTOMATIC_RERUN')
        return 1


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('action',choices=('prepare','audit'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--authorize-audit',action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    if args.action=='prepare':
        prepare(out)
        return 0
    return audit(out,args.authorize_audit)


if __name__=='__main__':
    raise SystemExit(main())
