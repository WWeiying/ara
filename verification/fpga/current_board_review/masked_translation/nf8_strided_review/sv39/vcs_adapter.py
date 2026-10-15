#!/usr/bin/env python3
"""No-build NF8 candidate04 admission and bounded, fail-fast four-ELF execution."""
import argparse
import csv
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
sys.dont_write_bytecode=True
import reference as ref
import csv_oracle
import host_csv
import ledger
from support import HERE,ANCESTOR,read,save,load

live_tail=load(ANCESTOR/'live_tail.py','nf8_live_tail')
scheduler=load(ANCESTOR/'scheduler.py','nf8_scheduler')
IMAGE=Path('/home/wangwy/fpga_runs/current_board_memory_candidate04/campaign/image')
FROZEN=IMAGE.parents[1]/'frozen'
IMAGE_SHA='e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673'
SNAPSHOT_SHA='b8dcc5d0efc55af13b1e194866135ac2d7370bbcc75276e37d402c5235ea545d'
SIMV_SHA='2caf02a142d9f28fa2bf390ab5225465e4a5281b6877a04eda976cfe80f27502'
REFERENCE=HERE/'reference01'
RUNNER=ref.base.BASE/'run.py'
TRIALS=list(ref.TRIALS)
TIMEOUT=1800
CASE_OUTER=1950
OUTER=5400
JOBS=2
require=ref.base.require
sha=ref.base.sha

def verify(pins):
    for p,h in pins.items(): require(sha(p)==h,'Pinned identity drift: '+p)

def check_image():
    require(sha(IMAGE/'image.json')==IMAGE_SHA,'Different authorized candidate04 image')
    require(sha(FROZEN/'snapshot.json')==SNAPSHOT_SHA,'Different frozen snapshot')
    runner=load(RUNNER,'nf8_integration_run')
    repo=runner.sealed(FROZEN)
    snapshot=read(FROZEN/'snapshot.json')
    require(len(snapshot['files'])==539,'Frozen membership changed')
    image=read(IMAGE/'image.json')
    require(image['snapshot']==str(FROZEN) and image['snapshot_sha256']==SNAPSHOT_SHA,'Image/source mismatch')
    require(image['simv']==str(IMAGE/'_build/vcs/simv') and image['files'][image['simv']]==SIMV_SHA,'Wrong simv')
    _,_,_,simulation_image=runner.framework(repo)
    require(simulation_image(Path(image['simv']))==image['files'],'Image content/membership drift')
    directory=Path(image['simv']).parent
    conf=directory/'simulator.conf'; manifest=directory/'vcs_source_manifest.json'
    require(sha(conf)==image['configuration_sha256'] and sha(manifest)==image['manifest_sha256'],'Image metadata drift')
    config=dict(line.split('=',1) for line in conf.read_text().splitlines())
    for k,v in dict(nr_lanes='4',vlen='1024',sim_l2_bytes='2097152').items(): require(config[k]==v,'Wrong SoC geometry')
    soc=(repo/'hardware/src/ara_soc.sv').read_text()
    require(re.search(r'OSSupport\s*=\s*1',soc) and 'cfg.NrPMPEntries          = 0;' in soc,'Wrong OS/PMP interface')
    from ara_verify.vcs_source_manifest import collect
    capture=read(manifest)
    require(collect(Path(capture['filelist']),repo,[Path(p) for p in capture['extra_sources']])==capture['files'],
            'Compiled-source manifest changed')
    return image

def reference_directory(t): return REFERENCE/f'trial{t:02d}'
def name(t): return f'nf8_trial{t:02d}'

def command(out,t=None,execute=False):
    destination=out/'cases'/f'trial{t:02d}'/'run' if execute else out/'dryrun'
    cmd=['/usr/bin/python3','-B',str(RUNNER),'run','--image',str(IMAGE),
         '--programs',str(out/'programs'),'--out',str(destination),
         '--jobs','1' if execute else str(JOBS),'--timeout',str(TIMEOUT)]
    for trial in ([t] if execute else TRIALS): cmd+=['--case',name(trial)]
    return cmd+(['--execute'] if execute else [])

