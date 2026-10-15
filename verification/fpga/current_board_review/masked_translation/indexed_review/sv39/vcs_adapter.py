#!/usr/bin/env python3
"""Prepare-only by default NF7 full96 adapter; worker requires later explicit authorization."""
import argparse
import csv
import json
import math
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
import ledger
import live_tail
import scheduler
from support import HERE,EXT,accepted_helpers,read,save

IMAGE=Path('/home/wangwy/fpga_runs/current_board_memory_candidate02/campaign/image')
IMAGE_SHA='384515b7365200942d08fc7b34275d10eee676cf6ce0574935043020e87c7810'
TIMEOUT=2400
GROUP_OUTER=2700
GROUPS=list(range(24))
require=ref.base.require


def reference_directory(g):
    root='reference01' if g==0 else 'reference02' if g in (1,6,18,23) else 'reference03'
    return HERE/root/f'group{g:02d}'


def accepted_references():
    """One-shot terminal gate, never an in-flight progress query or wait loop."""
    pins={}; geometry=ref.load_geometry(); total=[]; checks=0
    for root,groups in [('reference01',[0]),('reference02',[1,6,18,23]),
                        ('reference03',[g for g in GROUPS if g not in (0,1,6,18,23)])]:
        d=HERE/root
        final=read(d/'status.json')
        require(final['status']=='HOST_SPIKE_SELECTED_GROUPS_PASS_NOT_DUT' and final['groups']==groups,
                'Missing/incorrect terminal reference aggregate')
        require(not (d/'failure.json').exists(),'Reference failure artifact present')
        original=read(d/'input_pins.json')
        for p,h in original.items(): require(ref.base.sha(p)==h,'Reference input drift: '+p)
        pins.update(original)
        prepared=ref.base.prepare.check(d/'prepared')
        paths=[d/'status.json',d/'input_pins.json',d/'source_provenance.json',d/'host.json',d/'prepared/provenance.json']
        paths += [d/'prepared'/n for n in prepared['files']]
        require(read(d/'host.json')['status']=='HOST_ORACLE_ALL96_PASS_NOT_DUT','Host96 not PASS')
        pins.update({str(p):ref.base.sha(p) for p in paths})
    groups=[]
    for g in GROUPS:
        d=reference_directory(g); status=read(d/'status.json'); cases=read(d/'cases.json')
        require(status['status']=='HOST_SPIKE_PASS_NOT_DUT' and status['trials']==list(range(g*4,g*4+4)),
                'Missing/wrong original trial group')
        require(cases==geometry['cases'][g*4:g*4+4],'Original96 geometry changed')
        require(len(status['negative_oracle'])>0 if 'negative_oracle' in status else bool(read(d/'negative_oracle.json')),
                'Reference negative checks missing')
        for backend in ('soc','spike'):
            require(ref.base.sha(d/(backend+'.elf'))==status['elf_sha256'][backend],'Accepted ELF changed')
        soc=read(d/'soc.symbols.json'); spike=read(d/'spike.symbols.json')
        require('tohost' not in soc and soc['__bss_end']<0x800f0000,'Wrong SoC ELF interface')
        for n,a in soc.items():
            if n.startswith('ix_') and a>=soc['__bss_start']:
                require(spike[n]==a,'Reference/DUT data relocation requires explicit adapter')
        paths=[d/n for n in ('status.json','cases.json','negative_oracle.json','soc.elf','spike.elf',
                             'soc.symbols.json','spike.symbols.json','soc.dis','spike.dis','spike.trace')]
        pins.update({str(p):ref.base.sha(p) for p in paths})
        total+=status['trials']; checks+=status['checks']
        groups.append(dict(group=g,trials=status['trials'],reference=str(d),checks=status['checks'],
                           elf_sha256=status['elf_sha256']['soc']))
    require(total==list(range(96)),'Full96 membership/order differs')
    return dict(status='ALL96_REFERENCE_PASS_NOT_DUT',groups=groups,checks=checks,pins=pins)


