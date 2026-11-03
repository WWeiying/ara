#!/usr/bin/env python3
"""Consolidate original SoC evidence, replaying only a bounded matrix timeout.

Never relabel the original campaign. No RTL, image, ELF or checker changes.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from collect_shared_mul_soc import app_regions


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('campaign',type=Path);p.add_argument('mixed',type=Path)
    p.add_argument('llama',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    def save(name,data):
        tmp=out/(name+'.tmp');tmp.write_text(json.dumps(data,indent=2)+'\n');tmp.replace(out/name)
    def state(value,**extra):save('status.json',dict(state=value,**extra))
    def check_inputs():
        for f,h in read(a.campaign/'source-pins.json').items():
            if sha(Path(f))!=h:raise ValueError('Source drift: '+f)
        for name,h in read(a.campaign/'elf_hashes.json').items():
            if sha(a.campaign/'inputs'/name)!=h:raise ValueError('ELF drift')
        for v in ('baseline','shared'):
            image=a.campaign/v/'sim/simv'
            if sha(image)!=read(a.campaign/v/'image.json')['simv_sha256']:raise ValueError('Image drift')
            for row in read(a.campaign/v/'sim/vcs_source_manifest.json')['files']:
                if sha(Path(row['path']))!=row['sha256']:raise ValueError('Build input drift')
    def replay(v):
        d=out/v/'imatmul';d.mkdir(parents=True)
        cmd=[str((a.campaign/v/'sim/simv').resolve()),'-no_save','-l','run.vcs.log',
             f'+PRELOAD={(out/"imatmul.elf").resolve()}','+TESTCASE=imatmul','+NO_FSDB','+ntb_random_seed=1']
        (d/'inputs.json').write_text(json.dumps(dict(command=cmd,timeout_seconds=7200,
            elf_sha256=sha(out/'imatmul.elf'),image=read(a.campaign/v/'image.json')),indent=2)+'\n')
        with (d/'console.log').open('w') as log:
            rc=subprocess.run(cmd,cwd=d,stdout=log,stderr=subprocess.STDOUT,timeout=7200).returncode
        log=(d/'console.log').read_text(errors='replace')
        activity=re.findall(r'MUL_SOC_ACTIVITY .*accepted=(\d+),(\d+),(\d+),(\d+) completed=(\d+),(\d+),(\d+),(\d+) blocked=(\d+)',log)
        good=rc==0 and 'Core Test *** SUCCESS ***' in log and not re.search(r'Fatal:|Error:|\bFAILED\b',log)
        good=good and log.count('MUL_SOC_MODE '+v)==4 and len(activity)==4
        good=good and all(r[:4]==r[4:8] for r in activity) and sum(int(x) for r in activity for x in r[:4])>0
        row=dict(case='imatmul',variant=v,status='PASS' if good else 'FAIL',returncode=rc,activity=activity,
                 evidence=str(d),regions=app_regions('imatmul',log) if good else {})
        (d/'result.json').write_text(json.dumps(row,indent=2)+'\n')
        return row
    try:
        state('WAITING_ORIGINAL_CAMPAIGN')
        deadline=time.monotonic()+7200
        while read(a.campaign/'status.json')['state'] not in ('INITIAL_MATRIX_PASS','CASE_FAILED','ERROR'):
            if time.monotonic()>deadline:raise ValueError('Original wait bound')
            time.sleep(60)
        check_inputs()
        original=read(a.campaign/'status.json'); rows=read(a.campaign/'results.json')
        replay_rows=[]
        if original['state']!='INITIAL_MATRIX_PASS':
            bad=[r for r in rows if r['status']!='PASS']
            if original.get('case')!='imatmul' or len(rows)!=36 or not bad or any(r['case']!='imatmul' or r['returncode']!=124 for r in bad):
                raise ValueError('Failure is not exclusively bounded matrix timeout')
            # A timeout may coexist with an earlier printed error. Do not
            # suppress such failures by increasing the execution bound.
            for v in ('baseline','shared'):
                log=(a.campaign/v/'cases/imatmul/console.log').read_text(errors='replace')
                if re.search(r'Fatal:|Error:|\bFAILED\b',log):raise ValueError('Matrix log contains actual failure')
            shutil.copy2(a.campaign/'inputs/imatmul',out/'imatmul.elf')
            save('replay_reason.json',dict(original_status=original,
                reason='30-minute wall bound insufficient for unchanged 128x128 matrix sweep',
                rtl_changed=False,image_changed=False,elf_changed=False,new_wall_bound_seconds=7200))
            state('MATRIX_REPLAY_RUNNING')
            with ThreadPoolExecutor(max_workers=2) as pool:replay_rows=list(pool.map(replay,('baseline','shared')))
            if any(r['status']!='PASS' for r in replay_rows):raise ValueError('Matrix replay failed')
        check_inputs()
        chosen=[r for r in rows if not(replay_rows and r['case']=='imatmul')]+replay_rows
        if len(chosen)!=36 or any(r['status']!='PASS' for r in chosen):raise ValueError('Missing functional result')
        comparisons=[]
        expected=set(read(a.campaign/'elf_hashes.json'))
        if {r['case'] for r in chosen}!=expected:raise ValueError('Case identity mismatch')
        for name in sorted(expected):
            pair=[next(r for r in chosen if r['variant']==v and r['case']==name) for v in ('baseline','shared')]
            if [r[:8] for r in pair[0]['activity']]!=[r[:8] for r in pair[1]['activity']]:raise ValueError('Workload mismatch: '+name)
            if name not in ('dotproduct','imatmul'):continue
            regions=[]
            for v,row in zip(('baseline','shared'),pair):
                logpath=(Path(row['evidence']) if 'evidence' in row else a.campaign/v/'cases'/name)/'console.log'
                regions.append(app_regions(name,logpath.read_text(errors='replace')))
            if regions[0].keys()!=regions[1].keys():raise ValueError('Timing shape mismatch')
            if name=='imatmul' and set(regions[0])!={'n4','n8','n16','n32','n64','n128'}:
                raise ValueError('Full matrix sweep not completed')
            blocked=[sum(int(x[8]) for x in r['activity']) for r in pair]
            for region,b in regions[0].items():comparisons.append(dict(app=name,region=region,
                baseline_cycles=b,shared_cycles=regions[1][region],delta_cycles=regions[1][region]-b,
                baseline_blocked=blocked[0],shared_blocked=blocked[1]))
        if read(a.mixed/'status.json')['state']!='PASS':raise ValueError('Mixed test missing')
        mixed=read(a.mixed/'results.json')
        if len(mixed)!=2 or any(r['status']!='PASS' for r in mixed):raise ValueError('Mixed test incomplete')
        state('WAITING_LLAMA')
        deadline=time.monotonic()+4200
        while read(a.llama/'status.json')['state']=='RUNNING':
            if time.monotonic()>deadline:raise ValueError('Llama wait bound')
            time.sleep(60)
        llm=read(a.llama/'report.json')
        if llm['functional_status']!='PASS':raise ValueError('Llama functional failure')
        for f,h in read(a.llama/'source-pins.json').items():
            if sha(Path(f))!=h:raise ValueError('Llama input drift')
        clean=all(r['delta_cycles']<=0 and r['shared_blocked']<=r['baseline_blocked'] for r in comparisons)
        clean=clean and llm['performance_status']=='PASS'
        clean=clean and mixed[0]['hw_cycles']==mixed[1]['hw_cycles']
        report=dict(functional_status='PASS',performance_status='PASS' if clean else 'REGRESSION',
            matrix_replayed=bool(replay_rows),original_campaign_status=original,
            apps=comparisons,mixed=mixed,llama=llm,
            scope='Complete SoC shared integer multiplier acceptance; not physical or FPGA signoff')
        save('report.json',report)
        state('COMPLETE',functional_status=report['functional_status'],performance_status=report['performance_status'])
    except Exception as exc:
        state('ERROR',reason=str(exc));raise


if __name__=='__main__':main()
