#!/usr/bin/env python3
"""Prepare-only grouped NF8 driver. Explicit reviewed launch: pilot0 then max8."""
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
import scheduler8 as scheduler
import capacity8
from support import HERE,ANCESTOR,read,save,load
live_tail=load(ANCESTOR/'live_tail.py','nf8_group_live_tail')
IMAGE=Path('/home/wangwy/fpga_runs/current_board_memory_candidate04/campaign/image')
FROZEN=IMAGE.parents[1]/'frozen'
IMAGE_SHA='e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673'
SNAPSHOT_SHA='b8dcc5d0efc55af13b1e194866135ac2d7370bbcc75276e37d402c5235ea545d'
SIMV_SHA='2caf02a142d9f28fa2bf390ab5225465e4a5281b6877a04eda976cfe80f27502'
RUNNER=ref.base.BASE/'run.py'
CAMPAIGN=HERE/'reference_campaign01'
SELECTED=HERE.parent/'sv39/vcs_candidate04_01'
SELECTED_SHA='793a633ad9572cc5990cebb6da592f87a4cf4c02eef12b240f3eba5614b27baa'
GROUPS=list(range(48))
TIMEOUT=2400
CASE_OUTER=2520
OUTER=18000
JOBS=8
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


def reference_directory(g):
    root=HERE/'reference01' if g==0 else CAMPAIGN/f'partition{g%2:02d}'
    return root/f'group{g:02d}'

def name(g): return f'nf8_g{g:02d}'

def accepted_references():
    # One terminal admission only; never wait for or poll an in-flight reference.
    final=read(CAMPAIGN/'complete.json')
    require(final['status']=='HOST_SPIKE_ALL192_PASS_NOT_DUT' and final['trials']==list(range(192)),
            'Exact full192 reference terminal PASS required')
    require([g['group'] for g in final['groups']]==GROUPS,'Terminal reference membership differs')
    geometry=ref.load_geometry(); pins={}; groups=[]; total_checks=0
    roots=[HERE/'reference01',CAMPAIGN/'partition00',CAMPAIGN/'partition01']
    for root in roots:
        require(not (root/'failure.json').exists(),'Reference failure artifact exists')
        terminal=read(root/'status.json')
        expected=[0] if root==roots[0] else list(range(2,48,2)) if root==roots[1] else list(range(1,48,2))
        require(terminal['status']=='HOST_SPIKE_GROUPS_PASS_NOT_DUT' and terminal['groups']==expected,'Wrong reference partition')
        require(read(root/'host.json')==dict(status='HOST_ORACLE_ALL192_PASS_NOT_DUT',rows=909504),'Host192 not accepted')
        rp=read(root/'input_pins.json'); verify(rp); pins.update(rp)
        prep=ref.base.prepare.check(root/'prepared')
        paths=[root/n for n in ('status.json','host.json','input_pins.json','prepared/provenance.json')]
        paths += [root/'prepared'/n for n in prep['files']]
        pins.update({str(p):sha(p) for p in paths})
    for g in GROUPS:
        d=reference_directory(g); status=read(d/'status.json'); cases=read(d/'cases.json')
        require(status['status']=='HOST_SPIKE_PASS_NOT_DUT' and status['trials']==list(range(4*g,4*g+4)),'Wrong accepted group')
        require(cases==geometry['cases'][4*g:4*g+4],'Original source geometry mismatch')
        item=final['groups'][g]
        require(item['reference']==str(d) and item['status_sha256']==sha(d/'status.json')
                and item['checks']==status['checks'] and item['elf_sha256']==status['elf_sha256'],'Aggregate/reference binding mismatch')
        rejected=read(d/'negative_oracle.json')['rejected']
        require({n['trial'] for n in rejected}==set(status['trials']),'Missing trial negative coverage')
        for b in ('soc','spike'): require(sha(d/(b+'.elf'))==status['elf_sha256'][b],'Accepted ELF changed')
        paths=[d/n for n in ('status.json','cases.json','negative_oracle.json','soc.elf','spike.elf',
                            'soc.symbols.json','spike.symbols.json','soc.dis','spike.dis','spike.trace')]
        pins.update({str(p):sha(p) for p in paths})
        total_checks+=status['checks']; groups.append(dict(group=g,reference=str(d),checks=status['checks'],trials=status['trials']))
    require(total_checks==final['checks'],'Full192 comparison count mismatch')
    pins[str(CAMPAIGN/'complete.json')]=sha(CAMPAIGN/'complete.json')
    verify(read(CAMPAIGN/'plan.json')['pins'])
    return dict(groups=groups,checks=total_checks,pins=pins)

def host_directory(root,g): return HERE/'dut_host_group00' if g==0 else root/f'group{g:02d}'

