#!/usr/bin/env python3
"""One bounded, first-failure-stop NV8 replay on immutable candidate04."""
import argparse
from pathlib import Path
import re
import subprocess
import sys
import time

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import replay as common
read,save,sha,require=common.read,common.save,common.sha,common.require
IMAGE=Path('/home/wangwy/fpga_runs/current_board_memory_candidate04/campaign/image')
IMAGE_SHA='e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673'
OUT=HERE/'vcs_candidate04_01'
UNIT='ara-fp-compare-nv-successor-candidate04.service'

def accepted(text,entry,name):
    return 'FP_NV_FAIL' not in text and common.console_pass(text,entry,name)

def launch():
    require(not OUT.exists(),'Output collision, no retry')
    state=subprocess.check_output(['systemctl','--user','show',UNIT,'-p','LoadState'],text=True)
    require('LoadState=not-found' in state,'Service collision')
    programs=read(HERE/'soc01/programs.json')
    names=list(programs['programs'])
    reference=read(HERE/'reference01/reference.json')
    host=read(HERE/'host01/results.json')
    require(len(names)==8 and reference['status']=='PASS' and [r['name'] for r in reference['results']]==names,'Spike membership')
    require(len(host)==8 and all(r['returncode']==0 for r in host),'Host checks')
    require(sha(IMAGE/'image.json')==IMAGE_SHA,'Image identity')
    pins={}
    for directory in ('prepared01','soc01','spike01','reference01','host01'):
        for p in (HERE/directory).rglob('*'):
            if p.is_file(): pins[str(p)]=sha(p)
    provenance=read(HERE/'prepared01/provenance.json')
    pins.update(provenance['dependencies']); pins.update(provenance['source_pins'])
    ledger=read(IMAGE/'image.json'); snapshot=Path(ledger['snapshot'])/'snapshot.json'
    require(sha(snapshot)==ledger['snapshot_sha256'],'Snapshot identity')
    for p in (Path(__file__).resolve(),Path(common.__file__),IMAGE/'image.json',snapshot): pins[str(p)]=sha(p)
    frozen=read(snapshot)
    for p,digest in frozen['files'].items(): pins[str(Path(frozen['root'])/p)]=digest
    common.pins_check(pins)
    targets={}
    for name,entry in programs['programs'].items():
        require(sha(entry['path'])==entry['sha256'],'ELF identity')
        match=re.search(r'([0-9a-f]+) <source_target>:\n\s*[0-9a-f]+:\s*([0-9a-f]+)\s+([^\n]+)',(HERE/'soc01'/f'{name}.dis').read_text())
        require(match is not None,'Target missing')
        targets[name]=dict(pc='0x'+match[1],opcode=match[2],instruction=match[3],elf_sha256=entry['sha256'])
        valid='\n'.join(['BOARD_CASE_BEGIN '+name,*entry['pass_markers'],'Core Test *** SUCCESS *** (tohost = 0)'])
        require(accepted(valid,entry,name),'Valid rejected')
        for bad in ('FP_NV_FAIL x','BOARD_REPLAY_TRAP x','Fatal: x'):
            require(not accepted(valid+'\n'+bad,entry,name),'Contradiction accepted')
        require(not accepted('',entry,name),'Incomplete accepted')
    live=[]
    for p in Path('/proc').glob('[0-9]*'):
        try:
            args=[x.decode(errors='replace') for x in (p/'cmdline').read_bytes().split(b'\0') if x]
            if args and Path(args[0]).name=='simv': live.append(dict(pid=int(p.name),argv=args))
        except OSError: continue
    observed=sum(any('/indexed_review/' in a for a in p['argv']) for p in live)
    reserved=max(0,2-observed)
    mem=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    available=int(mem['MemAvailable'].split()[0])*1024; total=len(live)+reserved+1
    gate=dict(time=time.time(),live=live,live_count=len(live),nf7_unoccupied_reservation=reserved,
        own_slots=1,total_live_reserved=total,cap=24,available_bytes=available,
        min_available_bytes=32*1024**3,passed=total<=24 and available>=32*1024**3)
    OUT.mkdir(); save(OUT/'resource_gate.json',gate)
    save(OUT/'plan.json',dict(names=names,pins=pins,targets=targets,image=str(IMAGE),image_sha256=IMAGE_SHA,
        jobs=1,timeout_per_case_s=180,outer_s=1800,first_failure_stop=True,checker_host_tests=40))
    if not gate['passed']:
        save(OUT/'complete.json',dict(status='CAPACITY_BLOCKED_NO_LAUNCH',retries=0))
        print('CAPACITY_BLOCKED_NO_LAUNCH',total); return 2
    command=['systemd-run','--user','--unit='+UNIT,'--collect','--property=RuntimeMaxSec=1800',
        '--property=TimeoutStopSec=60','--property=KillMode=control-group','--property=Restart=no',
        '--property=StandardOutput=append:'+str(OUT/'service.log'),
        '--property=StandardError=append:'+str(OUT/'service.log'),
        sys.executable,'-B',str(Path(__file__).resolve()),'--work',sha(OUT/'plan.json')]
    result=subprocess.run(command,text=True,capture_output=True)
    save(OUT/'launch.json',dict(command=command,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))
    print(result.stderr.strip(),'total_live_reserved='+str(total),'available_GiB='+str(available/1024**3))
    return result.returncode

