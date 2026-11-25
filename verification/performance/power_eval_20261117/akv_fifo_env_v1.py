#!/usr/bin/env python3
"""Exact-netlist AKV unused FIFO startup experiment; opposing seeds gate power."""
import argparse
import importlib.util
import os
from pathlib import Path
import re
import shutil
import shlex
import subprocess
import time

OUT=Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
IMAGE=OUT/'power_gate_build_20261118_akv_fifo_init_01'
PARENT=OUT/'power_gate_build_20261117_vrf_init_02'
DIAG=OUT/'power_gls_20261117_long_akv_diag_02'
FROZEN=OUT/'power_dc_20261117_q8_matmul_subwindow_03/native/inputs'
EVIDENCE=OUT/'power_akv_queue_x_audit_20261117_02/result.json'
ROOT=Path('/home/wangwy/openproject/ara_dsa/verification/performance/power_eval_20261117')
NAME='akv_fifo_env_v1.py'
STATE='DC_MATCHED_GATE_VRF_AND_FIFO_INIT_BUILT_NOT_VALIDATED'


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


def helpers(inputs):
    return load(inputs/'q8_matmul_post_v1.py','akv_fifo_frozen_support')


def payload_cells(text):
    modules={x[1]:x[0] for x in re.finditer(r'^[ \t]*module\s+(\w+)\b.*?^endmodule\b',text,re.M|re.S)}
    def child(body,name):
        names=re.findall(r'\b(\w+)\s+'+re.escape(name)+r'\s*\(',body)
        if len(names)!=1:raise ValueError('Ambiguous mapped instance '+name)
        return modules[names[0]]
    cells=[]
    for lane in range(4):
        inst='gen_lanes_%d__i_lane'%lane
        body=child(text,inst)
        for name in ('i_operand_queues','i_operand_queue_alu_b','i_input_buffer'):
            body=child(body,name)
        names=re.findall(r'^\s+DFQD\w+\s+(mem_q_reg_\d+__\d+_)\s*\(',body,re.M)
        if len(set(names))!=320:raise ValueError('Not exactly five 64-bit ALU-B payload words')
        prefix='ara_tb.dut.i_ara_soc.i_system.i_ara.'+inst+'.i_operand_queues.i_operand_queue_alu_b.i_input_buffer.'
        cells.extend(prefix+n for n in names)
    if len(cells)!=len(set(cells)) or len(cells)!=1280:raise ValueError('Payload scope not 1280 data flops')
    return cells


