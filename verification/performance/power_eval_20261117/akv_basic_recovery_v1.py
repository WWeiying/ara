#!/usr/bin/env python3
"""Power-only continuation for observed memory-load/RVV-FMA AKV firmware."""
import argparse
import importlib.util
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess

OUT=Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
IMAGE=OUT/'power_gate_build_20261118_akv_fifo_init_01'
CAPTURE=OUT/'power_gls_20261118_akv_fifo_formal_01'
NAME='akv_basic_recovery_v1.py'


def module(path,name):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    return m


def basic_activity(a):
    if a['reasons']!=['No mapped resident PV FPU activity']:
        raise ValueError('Not the isolated wrong-path resident-PV requirement')
    if a['cycles']<20000 or a['active_payload_unknown_samples'] or a['pc_unknown_when_committing']:
        raise ValueError('Short window or active payload/commit unknown')
    if abs(a['clock_edges']-2*a['cycles'])>1 or not a['retire_samples']:
        raise ValueError('Invalid clock or no acknowledged execution')
    for key in ('clock','reset','ack','pc','dispatcher','sequencer','vector_valid','pv_state','qk_mode'):
        if a['signals'][key]['unknown_ticks']:raise ValueError('Critical X: '+key)
    if a['signals']['reset']['values'].get('1',0)!=a['duration_ticks']:
        raise ValueError('Reset asserted in window')
    pcs={int(k,2) for k,v in a['signals']['pc']['values'].items() if v}
    if not {0x80000224,0x800002ec,0x800002fc,0x80000300}<=pcs:
        raise ValueError('Expected custom QK/PV loads and RVV FMA PCs absent')
    return dict(cycles=a['cycles'],critical_control_unknown_ticks=0,
        observed_active_payload_unknown_samples=0,scope='Observed custom memory-load plus RVV FMA attention path',
        resident_PV_path_exercised=False,full_gate_numeric_or_protocol_pass=False)


def prepare(out):
    if out.parent!=OUT or out.exists():raise ValueError('Fresh independent output required')
    (out/'inputs').mkdir(parents=True)
    for name in (NAME,'test_akv_basic_recovery_v1.py'):
        shutil.copyfile(Path(__file__).with_name(name),out/'inputs'/name)
    f=module(IMAGE/'inputs/akv_fifo_env_v1.py','basic_prepare_frozen_pipeline')
    m=f.helpers(IMAGE/'inputs');d=m.d
    basic_activity(d.read(CAPTURE/'activity-audit.json'))
    unit=out.name.replace('_','-')+'.service'
    d.save(out/'plan.json',dict(service_unit=unit,capture=str(CAPTURE),image=str(IMAGE),
        original_FAIL_unchanged=True,new_GLS_or_compile=False,additional_whole_waveform_audit=False,
        policy='Power-only path-correct basic admission, not modification of original checker'))
    paths=[*(out/'inputs').iterdir(),out/'plan.json',IMAGE/'inputs/akv_fifo_env_v1.py',
        IMAGE/'source-pins.json',IMAGE/'image-pins.json',IMAGE/'pipeline-result.json',
        IMAGE/'environment-validation.json',CAPTURE/'plan.json',CAPTURE/'run-result.json',CAPTURE/'activity-audit.json']
    d.save(out/'source-pins.json',{str(p):d.sha(p) for p in paths})
    command=['/usr/bin/systemd-run','--user','--unit='+unit,'--property=Type=exec',
        '--property=KillMode=control-group','--property=RuntimeMaxSec=32400','--property=TimeoutStopSec=30',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        '/usr/bin/python3','-B',str(out/'inputs'/NAME),'continue','--output',str(out),'--authorize-post']
    d.save(out/'ready-command.json',dict(service=command,shell=shlex.join(command),launched=False))