def validate_plan(p):
    require(p['status']=='NF8_CANDIDATE04_PREFLIGHT_PASS_NOT_LAUNCHED','Not an accepted preflight')
    require(p['trials']==TRIALS and p['jobs']==2,'Original four tuples/jobs changed')
    require((p['timeout_s'],p['case_outer_s'],p['service_outer_s'])==(1800,1950,5400),'Fixed budgets changed')
    require(p['image_sha256']==IMAGE_SHA,'Plan image changed')

def preflight(out):
    require(not out.exists(),'Fresh preflight output required')
    verify(read(REFERENCE/'input_pins.json'))
    require(read(REFERENCE/'status.json')['status']=='HOST_SPIKE_SELECTED4_PASS_NOT_DUT','Reference not PASS')
    require(read(REFERENCE/'status.json')['trials']==TRIALS and not (REFERENCE/'failure.json').exists(),'Reference scope/failure differs')
    require(read(REFERENCE/'host.json')['status']=='HOST_ORACLE_SELECTED4_PASS_NOT_DUT','Host oracle not PASS')
    geometry=ref.load_geometry()
    prepared=ref.base.prepare.check(REFERENCE/'prepared')
    image=check_image()
    out.mkdir(); (out/'programs').mkdir(); (out/'cases').mkdir(); (out/'ledgers').mkdir()
    paths=[Path(__file__),HERE/'support.py',HERE/'csv_oracle.py',HERE/'host_csv.py',HERE/'ledger.py',
           HERE/'test_vcs_adapter.py',ANCESTOR/'live_tail.py',ANCESTOR/'scheduler.py',RUNNER,
           IMAGE/'image.json',FROZEN/'snapshot.json',REFERENCE/'status.json',REFERENCE/'host.json',
           REFERENCE/'source_provenance.json',REFERENCE/'postrun_audit.json',REFERENCE/'input_pins.json',
           REFERENCE/'prepared/provenance.json']
    paths += [REFERENCE/'prepared'/n for n in prepared['files']]
    pins={**read(REFERENCE/'input_pins.json'),**{str(p):sha(p) for p in paths}}
    programs={}
    for t in TRIALS:
        d=reference_directory(t); status=read(d/'status.json'); cases=read(d/'cases.json')
        require(status['status']=='HOST_SPIKE_PASS_NOT_DUT' and status['trials']==[t],'Wrong terminal reference')
        require(cases==[c for c in geometry['cases'] if c['trial']==t],'Original geometry changed')
        require(len(read(d/'negative_oracle.json')['rejected'])==65,'Missing reference negative coverage')
        soc=read(d/'soc.symbols.json'); spike=read(d/'spike.symbols.json')
        require('tohost' not in soc and soc['__bss_end']<0x800f0000,'Not a compatible SoC ELF')
        for n,a in soc.items():
            if n.startswith('nx_') and a>=soc['__bss_start']: require(spike[n]==a,'Unadapted data relocation')
        for backend in ('soc','spike'):
            require(sha(d/(backend+'.elf'))==status['elf_sha256'][backend],'Accepted ELF changed')
        nm=subprocess.check_output([str(ref.base.CC.with_name('riscv64-unknown-elf-nm')),'-n',str(d/'soc.elf')],text=True,timeout=15)
        actual={m[3]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$',nm,re.M)}
        require(actual==soc,'SoC symbols differ from ELF')
        readelf=ref.base.CC.with_name('riscv64-unknown-elf-readelf')
        header=subprocess.check_output([str(readelf),'-h',str(d/'soc.elf')],text=True,timeout=15)
        layout=subprocess.check_output([str(readelf),'-Wl',str(d/'soc.elf')],text=True,timeout=15)
        require('ELF64' in header and 'RISC-V' in header and re.search(r'Entry point address:\s+0x80000000',header),'Wrong ELF ABI/entry')
        loads=re.findall(r'^\s*LOAD\s+0x[0-9a-f]+\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+0x[0-9a-f]+\s+(0x[0-9a-f]+)',layout,re.M)
        require(loads and all(int(v,16)==int(p,16) and 0x80000000<=int(p,16) and int(p,16)+int(n,16)<=0x80200000 for v,p,n in loads),'ELF outside L2')
        host=out/f'host_trial{t:02d}'
        host_csv.exercise(d,host)
        calls=ledger.extract(d)
        require(calls==read(host/'ledger.json'),'Independent ledger extractors disagree')
        save(out/'ledgers'/f'trial{t:02d}.json',calls)
        paths=[d/n for n in ('status.json','cases.json','negative_oracle.json','soc.elf','spike.elf',
                            'soc.symbols.json','spike.symbols.json','soc.dis','spike.dis','spike.trace')]
        paths += [host/'status.json',host/'ledger.json',out/'ledgers'/f'trial{t:02d}.json']
        pins.update({str(p):sha(p) for p in paths})
        programs[name(t)]=dict(path=str(d/'soc.elf'),sha256=status['elf_sha256']['soc'],cases=[t],pass_markers=['NX_SV39_PASS'])
    save(out/'programs/programs.json',dict(schema_version=1,backend='vcs-soc',prepared=str(REFERENCE/'prepared'),
         provenance_sha256=sha(REFERENCE/'prepared/provenance.json'),programs=programs))
    with (out/'host_adapter.log').open('x') as log:
        subprocess.run(['/usr/bin/python3','-B',str(HERE/'test_vcs_adapter.py')],cwd=HERE,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=60)
    with (out/'dryrun.log').open('x') as log:
        subprocess.run(command(out),cwd=ref.base.ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    dry=read(out/'dryrun/summary.json')
    require(len(dry)==4 and {r['name'] for r in dry}==set(programs) and all(r['status']=='DRY_RUN' for r in dry),'Dryrun membership differs')
    paths=[out/'programs/programs.json',out/'dryrun/summary.json',out/'host_adapter.log']
    pins.update({str(p):sha(p) for p in paths}); verify(pins); require(check_image()==image,'Image changed during preflight')
    plan=dict(status='NF8_CANDIDATE04_PREFLIGHT_PASS_NOT_LAUNCHED',trials=TRIALS,jobs=JOBS,
        timeout_s=TIMEOUT,case_outer_s=CASE_OUTER,service_outer_s=OUTER,pins=pins,
        image_sha256=IMAGE_SHA,image_files=image['files'],VCS_started=False,
        scope='Four original source-derived tuples; original169/128 remains unlocalized; not Linux replay',
        authorization='User authorized candidate04 four independent ELFs jobs2 inner1800 outer5400; failfast no retries')
    validate_plan(plan); save(out/'plan.json',plan)
    print(plan['status'],out,flush=True)

def case_worker(out,t,abort):
    d=out/'cases'/f'trial{t:02d}'; d.mkdir()
    source=reference_directory(t); status=read(source/'status.json')
    checker=csv_oracle.Checker(read(source/'soc.symbols.json'),read(source/'cases.json'),status,
                              read(out/'ledgers'/f'trial{t:02d}.json'))
    cmd=command(out,t,True); save(d/'command.json',cmd)
    artifact=d/'run/tests'/name(t); trace=artifact/'commit_trace.csv'
    events=live_tail.DirectoryEvents(d); first_line=True
    def line(text):
        nonlocal first_line
        values=next(csv.reader([text]))
        if first_line:
            require(values==csv_oracle.FIELDS,'Wrong CSV header'); first_line=False
        else:
            require(len(values)==len(csv_oracle.FIELDS),'Malformed CSV row')
            checker.row(dict(zip(csv_oracle.FIELDS,values)))
    def failure(error):
        analysis=checker.failure(error)
        if not (d/'firstfailure.json').exists(): save(d/'firstfailure.json',analysis)
        abort.stop(dict(trial=t,analysis=analysis))
    start=time.monotonic(); code=None; timer=None; process=None
    try:
        with (d/'worker.log').open('x') as log:
            process=abort.launch(t,lambda: subprocess.Popen(cmd,cwd=ref.base.ROOT,stdout=log,
                stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True))
            timer=threading.Timer(CASE_OUTER,lambda: failure(ValueError('1950s runner/teardown bound reached')))
            timer.daemon=True; timer.start()
            code=live_tail.wait_append(process,events,trace,line,failure)
        analysis=checker.finish()
        summary=read(d/'run/summary.json'); meta=read(d/'run/run.json'); inputs=read(artifact/'inputs.json')
        image=read(IMAGE/'image.json')
        require(code==0 and len(summary)==1 and summary[0]['name']==name(t) and summary[0]['status']=='PASS'
                and summary[0]['returncode']==0,'Runner not PASS')
        require(meta['status']=='COMPLETE' and meta['tests']==[name(t)] and meta['commit_trace'] is True
                and meta['simv']==image['simv'] and meta['invocation']==cmd[2:],'Run metadata mismatch')
        require(inputs['simv']==dict(path=image['simv'],image_sha256=image['files']),'Executed image mismatch')
        require(inputs['binary']['sha256']==sha(artifact/'input.elf')==status['elf_sha256']['soc']
                and Path(inputs['binary']['source']).resolve()==source/'soc.elf','Executed ELF mismatch')
        console=(artifact/'console.log').read_text()
        require(console.count('NX_SV39_PASS')==1 and 'NX_SV39_FAIL' not in console,'Missing/failed firmware completion')
        result=dict(status='PASS',returncode=code,analysis=analysis,summary=summary)
    except Exception as error:
        failure(error)
        if process is None: events.close()
        result=dict(status='FAIL',returncode=code,analysis=checker.failure(error))
    finally:
        if timer: timer.cancel()
        abort.remove(t)
    result.update(trial=t,elapsed_s=time.monotonic()-start)
    save(d/'complete.json',result); return result

def worker(out,authorized):
    require(authorized,'Explicit authorization required')
    plan=read(out/'plan.json'); validate_plan(plan); verify(plan['pins']); image=check_image()
    require(image['files']==plan['image_files'],'Plan image mismatch')
    save(out/'worker.json',dict(pid=os.getpid(),start_unix=time.time(),jobs=JOBS,plan_sha256=sha(out/'plan.json')))
    abort=scheduler.Abort()
    for sig in (signal.SIGTERM,signal.SIGINT):
        signal.signal(sig,lambda signum,frame: abort.stop(dict(signal=signum)))
    results=scheduler.run_groups(TRIALS,JOBS,lambda t,a:case_worker(out,t,a),abort)
    passed=all(results[t]['status']=='PASS' for t in TRIALS); post='UNCHANGED'
    try:
        verify(plan['pins']); require(check_image()==image,'Post-run image drift')
        require(sha(out/'plan.json')==read(out/'worker.json')['plan_sha256'],'Plan changed')
    except Exception as error: passed=False; post=str(error)
    save(out/'complete.json',dict(status='CANDIDATE04_NF8_SELECTED4_PASS' if passed else 'CANDIDATE04_NF8_NOT_PASS',
        trials=results,firstfailure=abort.reason,post_hashes=post,image_sha256=IMAGE_SHA,scope=plan['scope']))
    return int(not passed)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['preflight','worker']); p.add_argument('--out',type=Path,required=True)
    p.add_argument('--authorize-run',action='store_true'); a=p.parse_args(); out=a.out.resolve()
    require(out.is_relative_to(HERE) and out!=HERE,'Output outside owned directory')
    if a.action=='preflight': preflight(out)
    else: sys.exit(worker(out,a.authorize_run))