def prepare(image):
    if image!=IMAGE or image.exists():raise ValueError('Fresh owned image required')
    m=helpers(FROZEN);d=m.d
    _,_,_,lineage,_=d.activity_inputs(DIAG,'native','akv')
    d.require(d.read(EVIDENCE)['state']=='AKV_SELECTED_FIRST_X_EVIDENCE_NOT_POWER','Missing real first-X evidence')
    image.mkdir()
    for folder in ('source','models','inputs'):shutil.copytree(PARENT/folder,image/folder)
    for name in ('q8_matmul_post_v1.py','dc_power.py','convert.py','reference-pair.json'):
        shutil.copyfile(FROZEN/name,image/'inputs'/name)
    for name in (NAME,'test_akv_fifo_env_v1.py'):
        shutil.copyfile(ROOT/name,image/'inputs'/name)
    shutil.copyfile(PARENT/'elfloader.o',image/'elfloader.o')
    (image/'sim').mkdir();(image/'logs').mkdir()
    cells=payload_cells((image/'source/ara_soc_dc.v').read_text())
    for seed in (0,1):
        (image/('fifo%d.cfg'%seed)).write_text('defaultvalue x\n'+''.join('instance %s %d\n'%(p,seed) for p in cells))
    (image/'sources.f').write_text((PARENT/'sources.f').read_text().replace(str(PARENT),str(image)))
    command=[a.replace(str(PARENT),str(image)) for a in d.read(PARENT/'plan.json')['compile_command']]
    command.insert(1,'+vcs+initreg+config+'+str(image/'fifo0.cfg'))
    env=d.read(image/'inputs/rtl-plan.json')
    env['environment']['VCS_PRINT_INITREG_INITIALIZATION']='1'
    d.save(image/'inputs/experiment-rtl-plan.json',env)
    unit=image.name.replace('_','-')+'.service'
    d.save(image/'plan.json',dict(parent=str(PARENT),compile_command=command,service_unit=unit,
        netlist_sha256=d.sha(image/'source/ara_soc_dc.v'),payload_cells=cells,
        evidence=dict(path=str(EVIDENCE),sha256=d.sha(EVIDENCE)),
        runtime_force=False,controls_initialized=False,minimum_formal_cycles=20000,
        candidate_only=True,opposite_seed_diagnostics_required=True,
        original_failures_unchanged=True,timing_model='zero-delay +nospecify +notimingchecks; not timing signoff'))
    lineage.update({str(p):d.sha(p) for p in image.rglob('*') if p.is_file()})
    lineage[str(EVIDENCE)]=d.sha(EVIDENCE)
    for p in (ROOT/'akv_queue_x_audit_v2.py',ROOT/'akv_x_audit_v1.py',DIAG/'plan.json',DIAG/'image-binding.json'):
        lineage[str(p)]=d.sha(p)
    d.save(image/'source-pins.json',lineage)
    command=['/usr/bin/systemd-run','--user','--unit='+unit,'--property=Type=exec',
        '--property=KillMode=control-group','--property=RuntimeMaxSec=64800','--property=TimeoutStopSec=30',
        '--property=StandardOutput=append:'+str(image/'service.stdout.log'),
        '--property=StandardError=append:'+str(image/'service.stderr.log'),
        '/usr/bin/python3','-B',str(image/'inputs'/NAME),'pipeline','--image',str(image),'--authorize-pipeline']
    d.save(image/'ready-command.json',dict(service=command,shell=shlex.join(command),launched=False))