def work(digest):
    require(sha(OUT/'plan.json')==digest,'Plan changed')
    plan=read(OUT/'plan.json'); common.pins_check(plan['pins'])
    command=[sys.executable,'-B',str(common.BASE/'run.py'),'run','--image',str(IMAGE),
        '--programs',str(HERE/'soc01'),'--out',str(OUT/'replay'),'--jobs','1','--timeout','180','--execute']
    for name in plan['names']: command+=['--case',name]
    save(OUT/'runner_command.json',command)
    with (OUT/'runner.log').open('x') as log: rc=subprocess.call(command,stdout=log,stderr=subprocess.STDOUT)
    results=[]; reason=''
    try:
        common.pins_check(plan['pins'])
        run=read(OUT/'replay/run.json'); summary=read(OUT/'replay/summary.json')
        programs=read(HERE/'soc01/programs.json')['programs']; ledger=read(IMAGE/'image.json')
        for row in summary:
            name=row['name']; artifact=OUT/'replay/tests'/name
            text=(artifact/'console.log').read_text() if (artifact/'console.log').exists() else ''
            entry=programs[name]
            result=dict(name=name,status=row['status'],returncode=row['returncode'],elapsed_s=row['elapsed_s'],
                markers=[s for s in text.splitlines() if 'FP_NV_' in s or 'BOARD_CASE_' in s or 'Core Test' in s])
            if row['status']=='PASS':
                require(row['returncode']==0 and accepted(text,entry,name),'Oracle veto '+name)
                require(sha(artifact/'input.elf')==entry['sha256'],'Private ELF drift')
                inputs=read(artifact/'inputs.json')
                require(inputs['binary']==dict(source=entry['path'],path=str(artifact/'input.elf'),sha256=entry['sha256']),'Input identity')
                require(inputs['simv']==dict(path=ledger['simv'],image_sha256=ledger['files']),'Image identity')
                result['console_sha256']=sha(artifact/'console.log')
            results.append(result)
        require(rc==0 and run['status']=='COMPLETE' and run['status_counts']=={'PASS':8} and
                run['tests']==plan['names'] and [r['name'] for r in results]==plan['names'], 'Not all eight passed')
        passed=True
    except Exception as error:
        reason=str(error); passed=False
    save(OUT/'complete.json',dict(status='PASS_NV8_CANDIDATE04' if passed else 'STOPPED_NOT_ACCEPTED',
        results=results,reason=reason,runner_returncode=rc,finished=time.time(),
        first_failure_stop=True,source_oracle_unchanged=True))
    return 0 if passed else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--launch',action='store_true'); mode.add_argument('--work')
    args=parser.parse_args()
    raise SystemExit(work(args.work) if args.work else launch())
