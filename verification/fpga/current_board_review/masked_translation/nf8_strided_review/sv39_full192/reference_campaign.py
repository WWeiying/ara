#!/usr/bin/env python3
"""Bounded software-reference campaign only. No VCS launch/build entry point."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
sys.dont_write_bytecode=True
import reference as ref
HERE=Path(__file__).resolve().parent
SCHEDULER=HERE.parents[1]/'indexed_review/sv39/scheduler.py'
spec=importlib.util.spec_from_file_location('nf8_reference_scheduler',SCHEDULER)
scheduler=importlib.util.module_from_spec(spec); spec.loader.exec_module(scheduler)
require=ref.base.require
sha=ref.base.sha

def read(path): return json.loads(Path(path).read_text())
def save(path,value):
    with Path(path).open('x') as stream: json.dump(value,stream,indent=2); stream.write('\n')
def verify(pins):
    for p,h in pins.items(): require(sha(p)==h,'Input identity changed: '+p)

def prepare(out):
    require(not out.exists(),'Fresh owned campaign required')
    accepted=HERE/'reference01'; pins=read(accepted/'input_pins.json'); verify(pins)
    require(read(accepted/'status.json')['groups']==[0] and not (accepted/'failure.json').exists(),'First group not accepted')
    require(read(accepted/'group00/status.json')['status']=='HOST_SPIKE_PASS_NOT_DUT','First group not PASS')
    require(read(accepted/'host.json')==dict(status='HOST_ORACLE_ALL192_PASS_NOT_DUT',rows=909504),'All192 host oracle missing')
    geometry=ref.load_geometry(); groups=[]
    for g in range(48):
        cases=geometry['cases'][g*4:g*4+4]
        groups.append(dict(group=g,trials=[c['trial'] for c in cases],cases=cases,
                           fault_count=sum(c['expected_cause'] is not None for c in cases)))
    calibration=[]
    selected=HERE.parent/'sv39/vcs_candidate04_01'
    for t in (19,17):
        p=selected/'cases'/f'trial{t:02d}'/'complete.json'; result=read(p)
        require(result['status']=='PASS' and result['analysis']['checks']==3122,'Calibration case not PASS')
        pins[str(p)]=sha(p)
        calibration.append(dict(trial=t,wall_s=result['summary'][0]['elapsed_s'],
                                last_cycle=result['analysis']['last_cycle'],evidence=str(p)))
    paths=[Path(__file__),SCHEDULER,HERE/'README.md',HERE/'VCS_PLAN.md',accepted/'status.json',accepted/'host.json',
           accepted/'input_pins.json',accepted/'prepared/provenance.json',accepted/'group00/status.json',
           accepted/'group00/negative_oracle.json',accepted/'group00/cases.json',
           accepted/'group00/soc.elf',accepted/'group00/spike.elf',accepted/'group00/spike.trace',
           accepted/'group00/soc.symbols.json',accepted/'group00/spike.symbols.json']
    paths += [accepted/'prepared'/n for n in read(accepted/'prepared/provenance.json')['files']]
    pins.update({str(p):sha(p) for p in paths}); verify(pins)
    out.mkdir(); save(out/'geometry192.json',groups)
    pins[str(out/'geometry192.json')]=sha(out/'geometry192.json')
    plan=dict(status='FULL192_REFERENCE_PLAN_NOT_DUT',groups=groups,partitions=[list(range(2,48,2)),list(range(1,48,2))],
        accepted_group0=str(accepted),reference_workers=2,per_spike_timeout_s=90,reference_service_outer_s=7200,
        live_simv_plus_spike_plus_reserved_cap=24,min_mem_available_bytes=32*1024**3,pins=pins,
        measured_calibration=calibration,calibration_limit='Only completed19/17 independently audited;67/31 not polled',
        future_DUT=dict(authorized=False,groups=48,tuples_per_group=4,proposed_jobs=4,inner_s=2400,
            per_group_orchestration_s=2700,proposed_outer_s_jobs4=33600,
            launch_requires='All192 host/Spike/negative PASS, selected4 aggregate reviewed, image/budget authorization, fresh one-shot capacity admission'),
        scope='Exact original192 source-derived geometry; not Linux/SIG replay;169/128 cause still unlocalized')
    save(out/'plan.json',plan)
    print('FULL192_REFERENCE_PLAN_NOT_DUT',out,flush=True)

def admission():
    memory=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    available=int(memory['MemAvailable'].split()[0])*1024
    require(available>=32*1024**3,'Available RAM below32GiB; no wait/retry')
    processes=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit(): continue
        try:
            comm=(p/'comm').read_text().strip()
            if comm not in ('simv','spike'): continue
            processes.append(dict(pid=int(p.name),comm=comm,cgroup=(p/'cgroup').read_text(),
                             argv=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode()))
        except (FileNotFoundError,ProcessLookupError): continue
    require(len(processes)+2<=24,'Live simv/Spike plus reference reservation exceeds24; no wait/retry')
    return dict(observed_unix=time.time(),mem_available_bytes=available,other_processes=processes,
                reference_reserved=2,total_live_plus_reserved=len(processes)+2,cap=24,one_shot=True)

def worker(out):
    plan=read(out/'plan.json'); verify(plan['pins'])
    require(plan['status']=='FULL192_REFERENCE_PLAN_NOT_DUT' and plan['reference_workers']==2,'Wrong reference plan')
    gate=admission()
    save(out/'worker.json',dict(pid=os.getpid(),start_unix=time.time(),admission=gate,plan_sha256=sha(out/'plan.json')))
    abort=scheduler.Abort()
    for sig in (signal.SIGTERM,signal.SIGINT): signal.signal(sig,lambda n,f:abort.stop(dict(signal=n)))
    def run_one(partition,control):
        dest=out/f'partition{partition:02d}'
        cmd=['/usr/bin/python3','-B',str(HERE/'reference.py'),'--out',str(dest),
             '--groups',*[str(g) for g in plan['partitions'][partition]]]
        save(out/f'command{partition:02d}.json',cmd)
        with (out/f'partition{partition:02d}.log').open('x') as log:
            process=control.launch(partition,lambda:subprocess.Popen(cmd,cwd=HERE,stdout=log,
                stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True))
            code=process.wait()
        control.remove(partition)
        result=dict(status='PASS' if code==0 else 'FAIL',returncode=code,output=str(dest))
        if code: control.stop(dict(partition=partition,result=result))
        return result
    results=scheduler.run_groups([0,1],2,run_one,abort)
    try:
        require(all(r['status']=='PASS' for r in results.values()),'Reference partition failed/cancelled')
        groups=[]; all_trials=[]; checks=0; negatives=0
        for g in range(48):
            root=HERE/'reference01' if g==0 else out/f'partition{g%2:02d}'
            verify(read(root/'input_pins.json'))
            require(not (root/'failure.json').exists(),'Reference failure artifact present')
            d=root/f'group{g:02d}'; status=read(d/'status.json'); cases=read(d/'cases.json')
            require(status['status']=='HOST_SPIKE_PASS_NOT_DUT' and status['trials']==list(range(g*4,g*4+4)),'Missing/wrong group')
            require(cases==plan['groups'][g]['cases'],'Original geometry changed')
            for backend in ('soc','spike'): require(sha(d/(backend+'.elf'))==status['elf_sha256'][backend],'ELF changed')
            rejected=read(d/'negative_oracle.json')['rejected']
            require({x['trial'] for x in rejected}==set(status['trials']),'Missing trial negative checks')
            all_trials+=status['trials']; checks+=status['checks']; negatives+=len(rejected)
            groups.append(dict(group=g,reference=str(d),checks=status['checks'],commits=status['commits'],
                               elf_sha256=status['elf_sha256'],status_sha256=sha(d/'status.json')))
        require(all_trials==list(range(192)),'Not exact full192')
        verify(plan['pins']); require(sha(out/'plan.json')==read(out/'worker.json')['plan_sha256'],'Plan changed')
        result=dict(status='HOST_SPIKE_ALL192_PASS_NOT_DUT',trials=all_trials,groups=groups,
                    checks=checks,negative_rejections=negatives)
    except Exception as error:
        result=dict(status='FULL192_REFERENCE_NOT_PASS_NOT_DUT',error=str(error),partitions=results,firstfailure=abort.reason)
    result.update(VCS_launched=False,Linux_replay=False,original169_128_localized=False)
    save(out/'complete.json',result)
    return int(result['status']!='HOST_SPIKE_ALL192_PASS_NOT_DUT')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('action',choices=['prepare','worker'])
    p.add_argument('--out',type=Path,required=True); a=p.parse_args(); out=a.out.resolve()
    require(out.is_relative_to(HERE) and out!=HERE,'Fresh owned full192 directory required')
    if a.action=='prepare': prepare(out)
    else: sys.exit(worker(out))