def run_capture(image,key,seed,formal,m,runner):
    d=m.d
    out=OUT/('power_gls_20261118_akv_fifo_'+key+'_01')
    d.require(not out.exists(),'No experiment retry')
    (out/'inputs').mkdir(parents=True);(out/'run').mkdir()
    shutil.copyfile(image/'inputs/experiment-rtl-plan.json',out/'inputs/rtl-plan.json')
    old=d.read(DIAG/'plan.json')
    first,last=(15603,57014) if formal else (28000,35500)
    plan=dict(old,first_cycle=first,last_cycle=last,max_cycles=last+500,
        wall_seconds=14400,slot_seconds=14400,max_vcd_bytes=32*1024**3,max_log_bytes=32*1024**2,
        image=str(image),environment_diagnostic=not formal,init_seed=seed)
    command=[]
    for arg in old['command']:
        arg=arg.replace(str(DIAG/'run'),str(out/'run')).replace(str(PARENT/'sim/simv'),str(image/'sim/simv'))
        if arg.startswith('+GATE_ROI_FIRST='):arg='+GATE_ROI_FIRST='+str(first)
        if arg.startswith('+GATE_ROI_LAST='):arg='+GATE_ROI_LAST='+str(last)
        if arg.startswith('+GATE_MAX_CYCLES='):arg='+GATE_MAX_CYCLES='+str(last+500)
        # Keep identical admitted ELF and reset-only VRF seed0 in both FIFO experiments.
        if arg.startswith('+GATE_VRF_INIT_SEED='):arg='+GATE_VRF_INIT_SEED=0'
        command.append(arg)
    command.append('+vcs+initreg+config+'+str(image/('fifo%d.cfg'%seed)))
    plan.update(command=command,cwd=str(out/'run'),fifo_seed=seed,VRF_seed=0)
    d.save(out/'plan.json',plan)
    d.verify(d.read(image/'source-pins.json'));d.verify(d.read(image/'image-pins.json'))
    result=runner.run_simulator(out,plan)
    d.save(out/'run-result.json',result)
    d.require(result['returncode']==0,'Bounded simulator failed')
    text=(out/'run/run.vcs.log').read_text();console=(out/'run/console.log').read_text()
    runner.b.clean_log(text);runner.b.clean_log(console)
    d.require(not runner.CRITICAL.search(console),'Critical memory control/address/clock X remains')
    ticks=runner.b.capture_markers(text,first,last)
    d.require(re.search(r'\$finish at simulation time\s+'+str(ticks[1])+r'\s*$',text,re.M), 'No clean EOF')
    report=out/'run/vcs_initreg_random_value.txt'
    allowed=set(d.read(image/'plan.json')['payload_cells']);observed=set()
    for line in report.read_text().splitlines():
        if not line.strip():continue
        fields=line.split('=',1)
        d.require(len(fields)==2 and re.fullmatch(r'\s*[01]\s*//\s*1\s+REG\s*',fields[1]),'Initreg report syntax/scope')
        path=fields[0].strip().strip('[]')
        matches=[p for p in allowed if path==p or path.startswith(p+'.')]
        d.require(len(matches)==1,'Initialization outside FIFO data-only whitelist')
        d.require(int(fields[1].strip()[0])==seed,'Wrong FIFO seed')
        observed.add(matches[0])
    d.require(observed==allowed,'Missing actual payload initialization')
    vcd=out/'run/window.vcd'
    eof=load(DIAG/'inputs/audit_gate_capture_eof.py','akv_fifo_eof')
    evidence=eof.inspect_vcd(vcd,ticks[0],ticks[1],last-first)
    if not formal:
        m.PATHS=dict(m.PATHS,pc=m.BASE+'i_system.i_ariane.pc_commit')
        frames,_=m.read_frames(vcd,evidence)
        values={};scalar=set()
        for tick,changes in frames:
            values.update(changes)
            if values.get('clock')=='0' and m.known(values.get('pc')) and int(values['pc'],2)==0x800017ec and values.get('ack','0').endswith('1'):
                word=values.get('writeback','x')[-64:]
                d.require(m.known(word),'Diagnostic scalar still X')
                scalar.add(int(word,2))
        d.require(scalar=={0xffffffff40c9651b},'Opposing FIFO seed does not reproduce exact admitted RTL scalar')
        state='FIFO_SEED_DIAGNOSTIC_PASS_NOT_POWER'
        proof=dict(scalar=hex(next(iter(scalar))),actual_initialization_cells=len(observed))
    else:
        d.require(last-first>=20000,'Short formal window')
        proof=d.scan_activity_vcd(vcd,last-first,*ticks,budget=7200)
        proof.update(d.activity_policy(proof,'native','akv'))
        d.save(out/'activity-audit.json',proof)
        d.require(proof['state']=='ACTIVITY_WINDOW_ELIGIBLE_NOT_GLS_PASS','Formal activity/active payload rejected')
        state='CAPTURE_COMPLETE_NOT_TASK_PASS'
    receipt=dict(state=state,vcd=str(vcd),log=str(out/'run/run.vcs.log'),first_cycle=first,last_cycle=last,
        cycles=last-first,clock_period_ns=1,vcd_evidence=evidence,vcd_sha256=d.sha(vcd),
        log_sha256=d.sha(out/'run/run.vcs.log'),elf_sha256=old['elf_map']['sha256'],
        simv_sha256=d.sha(image/'sim/simv'),fifo_seed=seed,VRF_seed=0,proof=proof,
        gate_numeric_pass=False,gate_protocol_pass=False,power_acceptance=False)
    d.save(out/'result.json',receipt)
    return out,receipt