def host_validate(out):
    require(not out.exists(),'Fresh host checker output required')
    references=accepted_references(); out.mkdir()
    abort=scheduler.Abort()
    def one(g,control):
        if g==0: return dict(status='PASS',output=str(host_directory(out,g)))
        d=host_directory(out,g)
        cmd=['/usr/bin/python3','-B',str(HERE/'host_csv.py'),'--reference',str(reference_directory(g)),'--out',str(d)]
        try:
            with (out/f'group{g:02d}.log').open('x') as log:
                process=control.launch(g,lambda:subprocess.Popen(cmd,cwd=HERE,stdout=log,stderr=subprocess.STDOUT,start_new_session=True))
                code=process.wait(timeout=600)
            control.remove(g)
            if code: control.stop(dict(group=g,returncode=code))
            return dict(status='PASS' if code==0 else 'FAIL',returncode=code)
        except Exception as error:
            control.stop(dict(group=g,error=str(error))); return dict(status='FAIL',error=str(error))
    results=scheduler.run_groups(GROUPS,4,one,abort)
    pins=dict(references['pins'])
    try:
        require(all(results[g]['status']=='PASS' for g in GROUPS),'Host group checker failed/cancelled')
        negatives=allowed=0
        for g in GROUPS:
            d=host_directory(out,g); result=read(d/'status.json'); refstatus=read(reference_directory(g)/'status.json')
            verify(result['pins'])
            require(result['status']=='HOST_SPIKE_DERIVED_CSV_CHECKER_PASS_NOT_DUT'
                    and result['positive']['trials']==list(range(g*4,g*4+4))
                    and result['positive']['checks']==refstatus['checks'],'Host CSV coverage differs')
            require(len(result['negatives_rejected'])>=16,'Missing checker negatives')
            require(ledger.extract(reference_directory(g))==read(d/'ledger.json'),'Independent ledger extractors differ')
            negatives+=len(result['negatives_rejected']); allowed+=result['allowed_partial_states']
            pins.update({str(p):sha(p) for p in (d/'status.json',d/'ledger.json')})
        pins.update({str(HERE/n):sha(HERE/n) for n in ('vcs_jobs8.py','scheduler8.py','capacity8.py','csv_oracle.py','host_csv.py','ledger.py','support.py')})
        verify(pins)
        result=dict(status='HOST_CSV_ALL192_PASS_NOT_DUT',groups=GROUPS,trials=list(range(192)),
                    checks=references['checks'],negatives_rejected=negatives,allowed_partial_states=allowed,pins=pins)
    except Exception as error:
        result=dict(status='HOST_CSV_FULL192_NOT_PASS_NOT_DUT',error=str(error),groups=results)
    save(out/'status.json',result)
    require(result['status']=='HOST_CSV_ALL192_PASS_NOT_DUT','Host192 CSV not PASS')
    print(result['status'],out,flush=True)

def command(out,t=None,execute=False):
    destination=out/'groups'/f'group{t:02d}'/'run' if execute else out/'dryrun'
    cmd=['/usr/bin/python3','-B',str(RUNNER),'run','--image',str(IMAGE),
         '--programs',str(out/'programs'),'--out',str(destination),
         '--jobs','1' if execute else str(JOBS),'--timeout',str(TIMEOUT)]
    for g in ([t] if execute else GROUPS): cmd+=['--case',name(g)]
    return cmd+(['--execute'] if execute else [])

def validate_plan(p):
    require(p['status']=='NF8_FULL192_JOBS8_PREFLIGHT_PASS_NOT_LAUNCHED','Not a ready preflight')
    require(p['groups']==GROUPS and p['trials']==list(range(192)),'No subset/reordering')
    require((p['jobs'],p['pilot'],p['timeout_s'],p['case_outer_s'],p['service_outer_s'])==(8,0,2400,2520,18000),'Fixed stages/budgets changed')
    require(7*p['case_outer_s']+360<=p['service_outer_s'],'Pilot plus6waves exceeds outer bound')
    require(p['image_sha256']==IMAGE_SHA and p['reserves']==dict(nf7=2,parent38=4,gather=4,whole=6,own=8),'Image/reservations changed')

