#!/usr/bin/env python3
"""Offline M4 EOF/activity recovery then SAIF/DC; never launch GLS or rewrite FAIL."""
import argparse
import importlib.util
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time

OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
PARENT = OUT/'power_gls_20261117_long_m4_01'
FROZEN = OUT/'power_dc_20261117_q8_matmul_subwindow_03/native/inputs'
REFERENCE = OUT/'power_dc_20261117_formal_native_follow_01/m4/pair-plan.json'
CASE = 'qwen3_attn_q_q4k_m4_n64_direct_native'
NAME = 'm4_long_recovery_v1.py'


def module(inputs):
    spec = importlib.util.spec_from_file_location('m4_frozen_recovery',inputs/'q8_matmul_post_v1.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def validate_window(plan):
    if (plan['case_id'] != CASE or plan['init_seed'] != 0 or plan['environment_diagnostic'] or
            plan['clock_period_ns'] != 1 or plan['mode'] != 'capture' or
            plan['last_cycle']-plan['first_cycle'] < 20000):
        raise ValueError('Wrong M4 case/environment or less than 20000 cycles')
    return plan['last_cycle']-plan['first_cycle']


def require_activity(activity):
    if activity['state'] != 'ACTIVITY_WINDOW_ELIGIBLE_NOT_GLS_PASS':
        raise ValueError('Activity rejected: '+'; '.join(activity['reasons']))


def prepare(pair):
    if pair.parent != OUT or pair.exists():
        raise ValueError('Fresh owned recovery output required')
    out = pair/'native'
    (out/'inputs').mkdir(parents=True)
    (out/'reports').mkdir()
    for name in ('q8_matmul_post_v1.py','dc_power.py','convert.py'):
        shutil.copyfile(FROZEN/name,out/'inputs'/name)
    shutil.copyfile(REFERENCE,out/'inputs/reference-pair.json')
    shutil.copyfile(__file__,out/'inputs'/NAME)
    shutil.copyfile(Path(__file__).with_name('test_m4_long_recovery_v1.py'),
                    out/'inputs/test_m4_long_recovery_v1.py')
    m = module(out/'inputs')
    cycles = validate_window(m.read(PARENT/'plan.json'))
    reference = m.read(REFERENCE)
    unit = pair.name.replace('_','-')+'.service'
    limitations = reference['limitations']+[
        'Original GLS worker FAIL remains FAIL; independent EOF/activity recovery only',
        'No full-program gate numerical/protocol PASS or timing/signoff claim',
        'Native seed0 reset-only VRF initialization; baseline environment must be audited separately']
    m.save(out/'recovery-plan.json',dict(parent=str(PARENT),service_unit=unit,
        minimum_cycles=20000,cycles=cycles,audit_seconds=7200,conversion_seconds=7200,
        library_sha256=reference['library_sha256'],limitations=limitations,
        no_GLS_or_compile=True,automatic_retry=False))
    m.save(pair/'pair-plan.json',dict(runs=dict(native=str(out),rvv=str(pair/'peer-not-collected')),
        period_ns=1,library_sha256=reference['library_sha256'],limitations=limitations,
        semantic_contract=reference['semantic_contract']))
    paths = [*(out/'inputs').iterdir(),out/'recovery-plan.json',pair/'pair-plan.json',REFERENCE,
             PARENT/'source-pins.json',PARENT/'plan.json',PARENT/'result.json',PARENT/'attempt.json',
             PARENT/'status.json',PARENT/'image-binding.json',PARENT/'image-pins.json',m.c.TOOL]
    m.save(out/'recovery-pins.json',{str(p):m.sha(p) for p in paths})
    command = ['/usr/bin/systemd-run','--user','--unit='+unit,'--property=Type=exec',
        '--property=KillMode=control-group','--property=RuntimeMaxSec=43200','--property=TimeoutStopSec=30',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        '/usr/bin/python3','-B',str(out/'inputs'/NAME),'recover','--output',str(pair),'--authorize-post']
    m.save(out/'ready-command.json',dict(service=command,shell=shlex.join(command),launched=False))


def recover(pair, authorized):
    out = pair/'native'
    m = module(out/'inputs')
    d,c = m.d,m.c
    d.require(authorized and Path(__file__).resolve()==out/'inputs'/NAME,'Frozen authorized worker required')
    job = d.read(out/'recovery-plan.json')
    owner = subprocess.check_output(['systemctl','--user','show',job['service_unit'],
                                    '-p','MainPID','--value'],text=True).strip()
    d.require(owner==str(os.getpid()) and '/'+job['service_unit'] in Path('/proc/self/cgroup').read_text(),
              'Direct service ownership required')
    d.verify(d.read(out/'recovery-pins.json'))
    d.save(out/'recovery-attempt.json',dict(pid=os.getpid(),started_ns=time.time_ns()))
    def status(state):
        m.update_status(out/'recovery-status.json',dict(state=state,pid=os.getpid(),power_acceptance=False))
        print(state,flush=True)
    try:
        parent = Path(job['parent'])
        status('VERIFYING_M4_IMMUTABLE_IMAGE_ELF_RTL_ADMISSION')
        plan,binding,ddc,pins,roles = d.activity_inputs(parent,'native','m4')
        cycles = validate_window(plan)
        status('AUDITING_COMPLETE_INITIAL_STATE_AND_EOF_NO_GLS')
        capture = m.completed_parent(parent,out,plan,binding)
        evidence = capture['vcd_evidence']
        vcd,log = Path(capture['vcd']),Path(capture['log'])
        status('AUDITING_CRITICAL_CONTROLS_AND_ACTIVE_PAYLOADS')
        activity = d.scan_activity_vcd(vcd,cycles,evidence['first_tick'],evidence['last_tick'],
                                      budget=job['audit_seconds'])
        activity.update(d.activity_policy(activity,'native','m4'))
        d.save(out/'activity-audit.json',activity)
        require_activity(activity)
        pins.update(d.read(out/'recovery-pins.json'))
        for p in (parent/'result.json',parent/'run/console.log',vcd,log,
                  out/'parent-independent-audit.json',out/'activity-audit.json'):
            pins[str(p)] = d.sha(p)
        d.verify(pins)
        d.save(out/'checked-artifacts.json',pins)
        d.save(out/'capture-audit.json',dict(state='INDEPENDENT_LONG_CAPTURE_ELIGIBLE_NOT_TASK_PASS',
            original_result=dict(path=str(parent/'result.json'),sha256=d.sha(parent/'result.json')),
            original_worker_reclassified=False,original_state='FAIL',vcd=str(vcd),vcd_sha256=d.sha(vcd),
            log=str(log),log_sha256=d.sha(log),cycles=cycles,first_cycle=plan['first_cycle'],
            last_cycle=plan['last_cycle'],clock_period_ns=1,vcd_evidence=evidence,
            elf_sha256=capture['elf_sha256'],simv_sha256=capture['simv_sha256'],
            source_pins=str(out/'checked-artifacts.json'),image_pins=str(parent/'image-pins.json'),
            activity_audit=str(out/'activity-audit.json'),task_pass=False,power_acceptance=False,
            scope='Whole first timed call, not matmul-only; no padding or waveform rewriting'))
        status('CONVERTING_AUDITED_INTACT_M4_VCD')
        conversion = out/'conversion'
        conversion.mkdir()
        saif = conversion/'activity.saif'
        command = [str(c.TOOL),'-input',str(vcd),'-output',str(saif),
                   '-instance','ara_tb.dut.i_ara_soc','-time',str(evidence['first_tick']),str(evidence['last_tick'])]
        with (conversion/'conversion.log').open('x') as stream:
            subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,check=True,
                           timeout=job['conversion_seconds'])
        summary = c.saif_summary(saif)
        c.check_activity(dict(duration_fs=evidence['duration_fs'],tick_fs=evidence['timescale_fs']),summary,cycles,1)
        pins.update({str(out/'capture-audit.json'):d.sha(out/'capture-audit.json'),str(saif):d.sha(saif)})
        d.verify(pins)
        d.save(conversion/'source-pins.json',pins)
        d.save(conversion/'result.json',dict(state='SAIF_CONVERSION_PASS_NOT_POWER',command=command,
            capture_audit=dict(path=str(out/'capture-audit.json'),sha256=d.sha(out/'capture-audit.json')),
            saif=str(saif),saif_sha256=d.sha(saif),saif_summary=summary,cycles=cycles,
            source_pins=str(conversion/'source-pins.json'),original_worker_reclassified=False,
            elf_sha256=capture['elf_sha256'],simv_sha256=capture['simv_sha256'],power_measured=False))
        status('PREPARING_SAME_DDC_REAL_PIN_LOAD_DC')
        shutil.copyfile(ddc,out/'inputs/design.ddc')
        shutil.copyfile(saif,out/'inputs/activity.saif')
        (out/'inputs/power.tcl').write_text(d.make_real_load_tcl(out,sorted(job['library_sha256']),'qbs'))
        cpins = dict(job['library_sha256'])
        cpins.update({str(p):d.sha(p) for p in (d.DC_SHELL,*d.DC_INIT_FILES,out/'inputs/design.ddc',
                                              out/'inputs/activity.saif',out/'inputs/power.tcl')})
        (out/'inputs/container-pins.sha256').write_text(''.join(h+'  '+p+'\n' for p,h in sorted(cpins.items())))
        docker = Path(shutil.which('docker') or '/usr/bin/docker')
        command = [str(docker),'exec','-u',f'{os.getuid()}:{os.getgid()}','-e','HOME=/home/wangwy',
            '-e','SNPSLMD_LICENSE_FILE=27000@t7920','-w',str(out),'synopsys_workspace',
            '/usr/bin/timeout','--signal=TERM','--kill-after=20','3600','/bin/bash','-c',
            'sha256sum -c "$1" || exit 1; exec "$2" '+' '.join(d.DC_FLAGS)+' -f "$3"',
            'power-dc',str(out/'inputs/container-pins.sha256'),str(d.DC_SHELL),str(out/'inputs/power.tcl')]
        roles.update(independent_capture_audit=str(out/'capture-audit.json'),
            activity_audit=str(out/'activity-audit.json'),
            initialization='Actual native reset-only VRF seed0; baseline must be independently checked',
            window_semantics=plan['window_selection'],same_stage_ratio_claimed=False)
        dcplan = dict(schema='power-real-pin-load-run-v1',role='native',pair=str(pair),command=command,
            high_fanout_net_threshold=0,execute_seconds=3600,service_unit=job['service_unit'],
            original_result=dict(path=str(parent/'result.json'),sha256=d.sha(parent/'result.json')),
            proof_roles=roles,saif_unknowns=d.saif_unknown_fraction(saif),period_ns=1,
            library_sha256=job['library_sha256'],limitations=job['limitations'],
            ddc_sha256=d.sha(out/'inputs/design.ddc'),saif_sha256=d.sha(out/'inputs/activity.saif'))
        d.validate_real_load_plan(dcplan)
        d.save(out/'plan.json',dcplan)
        pins.update(cpins)
        pins.update({str(p):d.sha(p) for p in (out/'inputs').iterdir() if p.is_file()})
        pins.update({str(out/'plan.json'):d.sha(out/'plan.json'),str(docker):d.sha(docker)})
        d.save(out/'source-pins.json',pins)
        status('WAITING_BOUNDED_SHARED_DC_SLOT')
        with d.activity_dc_slot(time.monotonic()+14400):
            rc = d.execute_real_load(argparse.Namespace(output=out,authorize_dc=True))
        status('DC_POSTPROCESS_COMPLETE_PROVISIONAL_NOT_SIGNOFF' if rc==0 else 'DC_POSTPROCESS_FAILED_PRESERVED')
        return rc
    except Exception as error:
        d.save(out/'recovery-result.json',dict(state='INDEPENDENT_RECOVERY_FAIL',error=repr(error),
            original_result_unchanged=True,new_GLS_launched=False,power_acceptance=False))
        status('INDEPENDENT_RECOVERY_FAIL_NO_AUTOMATIC_RERUN')
        return 1


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('action',choices=('prepare','recover'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--authorize-post',action='store_true')
    args = parser.parse_args()
    if args.action=='prepare':
        prepare(args.output.resolve())
        return 0
    return recover(args.output.resolve(),args.authorize_post)


if __name__=='__main__':
    raise SystemExit(main())