def postprocess(image,capture,receipt,m,unit):
    pair=OUT/'power_dc_20261118_akv_fifo_formal_01';out=pair/'native'
    d=m.d
    (out/'inputs').mkdir(parents=True);(out/'reports').mkdir()
    for name in ('q8_matmul_post_v1.py','dc_power.py','convert.py','reference-pair.json'):
        shutil.copyfile(image/'inputs'/name,out/'inputs'/name)
    m=helpers(out/'inputs');d,c=m.d,m.c
    pins=d.read(image/'source-pins.json');pins.update(d.read(image/'image-pins.json'))
    for p in (capture/'plan.json',capture/'result.json',capture/'run/run.vcs.log',capture/'run/console.log',Path(receipt['vcd']),image/'environment-validation.json'):
        pins[str(p)]=d.sha(p)
    evidence=receipt['vcd_evidence'];saif=out/'inputs/activity.saif'
    command=[str(c.TOOL),'-input',receipt['vcd'],'-output',str(saif),'-instance','ara_tb.dut.i_ara_soc',
             '-time',str(evidence['first_tick']),str(evidence['last_tick'])]
    with (out/'conversion.log').open('x') as log:
        subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=7200)
    summary=c.saif_summary(saif)
    c.check_activity(dict(duration_fs=evidence['duration_fs'],tick_fs=evidence['timescale_fs']),summary,receipt['cycles'],1)
    d.save(out/'conversion-result.json',dict(state='SAIF_CONVERSION_PASS_NOT_POWER',command=command,
        capture=str(capture/'result.json'),saif=str(saif),saif_sha256=d.sha(saif),saif_summary=summary))
    _,_,ddc,lineage,roles=d.activity_inputs(DIAG,'native','akv');pins.update(lineage)
    libraries=d.read(out/'inputs/reference-pair.json')['library_sha256']
    limits=['AKV exact-ELF first timed call; confirm phase scope against any baseline before ratios',
        'Reset-only VRF plus time-zero unused ALU-B FIFO payload initialization, opposing seeds checked',
        'Zero-delay mapped power only; not gate full-task numerical/protocol or timing signoff',
        'Strict annotation/link/active-X gates remain required; no baseline identity substitution']
    d.save(pair/'pair-plan.json',dict(runs=dict(native=str(out),rvv=str(pair/'peer-not-collected')),
        period_ns=1,library_sha256=libraries,limitations=limits))
    shutil.copyfile(ddc,out/'inputs/design.ddc')
    (out/'inputs/power.tcl').write_text(d.make_real_load_tcl(out,sorted(libraries),'qbs'))
    cpins=dict(libraries)
    cpins.update({str(p):d.sha(p) for p in (d.DC_SHELL,*d.DC_INIT_FILES,out/'inputs/design.ddc',saif,out/'inputs/power.tcl')})
    (out/'inputs/container-pins.sha256').write_text(''.join(h+'  '+p+'\n' for p,h in sorted(cpins.items())))
    docker=Path(shutil.which('docker') or '/usr/bin/docker')
    command=[str(docker),'exec','-u',f'{os.getuid()}:{os.getgid()}','-e','HOME=/home/wangwy',
        '-e','SNPSLMD_LICENSE_FILE=27000@t7920','-w',str(out),'synopsys_workspace',
        '/usr/bin/timeout','--signal=TERM','--kill-after=20','3600','/bin/bash','-c',
        'sha256sum -c "$1" || exit 1; exec "$2" '+' '.join(d.DC_FLAGS)+' -f "$3"',
        'power-dc',str(out/'inputs/container-pins.sha256'),str(d.DC_SHELL),str(out/'inputs/power.tcl')]
    roles.update(gate_simv_sha256=receipt['simv_sha256'],
        initialization='VRF seed0 plus exactly 1280 unreset ALU-B data flops initialized once; FIFO seeds0/1 checked',
        environment_validation=str(image/'environment-validation.json'))
    d.save(out/'plan.json',dict(schema='power-real-pin-load-run-v1',role='native',pair=str(pair),
        command=command,high_fanout_net_threshold=0,execute_seconds=3600,service_unit=unit,
        original_result=dict(path=str(capture/'result.json'),sha256=d.sha(capture/'result.json')),
        proof_roles=roles,saif_unknowns=d.saif_unknown_fraction(saif),period_ns=1,
        library_sha256=libraries,limitations=limits,ddc_sha256=d.sha(out/'inputs/design.ddc'),saif_sha256=d.sha(saif)))
    pins.update(cpins)
    pins.update({str(p):d.sha(p) for p in (out/'inputs').iterdir() if p.is_file()})
    for p in (out/'plan.json',pair/'pair-plan.json',out/'conversion-result.json',c.TOOL,docker):pins[str(p)]=d.sha(p)
    d.save(out/'source-pins.json',pins)
    with d.activity_dc_slot(time.monotonic()+14400):
        return d.execute_real_load(argparse.Namespace(output=out,authorize_dc=True))