def command(out,g=None,execute=False):
    runner=ref.base.BASE/'run.py'
    destination=out/'groups'/f'g{g:02d}'/'run' if execute else out/'dryrun'
    cmd=['/usr/bin/python3','-B',str(runner),'run','--image',str(IMAGE),
         '--programs',str(out/'programs'),'--out',str(destination),'--jobs','1' if execute else '4',
         '--timeout',str(TIMEOUT)]
    for group in ([g] if execute else GROUPS): cmd+=['--case',f'nf7_g{group:02d}']
    return cmd+(['--execute'] if execute else [])


def verify(pins):
    for p,h in pins.items(): require(ref.base.sha(p)==h,'Pinned identity drift: '+p)


def validate_plan(plan):
    require(plan['groups']==GROUPS and plan['trials']==list(range(96)),'No subset substitution permitted')
    require(plan['group_timeout_s']==2400 and plan['group_outer_s']==2700 and plan['max_jobs']==4,'Fixed limits changed')
    require(plan['image_sha256']==IMAGE_SHA,'Different candidate image')
    require(plan['status']=='NF7_FULL96_PREFLIGHT_PASS_NOT_LAUNCHED','Not an accepted preflight')


def preflight(out):
    require(out.is_relative_to(HERE) and not out.exists(),'Fresh owned output required')
    # Refuse without creating a plan if all96 are not terminal PASS. No polling.
    references=accepted_references()
    su=accepted_helpers(); image=su.check_image(); parent=su.parent_gate(image)
    require(ref.base.sha(IMAGE/'image.json')==IMAGE_SHA,'Candidate02 image differs')
    extended=EXT/'candidate02_extended8_02'
    require(read(extended/'complete.json')['status']=='CANDIDATE02_EXTENDED8_PASS' and
            read(extended/'csv_analysis.json')['checks']==6227,'Extended8 completion not accepted')
    hostpaths=[HERE/'csv_host01/status.json',HERE/'csv_host02/status.json',HERE/'csv_host03/status.json',
               HERE/'runner_host01.json']
    for p in hostpaths:
        result=read(p)
        require(result['status'] in ('HOST_SPIKE_DERIVED_CSV_CHECKER_PASS_NOT_DUT','HOST_RUNNER_NEGATIVES_PASS_NOT_DUT'),
                'Missing host checker/runner validation')
        verify(result['pins'])
    out.mkdir(); (out/'programs').mkdir(); (out/'ledgers').mkdir(); (out/'groups').mkdir()
    save(out/'reference_acceptance.json',references)
    prepared=HERE/'reference01/prepared'
    programs={}
    for g in GROUPS:
        d=reference_directory(g); entry=read(d/'status.json')
        # Fast extraction is cross-checked against the independently exercised parser.
        calls=ledger.extract(d)
        host={0:'csv_host01',18:'csv_host02',23:'csv_host03'}.get(g)
        if host: require(calls==read(HERE/host/'ledger.json'),'Reference ledger extractors disagree')
        save(out/'ledgers'/f'g{g:02d}.json',calls)
        programs[f'nf7_g{g:02d}']=dict(path=str(d/'soc.elf'),sha256=entry['elf_sha256']['soc'],
                                   cases=entry['trials'],pass_markers=['IX_SV39_PASS'])
        print(f'Prepared reference ledger group{g:02d}',flush=True)
    save(out/'programs/programs.json',dict(schema_version=1,backend='vcs-soc',prepared=str(prepared),
        provenance_sha256=ref.base.sha(prepared/'provenance.json'),programs=programs))
    cmd=command(out); save(out/'dryrun_command.json',cmd)
    with (out/'dryrun.log').open('x') as log:
        subprocess.run(cmd,cwd=ref.base.ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    dry=read(out/'dryrun/summary.json')
    require(len(dry)==24 and {r['name'] for r in dry}==set(programs) and all(r['status']=='DRY_RUN' for r in dry),
            'All24 dry-run membership differs')
    paths=[Path(__file__),HERE/'support.py',HERE/'csv_oracle.py',HERE/'ledger.py',HERE/'host_csv.py',
           HERE/'live_tail.py',HERE/'scheduler.py',HERE/'test_runner.py',
           out/'programs/programs.json',out/'reference_acceptance.json',out/'dryrun_command.json',out/'dryrun/summary.json',
           IMAGE/'image.json',extended/'complete.json',extended/'csv_analysis.json',
           ref.base.BASE/'run.py',ref.base.BASE/'prepare.py',EXT/'successor.py',EXT/'csv_check.py',
           EXT/'reference.py',EXT/'prepare_vcs_plan.py',EXT/'vcs_plan01/plan.json',*hostpaths]
    paths+=list((out/'ledgers').glob('*.json'))
    pins={**references['pins'],**parent['pins'],**{str(p):ref.base.sha(p) for p in paths}}
    verify(pins); su.check_image()
    plan=dict(status='NF7_FULL96_PREFLIGHT_PASS_NOT_LAUNCHED',groups=GROUPS,trials=list(range(96)),
              group_timeout_s=TIMEOUT,group_outer_s=GROUP_OUTER,max_jobs=4,image_sha256=IMAGE_SHA,
              image_files=image['files'],pins=pins,VCS_started=False,
              scope='NF7 source-derived full96, not original Linux replay',
              launch_gate='Requires new parent authorization, NF2 terminal unit, arithmetic unit and global <=8 capacity',
              suggested_service_runtime_s=16800)
    validate_plan(plan); save(out/'plan.json',plan)
    print(plan['status'],out,flush=True)


def unit_state(unit):
    require(re.fullmatch(r'ara-[A-Za-z0-9_-]+\.service',unit) is not None,'Explicit ara service unit required')
    text=subprocess.check_output(['systemctl','--user','show',unit,'-p','LoadState','-p','ActiveState',
                                 '-p','MainPID','-p','Result','-p','ControlGroup'],text=True,timeout=10)
    state=dict(line.split('=',1) for line in text.splitlines())
    require(state.get('LoadState')=='loaded','Unknown service unit')
    return state


def capacity_gate(nf2_unit,arithmetic_unit,jobs):
    require(nf2_unit!=arithmetic_unit and 1<=jobs<=4,'Invalid capacity allocation')
    nf2=unit_state(nf2_unit); arithmetic=unit_state(arithmetic_unit)
    require(nf2['ActiveState'] in ('inactive','failed') and nf2['MainPID']=='0','NF2 has not finished; refuse, do not wait')
    active=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit(): continue
        try:
            exe=(p/'exe').resolve(strict=True)
            if exe.name!='simv': continue
            cgroup=(p/'cgroup').read_text()
        except (FileNotFoundError,PermissionError,ProcessLookupError): continue
        require(bool(arithmetic.get('ControlGroup')) and arithmetic['ControlGroup'] in cgroup,
                'Another simulation occupies capacity outside the approved arithmetic unit')
        active.append(int(p.name))
    require(len(active)<=4 and len(active)+jobs<=8,'Combined arithmetic/NF7 capacity exceeds eight')
    return dict(nf2_unit=nf2_unit,nf2=nf2,arithmetic_unit=arithmetic_unit,arithmetic=arithmetic,
                arithmetic_pids=active,nf7_jobs=jobs,arithmetic_reserved_max_jobs=4,total_reserved_max_jobs=jobs+4)


def group_worker(out,g,abort):
    d=out/'groups'/f'g{g:02d}'; d.mkdir()
    source=reference_directory(g); status=read(source/'status.json')
    checker=csv_oracle.Checker(read(source/'soc.symbols.json'),read(source/'cases.json'),status,
                              read(out/'ledgers'/f'g{g:02d}.json'))
    cmd=command(out,g,True); save(d/'command.json',cmd)
    trace=d/'run/tests'/f'nf7_g{g:02d}'/'commit_trace.csv'
    events=live_tail.DirectoryEvents(d); first_line=True
    def line(text):
        nonlocal first_line
        values=next(csv.reader([text]))
        if first_line:
            require(values==csv_oracle.FIELDS,'Wrong live CSV header'); first_line=False
        else:
            require(len(values)==len(csv_oracle.FIELDS),'Malformed live CSV row')
            checker.row(dict(zip(csv_oracle.FIELDS,values)))
    def failure(error):
        analysis=checker.failure(error)
        if not (d/'firstfailure.json').exists(): save(d/'firstfailure.json',analysis)
        abort.stop(dict(group=g,analysis=analysis))
    start=time.monotonic(); code=None; timer=None; process=None
    try:
        with (d/'worker.log').open('x') as log:
            process=abort.launch(g,lambda: subprocess.Popen(cmd,cwd=ref.base.ROOT,stdout=log,
                    stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True))
            timer=threading.Timer(GROUP_OUTER,lambda: failure(ValueError('2700s orchestration bound reached')))
            timer.daemon=True; timer.start()
            code=live_tail.wait_append(process,events,trace,line,failure)
        analysis=checker.finish()
        summary=read(d/'run/summary.json')
        require(code==0 and len(summary)==1 and summary[0]['name']==f'nf7_g{g:02d}' and
                summary[0]['status']=='PASS' and summary[0]['returncode']==0,'Sealed runner did not PASS')
        result=dict(status='PASS',returncode=code,analysis=analysis,summary=summary)
    except Exception as error:
        failure(error)
        if process is None: events.close()
        result=dict(status='FAIL',returncode=code,analysis=checker.failure(error))
    finally:
        if timer: timer.cancel()
        abort.remove(g)
    result.update(group=g,elapsed_s=time.monotonic()-start)
    save(d/'complete.json',result)
    return result


def worker(out,authorized,nf2_unit,arithmetic_unit,jobs):
    require(authorized,'Later explicit --authorize-run required; prepare is not launch permission')
    plan=read(out/'plan.json'); validate_plan(plan); verify(plan['pins'])
    su=accepted_helpers(); image=su.check_image()
    require(ref.base.sha(IMAGE/'image.json')==plan['image_sha256'] and image['files']==plan['image_files'],'Image changed')
    su.parent_gate(image)
    gate=capacity_gate(nf2_unit,arithmetic_unit,jobs)
    save(out/'worker.json',dict(pid=os.getpid(),start_unix=time.time(),gate=gate,jobs=jobs,
                              plan_sha256=ref.base.sha(out/'plan.json')))
    abort=scheduler.Abort()
    for sig in (signal.SIGTERM,signal.SIGINT):
        signal.signal(sig,lambda signum,frame: abort.stop(dict(signal=signum)))
    results=scheduler.run_groups(GROUPS,jobs,lambda g,a: group_worker(out,g,a),abort)
    passed=all(results[g]['status']=='PASS' for g in GROUPS)
    post='UNCHANGED'
    try:
        verify(plan['pins']); require(su.check_image()==image,'Post-run image drift')
        require(ref.base.sha(out/'plan.json')==read(out/'worker.json')['plan_sha256'],'Plan changed during execution')
    except Exception as error: passed=False; post=str(error)
    save(out/'complete.json',dict(status='NF7_FULL96_PASS' if passed else 'NF7_FULL96_NOT_PASS',
          groups=results,firstfailure=abort.reason,post_hashes=post,scope=plan['scope'],image_sha256=IMAGE_SHA))
    return int(not passed)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['preflight','worker']); p.add_argument('--out',type=Path,required=True)
    p.add_argument('--authorize-run',action='store_true'); p.add_argument('--jobs',type=int,default=4)
    p.add_argument('--nf2-unit'); p.add_argument('--arithmetic-unit')
    a=p.parse_args(); out=a.out.resolve()
    require(out.is_relative_to(HERE) and out!=HERE,'Output outside owned directory')
    if a.action=='preflight': preflight(out)
    else: sys.exit(worker(out,a.authorize_run,a.nf2_unit,a.arithmetic_unit,a.jobs))