def preflight(out,host_root):
    require(not out.exists(),'Fresh full192 DUT plan required')
    references=accepted_references()
    require(host_root is not None and host_root.resolve().is_relative_to(HERE),'Owned complete host checker run required')
    host=read(host_root/'status.json')
    require(host['status']=='HOST_CSV_ALL192_PASS_NOT_DUT' and host['groups']==GROUPS,'Full group CSV/negative acceptance required')
    verify(host['pins'])
    require(sha(SELECTED/'complete.json')==SELECTED_SHA and
            read(SELECTED/'complete.json')['status']=='CANDIDATE04_NF8_SELECTED4_PASS','Selected4 acceptance changed')
    verify(read(SELECTED/'plan.json')['pins'])
    image=check_image()
    out.mkdir(); (out/'programs').mkdir(); (out/'groups').mkdir(); (out/'ledgers').mkdir()
    programs={}
    for g in GROUPS:
        d=reference_directory(g); status=read(d/'status.json'); soc=read(d/'soc.symbols.json'); spike=read(d/'spike.symbols.json')
        require('tohost' not in soc and soc['__bss_end']<0x800f0000,'Wrong SoC interface')
        for n,a in soc.items():
            if n.startswith('na_') and a>=soc['__bss_start']: require(spike[n]==a,'Unadapted data relocation')
        nm=subprocess.check_output([str(ref.base.CC.with_name('riscv64-unknown-elf-nm')),'-n',str(d/'soc.elf')],text=True,timeout=15)
        actual={m[3]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$',nm,re.M)}
        require(actual==soc,'Wrong SoC symbol identity')
        readelf=ref.base.CC.with_name('riscv64-unknown-elf-readelf')
        header=subprocess.check_output([str(readelf),'-h',str(d/'soc.elf')],text=True,timeout=15)
        layout=subprocess.check_output([str(readelf),'-Wl',str(d/'soc.elf')],text=True,timeout=15)
        require('ELF64' in header and 'RISC-V' in header and re.search(r'Entry point address:\s+0x80000000',header),'Wrong ELF entry/ABI')
        loads=re.findall(r'^\s*LOAD\s+0x[0-9a-f]+\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+0x[0-9a-f]+\s+(0x[0-9a-f]+)',layout,re.M)
        require(loads and all(int(v,16)==int(p,16) and 0x80000000<=int(p,16) and int(p,16)+int(n,16)<=0x80200000 for v,p,n in loads),'ELF outside L2')
        save(out/'ledgers'/f'group{g:02d}.json',read(host_directory(host_root,g)/'ledger.json'))
        programs[name(g)]=dict(path=str(d/'soc.elf'),sha256=status['elf_sha256']['soc'],
                              cases=status['trials'],pass_markers=['NA_SV39_PASS'])
    prepared=HERE/'reference01/prepared'
    save(out/'programs/programs.json',dict(schema_version=1,backend='vcs-soc',prepared=str(prepared),
         provenance_sha256=sha(prepared/'provenance.json'),programs=programs))
    with (out/'tests.log').open('x') as log:
        subprocess.run(['/usr/bin/python3','-B',str(HERE/'test_jobs8.py')],cwd=HERE,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    with (out/'dryrun.log').open('x') as log:
        subprocess.run(command(out),cwd=ref.base.ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    dry=read(out/'dryrun/summary.json')
    require(len(dry)==48 and {r['name'] for r in dry}==set(programs) and all(r['status']=='DRY_RUN' for r in dry),'Dryrun membership differs')
    paths=[Path(__file__),HERE/'scheduler8.py',HERE/'capacity8.py',HERE/'test_jobs8.py',
           HERE/'csv_oracle.py',HERE/'host_csv.py',HERE/'ledger.py',HERE/'support.py',HERE/'DUT_JOBS8_PLAN.md',
           ANCESTOR/'scheduler.py',ANCESTOR/'live_tail.py',RUNNER,IMAGE/'image.json',FROZEN/'snapshot.json',
           SELECTED/'complete.json',SELECTED/'plan.json',HERE.parent/'sv39/DUT_ACCEPTANCE.md',
           host_root/'status.json',out/'programs/programs.json',out/'tests.log',out/'dryrun/summary.json']
    paths+=list((out/'ledgers').glob('*.json'))
    pins={**references['pins'],**host['pins'],**{str(p):sha(p) for p in paths}}
    verify(pins); require(check_image()==image,'Image drift during preflight')
    plan=dict(status='NF8_FULL192_JOBS8_PREFLIGHT_PASS_NOT_LAUNCHED',groups=GROUPS,trials=list(range(192)),
              jobs=8,pilot=0,timeout_s=2400,case_outer_s=2520,service_outer_s=18000,reserves=dict(nf7=2,parent38=4,gather=4,whole=6,own=8),
              image_sha256=IMAGE_SHA,image_files=image['files'],pins=pins,VCS_started=False,
              scope='Original192 source-derived Sv39, not Linux/SIG replay or169/128 root-cause closure')
    validate_plan(plan); save(out/'plan.json',plan)
    save(out/'review.template.json',dict(parent_authorized=False,plan_sha256=sha(out/'plan.json'),
         image_sha256=IMAGE_SHA,reserved_units=dict(parent38='',gather='',whole=''),nf7_unit=capacity8.NF7_UNIT,jobs=8))
    print(plan['status'],sha(out/'plan.json'),flush=True)

def group_worker(out,t,abort):
    d=out/'groups'/f'group{t:02d}'; d.mkdir()
    source=reference_directory(t); status=read(source/'status.json')
    checker=csv_oracle.Checker(read(source/'soc.symbols.json'),read(source/'cases.json'),status,
                              read(out/'ledgers'/f'group{t:02d}.json'))
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
        abort.stop(dict(group=t,analysis=analysis))
    start=time.monotonic(); code=None; timer=None; process=None
    try:
        with (d/'worker.log').open('x') as log:
            process=abort.launch(t,lambda: subprocess.Popen(cmd,cwd=ref.base.ROOT,stdout=log,
                stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True))
            timer=threading.Timer(CASE_OUTER,lambda: failure(ValueError('2520s runner/teardown bound reached')))
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
        require(console.count('NA_SV39_PASS')==1 and 'NA_SV39_FAIL' not in console,'Missing/failed firmware completion')
        result=dict(status='PASS',returncode=code,analysis=analysis,summary=summary)
    except Exception as error:
        failure(error)
        if process is None: events.close()
        result=dict(status='FAIL',returncode=code,analysis=checker.failure(error))
    finally:
        if timer: timer.cancel()
        abort.remove(t)
    result.update(group=t,elapsed_s=time.monotonic()-start)
    save(d/'complete.json',result); return result


def worker(out,review_path,authorized):
    require(authorized and review_path is not None,'Explicit parent review and authorization required')
    require(not (out/'worker.json').exists(),'One launch only; no repeat/retry')
    plan=read(out/'plan.json'); validate_plan(plan); verify(plan['pins'])
    review=read(review_path)
    require(review.get('parent_authorized') is True and review.get('plan_sha256')==sha(out/'plan.json')
            and review.get('image_sha256')==IMAGE_SHA and review.get('jobs')==8
            and review.get('nf7_unit')==capacity8.NF7_UNIT,'Review identity/authorization differs')
    image=check_image(); require(image['files']==plan['image_files'],'Plan image differs')
    gate=capacity8.actual(review['reserved_units'])
    save(out/'worker.json',dict(pid=os.getpid(),start_unix=time.time(),jobs=8,reserved_through_pilot=8,
         plan_sha256=sha(out/'plan.json'),review_sha256=sha(review_path),gate=gate))
    abort=scheduler.Abort()
    for sig in (signal.SIGTERM,signal.SIGINT): signal.signal(sig,lambda n,f:abort.stop(dict(signal=n)))
    def pilot_ok(result):
        require(result['status']=='PASS' and result['analysis']['trials']==[0,1,2,3],'Pilot not full four-case PASS')
        verify(plan['pins']); require(check_image()==image,'Pilot input/image drift')
        save(out/'pilot_acceptance.json',dict(status='PILOT_GROUP0_EXACT_ORACLE_PASS',group0_complete_sha256=sha(out/'groups/group00/complete.json'),
             csv_sha256=sha(out/'groups/group00/run/tests/nf8_g00/commit_trace.csv'),remaining_groups=list(range(1,48)),remaining_jobs=8))
    results=scheduler.pilot_then_remaining(lambda g,a:group_worker(out,g,a),abort,pilot_ok)
    passed=all(results[g]['status']=='PASS' for g in GROUPS); post='UNCHANGED'
    try:
        verify(plan['pins']); require(check_image()==image,'Post image drift')
        require(sha(out/'plan.json')==read(out/'worker.json')['plan_sha256']
                and sha(review_path)==read(out/'worker.json')['review_sha256'],'Plan/review changed')
    except Exception as error: passed=False; post=str(error)
    save(out/'complete.json',dict(status='CANDIDATE04_NF8_FULL192_PASS' if passed else 'CANDIDATE04_NF8_FULL192_NOT_PASS',
         groups=results,firstfailure=abort.reason,post_hashes=post,image_sha256=IMAGE_SHA,scope=plan['scope']))
    return int(not passed)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['host-validate','preflight','worker'])
    p.add_argument('--out',type=Path,required=True); p.add_argument('--host-root',type=Path)
    p.add_argument('--review',type=Path); p.add_argument('--authorize-run',action='store_true')
    a=p.parse_args(); out=a.out.resolve()
    require(out.is_relative_to(HERE) and out!=HERE,'Owned output required')
    if a.action=='host-validate': host_validate(out)
    elif a.action=='preflight': preflight(out,a.host_root.resolve() if a.host_root else None)
    else: sys.exit(worker(out,a.review.resolve() if a.review else None,a.authorize_run))
