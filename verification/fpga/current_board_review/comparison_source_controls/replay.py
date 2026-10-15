#!/usr/bin/env python3
"""Exactly three frozen controls on candidate03; no build, no automatic retry."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'integration'
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate03/campaign/image')
IMAGE_SHA = 'e2c32c314ca85042e49517476d36c93d0d1f8a9c8eae75d86602cef1de476cb6'
OUT = HERE / 'vcs_candidate03_01'
UNIT = 'ara-fp-compare-source-candidate03.service'
NAMES = ['vv_restart16', 'vv_start0', 'vf_restart16']
FAIL = re.compile(r'FP_SOURCE_FAIL|RVV_[A-Z_]*FAIL|BOARD_CASE_FAIL|BOARD_REPLAY_[A-Z_]*(?:FAIL|TRAP|MISMATCH)|'
    r'Core Test \*\*\* FAILED|\$fatal|\bFatal\s*:|\bUVM_FATAL\b(?!\s*:\s*0\b)|'
    r'^\s*(?:FAIL(?:ED|URE)?|FATAL)\b', re.I | re.M)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read(p):
    return json.loads(Path(p).read_text())


def save(p, data):
    Path(p).write_text(json.dumps(data, indent=2)+'\n')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def console_pass(text, entry, name):
    markers = ['BOARD_CASE_BEGIN '+name, *entry['pass_markers'],
               'Core Test *** SUCCESS *** (tohost = 0)']
    return not FAIL.search(text) and all(text.splitlines().count(m)==1 for m in markers)


def pins_check(pins):
    for path, digest in pins.items():
        require(sha(path)==digest, 'Identity drift: '+path)


def preflight():
    require(not (HERE/'preflight01.json').exists(), 'Preflight collision')
    programs=read(HERE/'soc01/programs.json')
    require(list(programs['programs'])==NAMES, 'Membership differs')
    reference=read(HERE/'reference01/reference.json')
    require(reference['status']=='PASS' and [r['name'] for r in reference['results']]==NAMES,
            'Three references required')
    require(read(HERE/'host01/result.json')['returncode']==0, 'Host checks required')
    require(sha(IMAGE/'image.json')==IMAGE_SHA, 'Wrong candidate03 image')
    pins={}
    for directory in ('prepared01', 'soc01', 'spike01', 'reference01', 'host01'):
        for p in (HERE/directory).rglob('*'):
            if p.is_file(): pins[str(p)]=sha(p)
    provenance=read(HERE/'prepared01/provenance.json')
    pins.update(provenance['dependencies'])
    pins.update(provenance['source_pins'])
    pins[str(Path(__file__).resolve())]=sha(__file__)
    ledger=read(IMAGE/'image.json')
    snapshot=Path(ledger['snapshot'])/'snapshot.json'
    require(sha(snapshot)==ledger['snapshot_sha256'], 'Snapshot mismatch')
    pins[str(IMAGE/'image.json')]=IMAGE_SHA
    pins[str(snapshot)]=sha(snapshot)
    frozen=read(snapshot)
    for p,digest in frozen['files'].items(): pins[str(Path(frozen['root'])/p)]=digest
    pins_check(pins)
    targets={}
    for name,entry in programs['programs'].items():
        require(sha(entry['path'])==entry['sha256'], 'ELF mismatch')
        dis=(HERE/'soc01'/f'{name}.dis').read_text()
        match=re.search(r'([0-9a-f]+) <source_target>:\n\s*[0-9a-f]+:\s*([0-9a-f]+)\s+([^\n]+)',dis)
        require(match is not None, 'Missing target')
        targets[name]=dict(pc='0x'+match[1], opcode=match[2], instruction=match[3], elf_sha256=entry['sha256'])
    entry=programs['programs'][NAMES[0]]
    valid='\n'.join(['BOARD_CASE_BEGIN '+NAMES[0], *entry['pass_markers'], 'Core Test *** SUCCESS *** (tohost = 0)'])
    require(console_pass(valid,entry,NAMES[0]), 'Valid console rejected')
    for bad in ('FP_SOURCE_FAIL x', 'BOARD_REPLAY_TRAP x', 'Fatal: x', 'RVV_FP_COMPARE_FAIL'):
        require(not console_pass(valid+'\n'+bad,entry,NAMES[0]), 'Failure veto broken')
    require(not console_pass('',entry,NAMES[0]), 'Incomplete console accepted')
    save(HERE/'preflight01.json',dict(status='READY_HOST_SPIKE_3_PASS_NOT_DUT',pins=pins,
        targets=targets,names=NAMES,jobs=1,timeout_per_case_s=180,outer_s=900,
        checker_host_tests=6,immutable_inputs=True,no_recompile_for_candidate04=True))
    print(json.dumps(dict(status='READY',targets=targets),indent=2))


def launch():
    require(not OUT.exists(), 'Output collision; no retry')
    state=subprocess.check_output(['systemctl','--user','show',UNIT,'-p','LoadState'],text=True)
    require('LoadState=not-found' in state, 'Service collision')
    plan=read(HERE/'preflight01.json')
    pins_check(plan['pins'])
    live=[]
    for p in Path('/proc').glob('[0-9]*'):
        try:
            argv=[x.decode(errors='replace') for x in (p/'cmdline').read_bytes().split(b'\0') if x]
            if argv and Path(argv[0]).name=='simv': live.append(dict(pid=int(p.name),argv=argv))
        except OSError:
            continue
    observed=sum(any('/indexed_review/' in a for a in p['argv']) for p in live)
    reserved=max(0,2-observed)
    mem=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    available=int(mem['MemAvailable'].split()[0])*1024
    total=len(live)+reserved+1
    gate=dict(time=time.time(),live=live,live_count=len(live),nf7_slots=2,nf7_observed=observed,
        nf7_unoccupied_reservation=reserved,own_slots=1,total_live_reserved=total,cap=24,
        available_bytes=available,min_available_bytes=32*1024**3,
        passed=total<=24 and available>=32*1024**3)
    OUT.mkdir()
    save(OUT/'resource_gate.json',gate)
    save(OUT/'plan.json',plan)
    if not gate['passed']:
        save(OUT/'complete.json',dict(status='CAPACITY_BLOCKED_NO_LAUNCH',retries=0))
        print(json.dumps(dict(status='BLOCKED',total=total,available_gib=available/1024**3)))
        return 2
    command=['systemd-run','--user','--unit='+UNIT,'--collect','--property=RuntimeMaxSec=900',
        '--property=TimeoutStopSec=60','--property=KillMode=control-group','--property=Restart=no',
        '--property=StandardOutput=append:'+str(OUT/'service.log'),
        '--property=StandardError=append:'+str(OUT/'service.log'),
        sys.executable,'-B',str(Path(__file__).resolve()),'--work',sha(OUT/'plan.json')]
    result=subprocess.run(command,text=True,capture_output=True)
    save(OUT/'launch.json',dict(command=command,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))
    print(json.dumps(dict(returncode=result.returncode,total_live_reserved=total,
        available_gib=available/1024**3,unit=UNIT,output=str(OUT),launch=result.stderr)))
    return result.returncode


def work(digest):
    require(sha(OUT/'plan.json')==digest,'Plan changed')
    plan=read(OUT/'plan.json')
    programs=read(HERE/'soc01/programs.json')['programs']
    ledger=read(IMAGE/'image.json')
    results=[]
    for name in NAMES:
        pins_check(plan['pins'])
        destination=OUT/name
        command=[sys.executable,'-B',str(BASE/'run.py'),'run','--image',str(IMAGE),
            '--programs',str(HERE/'soc01'),'--out',str(destination),
            '--case',name,'--jobs','1','--timeout','180','--execute']
        with (OUT/(name+'.runner.log')).open('x') as log:
            rc=subprocess.call(command,stdout=log,stderr=subprocess.STDOUT)
        entry=programs[name]
        record=dict(name=name,runner_returncode=rc,command=command,status='NOT_ACCEPTED')
        try:
            run=read(destination/'run.json')
            summary=read(destination/'summary.json')
            require(run['status']=='COMPLETE' and run['tests']==[name] and len(summary)==1,'Incomplete runner')
            artifact=destination/'tests'/name
            inputs=read(artifact/'inputs.json')
            require(sha(artifact/'input.elf')==entry['sha256'],'Private ELF differs')
            require(inputs['binary']==dict(source=entry['path'],path=str(artifact/'input.elf'),sha256=entry['sha256']), 'Input identity differs')
            require(inputs['simv']==dict(path=ledger['simv'],image_sha256=ledger['files']),'Image identity differs')
            text=(artifact/'console.log').read_text()
            accepted=rc==0 and summary[0]['status']=='PASS' and summary[0]['returncode']==0 and console_pass(text,entry,name)
            record.update(status='PASS' if accepted else 'FAIL',runner_status=summary[0]['status'],
                sim_returncode=summary[0]['returncode'],elapsed_s=summary[0]['elapsed_s'],
                failure_marker_veto=bool(FAIL.search(text)),
                markers=[s for s in text.splitlines() if 'FP_SOURCE_' in s or 'BOARD_CASE_' in s or 'Core Test' in s],
                console_sha256=sha(artifact/'console.log'))
        except Exception as error:
            record['reason']=str(error)
        results.append(record)
        # Separate runner invocations deliberately keep normal controls running after baseline failure.
    pins_check(plan['pins'])
    save(OUT/'complete.json',dict(status='COMPLETE_3_BASELINE_OBSERVATIONS',results=results,
        all_pass=all(r['status']=='PASS' for r in results),pins_unchanged=True,finished=time.time()))
    return int(any(r['status']!='PASS' for r in results))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight',action='store_true')
    mode.add_argument('--launch',action='store_true')
    mode.add_argument('--work')
    args=parser.parse_args()
    raise SystemExit(work(args.work) if args.work else launch() if args.launch else preflight())