def resume(out,authorized):
    f=module(IMAGE/'inputs/akv_fifo_env_v1.py','basic_frozen_pipeline')
    m=f.helpers(IMAGE/'inputs');d=m.d
    d.require(authorized and Path(__file__).resolve()==out/'inputs'/NAME,'Authorized frozen continuation required')
    job=d.read(out/'plan.json');unit=job['service_unit']
    owner=subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','--value'],text=True).strip()
    d.require(owner==str(os.getpid()) and '/'+unit in Path('/proc/self/cgroup').read_text(),'Direct service owner required')
    d.save(out/'attempt.json',dict(pid=os.getpid()))
    def status(state):
        m.update_status(out/'status.json',dict(state=state,pid=os.getpid(),power_acceptance=False));print(state,flush=True)
    try:
        status('VERIFYING_BASIC_EXISTING_WINDOW_NO_NEW_WAVEFORM_AUDIT')
        d.verify(d.read(out/'source-pins.json'));d.verify(d.read(IMAGE/'source-pins.json'))
        d.verify(d.read(IMAGE/'image-pins.json'))
        d.require(d.read(IMAGE/'pipeline-result.json')['error']=="ValueError('Formal activity/active payload rejected')",
                  'Original rejection changed')
        a=d.read(CAPTURE/'activity-audit.json');proof=basic_activity(a)
        plan=d.read(CAPTURE/'plan.json');run=d.read(CAPTURE/'run-result.json')
        d.require(run['returncode']==0 and a['cycles']==plan['last_cycle']-plan['first_cycle'], 'Bounded run/duration mismatch')
        env=d.read(IMAGE/'environment-validation.json')
        d.require(env['state']=='VRF_AND_FIFO_OPPOSITE_SEEDS_PASS_NOT_TASK_PASS','Unvalidated startup environment')
        for r in env['diagnostics']:d.verify({r['path']:r['sha256']})
        log=CAPTURE/'run/run.vcs.log';vcd=CAPTURE/'run/window.vcd'
        text=log.read_text();console=(CAPTURE/'run/console.log').read_text()
        d.require(not re.search(r'input (?:CLK|CEB/CEBM|WEB/WEBM|A/AM|BWEB/BWEBM) unknown/high-Z',console),
                  'Critical memory control X')
        for label,cycle,tick in (('GATE_ROI_BEGIN',plan['first_cycle'],a['first_tick']),
                                  ('GATE_CAPTURE_WINDOW_COMPLETE',plan['last_cycle'],a['last_tick'])):
            d.require(len(re.findall(r'^'+label+r' cycle='+str(cycle)+r' time='+str(tick)+r'\b',text,re.M))==1,
                      'Original capture marker mismatch')
        d.require(re.search(r'\$finish at simulation time\s+'+str(a['last_tick'])+r'\s*$',text,re.M), 'Missing clean EOF')
        stat=vcd.stat()
        d.require(0<stat.st_size<=plan['max_vcd_bytes'] and
                  run['started_ns']<=stat.st_mtime_ns<=run['finished_ns']+2*10**9 and
                  run['started_ns']<=stat.st_ctime_ns<=run['finished_ns']+2*10**9,'VCD provenance/size mismatch')
        # The sealed worker calls inspect_vcd successfully before writing this activity report.
        evidence=dict(first_tick=a['first_tick'],last_tick=a['last_tick'],timescale_fs=100,
            duration_fs=a['duration_ticks']*100,complete_initial_state=True,eof_at_selected_end=True,
            reuse_basis='Previously completed EOF check in pinned producer before its isolated resident-PV rejection',
            repeated_whole_waveform_scan=False)
        adapter=out/'independent-capture';adapter.mkdir()
        (adapter/'run').symlink_to(CAPTURE/'run',target_is_directory=True)
        shutil.copyfile(CAPTURE/'plan.json',adapter/'plan.json')
        receipt=dict(state='POWER_WINDOW_ELIGIBLE_RELATIVE_ESTIMATE_NOT_TASK_PASS',proof=proof,
            original_rejection=str(IMAGE/'pipeline-result.json'),original_activity=str(CAPTURE/'activity-audit.json'),
            original_worker_reclassified=False,original_capture=str(CAPTURE),
            vcd=str(vcd),vcd_sha256=d.sha(vcd),log=str(log),log_sha256=d.sha(log),
            first_cycle=plan['first_cycle'],last_cycle=plan['last_cycle'],cycles=a['cycles'],
            clock_period_ns=1,vcd_evidence=evidence,elf_sha256=plan['elf_map']['sha256'],
            simv_sha256=d.sha(IMAGE/'sim/simv'),power_acceptance=False,
            limitation='Not resident-PV activity or full gate task PASS; unused resident operands X/Z with valid=0 are not active payload errors')
        d.verify({plan['elf_map']['gls']:receipt['elf_sha256']})
        d.save(adapter/'result.json',receipt)
        pins=d.read(out/'source-pins.json')
        for p in (log,vcd,CAPTURE/'run/console.log',adapter/'plan.json',adapter/'result.json'):
            pins[str(p)]=d.sha(p)
        d.save(out/'checked-artifacts.json',pins)
        status('EXISTING_41411_CYCLE_WINDOW_ACCEPTED_CONVERTING_SAIF_THEN_DC')
        rc=f.postprocess(IMAGE,adapter,receipt,m,unit)
        d.save(out/'result.json',dict(state='POWER_POSTPROCESS_COMPLETE_NOT_SIGNOFF' if rc==0 else 'DC_FAILED_PRESERVED',
            original_rejection_unchanged=True,new_GLS_launched=False,independent_admission=str(adapter/'result.json'),
            power_output=str(OUT/'power_dc_20261118_akv_fifo_formal_01/native')))
        status('POWER_POSTPROCESS_COMPLETE_NOT_SIGNOFF' if rc==0 else 'DC_FAILED_PRESERVED')
        return rc
    except Exception as error:
        d.save(out/'result.json',dict(state='BASIC_CONTINUATION_FAIL',error=repr(error),original_rejection_unchanged=True))
        status('STOPPED_NO_AUTOMATIC_GLS_RETRY')
        return 1


if __name__=='__main__':
    p=argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('action',choices=('prepare','continue'))
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--authorize-post',action='store_true')
    args=p.parse_args()
    if args.action=='prepare':prepare(args.output.resolve())
    else:raise SystemExit(resume(args.output.resolve(),args.authorize_post))