def pipeline(image,authorized):
    m=helpers(image/'inputs');d=m.d
    d.require(authorized and Path(__file__).resolve()==image/'inputs'/NAME,'Frozen authorized pipeline required')
    plan=d.read(image/'plan.json');unit=plan['service_unit']
    owner=subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','--value'],text=True).strip()
    d.require(owner==str(os.getpid()) and '/'+unit in Path('/proc/self/cgroup').read_text(),'Direct systemd owner required')
    d.save(image/'attempt.json',dict(pid=os.getpid(),started_ns=time.time_ns()))
    def status(state):
        m.update_status(image/'status.json',dict(state=state,pid=os.getpid(),power_acceptance=False));print(state,flush=True)
    try:
        d.verify(d.read(image/'source-pins.json'))
        d.activity_inputs(DIAG,'native','akv')
        status('COMPILING_SAME_NETLIST_FIFO_DATA_INIT_CANDIDATE')
        env=d.read(image/'inputs/experiment-rtl-plan.json')['environment']
        with (image/'logs/compile-console.log').open('x') as log:
            subprocess.run(plan['compile_command'],cwd=image/'sim',env=env,stdout=log,stderr=subprocess.STDOUT,
                           timeout=7200,check=True)
        d.verify(d.read(image/'source-pins.json'))
        d.require(d.sha(image/'source/ara_soc_dc.v')==plan['netlist_sha256']==d.sha(PARENT/'source/ara_soc_dc.v'),'Mapped netlist drift')
        files=[image/'sim/simv',*(p for p in (image/'sim/simv.daidir').rglob('*') if p.is_file())]
        d.save(image/'image-pins.json',{str(p):d.sha(p) for p in files})
        d.save(image/'build.json',dict(state=STATE,simulation_validated=False,netlist_sha256=plan['netlist_sha256']))
        runner=load(DIAG/'inputs/gate_long_window_v3.py','akv_fifo_frozen_runner')
        reports=[]
        for seed in (0,1):
            status('RUNNING_FIFO_SEED_%d_DIAGNOSTIC_NOT_POWER'%seed)
            path,receipt=run_capture(image,'diag_seed%d'%seed,seed,False,m,runner)
            reports.append(dict(path=str(path/'result.json'),sha256=d.sha(path/'result.json'),proof=receipt['proof']))
        d.save(image/'environment-validation.json',dict(state='VRF_AND_FIFO_OPPOSITE_SEEDS_PASS_NOT_TASK_PASS',
            diagnostics=reports,initialized_FIFO_bits=1280,controls_initialized=False,runtime_force=False))
        status('RUNNING_FORMAL_41411_CYCLE_AKV_CAPTURE')
        path,receipt=run_capture(image,'formal',0,True,m,runner)
        status('AUDITED_FORMAL_CAPTURE_CONVERTING_SAIF_THEN_DC')
        rc=postprocess(image,path,receipt,m,unit)
        status('DOWNSTREAM_COMPLETE_PROVISIONAL_NOT_SIGNOFF' if rc==0 else 'DOWNSTREAM_FAILED_EVIDENCE_PRESERVED')
        return rc
    except Exception as error:
        d.save(image/'pipeline-result.json',dict(state='CANDIDATE_OR_PIPELINE_FAIL_NO_RETRY',error=repr(error),
            original_failures_unchanged=True,power_acceptance=False))
        status('STOPPED_NO_UNVALIDATED_POWER_OR_AUTOMATIC_RETRY')
        return 1


if __name__=='__main__':
    p=argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('action',choices=('prepare','pipeline'))
    p.add_argument('--image',type=Path,default=IMAGE)
    p.add_argument('--authorize-pipeline',action='store_true')
    args=p.parse_args()
    if args.action=='prepare':prepare(args.image.resolve())
    else:raise SystemExit(pipeline(args.image.resolve(),args.authorize_pipeline))
