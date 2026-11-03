#!/usr/bin/env python3
"""Measure removal of debug visibility, then finish the unchanged matrix ELF.

No RTL edits. Preserve old evidence; supersede the slow replay only after a
paired control reproduces its target timing and demonstrates faster simulation.
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
    p.add_argument('llama',type=Path);p.add_argument('slow',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--prepared',type=Path,help='Reuse a completed fast build and checked control logs')
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    def save(path,obj):
        temp=path.with_suffix('.tmp');temp.write_text(json.dumps(obj,indent=2)+'\n');temp.replace(path)
    def state(value,**extra):save(out/'status.json',dict(state=value,**extra))
    def check_old():
        for f,h in read(a.campaign/'source-pins.json').items():
            if sha(Path(f))!=h:raise ValueError('Source drift: '+f)
        for v in ('baseline','shared'):
            for row in read(a.campaign/v/'sim/vcs_source_manifest.json')['files']:
                if sha(Path(row['path']))!=row['sha256']:raise ValueError('Build source drift')
    def build(v):
        d=out/v;d.mkdir()
        if a.prepared:
            source=a.prepared.resolve()/v
            identity=read(source/'image.json')
            if sha(source/'sim/simv')!=identity['sha256']:raise ValueError('Prepared image drift')
            if sha(source/'sim/vcs_source_manifest.json')!=identity['source_manifest_sha256']:raise ValueError('Prepared manifest drift')
            (d/'sim').symlink_to(source/'sim',target_is_directory=True)
            shutil.copy2(source/'command.json',d/'command.json')
            shutil.copy2(source/'image.json',d/'image.json')
            manifest=read(source/'sim/vcs_source_manifest.json')
            for r in manifest['files']:
                if sha(Path(r['path']))!=r['sha256']:raise ValueError('Prepared source drift')
            return {r['path']:r['sha256'] for r in manifest['files'] if not Path(r['path']).is_relative_to(a.prepared.resolve())}
        command=read(a.campaign/v/'command.json')['command']
        cmd=[s.replace(str(a.campaign/v),str(d)) for s in command]
        opt=next(s for s in cmd if s.startswith('SIMULATOR_OPT='))
        replacement=opt.replace(' -kdb','').replace(' -debug_access+all','')
        if replacement==opt:raise ValueError('Expected original debug options')
        cmd[cmd.index(opt)]=replacement
        save(d/'command.json',dict(command=cmd,only_semantic_change='none; disable debug visibility'))
        with (d/'build.log').open('w') as log:
            subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=7200)
        manifest=read(d/'sim/vcs_source_manifest.json')
        save(d/'image.json',dict(sha256=sha(d/'sim/simv'),source_manifest_sha256=sha(d/'sim/vcs_source_manifest.json')))
        return {r['path']:r['sha256'] for r in manifest['files'] if not Path(r['path']).is_relative_to(out)}
    def run(v,case,elf,timeout):
        d=out/v/case;d.mkdir()
        cmd=[str(out/v/'sim/simv'),'-no_save','-l','run.vcs.log',f'+PRELOAD={elf}',
             f'+TESTCASE={case}','+NO_FSDB','+ntb_random_seed=1']
        save(d/'inputs.json',dict(command=cmd,elf_sha256=sha(elf),timeout_seconds=timeout))
        started=time.monotonic()
        with (d/'console.log').open('w') as log:
            rc=subprocess.run(cmd,cwd=d,stdout=log,stderr=subprocess.STDOUT,timeout=timeout).returncode
        wall=time.monotonic()-started;text=(d/'console.log').read_text(errors='replace')
        if rc or 'Core Test *** SUCCESS ***' not in text or re.search(r'Fatal:|Error:|\bFAILED\b',text):
            raise ValueError(v+'/'+case+': functional failure')
        activity=re.findall(r'MUL_SOC_ACTIVITY .*accepted=(\d+),(\d+),(\d+),(\d+) completed=(\d+),(\d+),(\d+),(\d+) blocked=(\d+)',text)
        if text.count('MUL_SOC_MODE '+v)!=4 or len(activity)!=4 or any(r[:4]!=r[4:8] for r in activity):
            raise ValueError('Missing/unbalanced real multiplier activity')
        if not sum(int(x) for r in activity for x in r[:4]):raise ValueError('No actual multiplication')
        cpu=re.findall(r'CPU Time:\s*([\d.]+) seconds',text)
        finish=re.findall(r'\$finish at simulation time\s+(\d+)',text)
        if len(cpu)!=1 or len(finish)!=1:raise ValueError('Missing simulator metrics')
        result=dict(variant=v,activity=activity,cpu_seconds=float(cpu[0]),wall_seconds=wall,finish_time=finish[0])
        save(d/'result.json',result)
        return result
    try:
        check_old();state('BUILDING_FAST_PAIR')
        for name in ('rv64uv-ara-vmul','imatmul'):
            expected=read(a.campaign/'elf_hashes.json')[name]
            source=a.campaign/'inputs'/name
            if sha(source)!=expected:raise ValueError('ELF drift')
            shutil.copy2(source,out/(name+'.elf'))
        with ThreadPoolExecutor(max_workers=2) as pool:manifests=list(pool.map(build,('baseline','shared')))
        if manifests[0]!=manifests[1]:raise ValueError('Fast source mismatch')
        original={r['path']:r['sha256'] for r in read(a.campaign/'baseline/sim/vcs_source_manifest.json')['files']
                  if not Path(r['path']).is_relative_to(a.campaign)}
        if manifests[0]!=original:raise ValueError('Fast source differs from accepted RTL')
        state('CONTROL_RUNNING')
        if a.prepared:
            controls=[]
            for v in ('baseline','shared'):
                d=a.prepared.resolve()/v/'rv64uv-ara-vmul'
                log=(d/'console.log').read_text(errors='replace')
                r=read(d/'result.json');inputs=read(d/'inputs.json')
                if inputs['elf_sha256']!=sha(out/'rv64uv-ara-vmul.elf'):raise ValueError('Control ELF drift')
                if 'Core Test *** SUCCESS ***' not in log or re.search(r'Fatal:|Error:|\bFAILED\b',log):raise ValueError('Control log invalid')
                observed=re.findall(r'MUL_SOC_ACTIVITY .*accepted=(\d+),(\d+),(\d+),(\d+) completed=(\d+),(\d+),(\d+),(\d+) blocked=(\d+)',log)
                if [list(x) for x in observed]!=r['activity']:raise ValueError('Control report differs from log')
                controls.append(r)
        else:
            with ThreadPoolExecutor(max_workers=2) as pool:
                controls=list(pool.map(lambda v:run(v,'rv64uv-ara-vmul',out/'rv64uv-ara-vmul.elf',600),('baseline','shared')))
        gain=[]
        for v,r in zip(('baseline','shared'),controls):
            old=(a.campaign/v/'cases/rv64uv-ara-vmul/console.log').read_text(errors='replace')
            if re.findall(r'\$finish at simulation time\s+(\d+)',old)!=[r['finish_time']]:
                raise ValueError('Control target execution timing changed')
            old_activity=next(x for x in read(a.campaign/'results.json') if x['variant']==v and x['case']=='rv64uv-ara-vmul')['activity']
            if [list(x) for x in r['activity']]!=old_activity:raise ValueError('Control activity changed')
            old_cpu=float(re.findall(r'CPU Time:\s*([\d.]+) seconds',old)[0])
            gain.append(old_cpu/r['cpu_seconds'])
        save(out/'control.json',dict(results=controls,simulation_cpu_speedup=gain,target_timing_identical=True))
        if min(gain)<1.2:
            state('NO_MEASURED_GAIN',simulation_cpu_speedup=gain);return
        # The original accepted campaign is already terminal. Only stop our
        # expensive replay, never unrelated services or simulators.
        slow=read(a.slow/'status.json')
        if slow['state']=='MATRIX_REPLAY_RUNNING':
            subprocess.run(['systemctl','--user','stop','shared-mul-soc-complete-20261103-01.service'],check=True)
            save(a.slow/'superseded.json',dict(reason='Measured fast simulation with unchanged RTL/control target cycles',
                successor=str(out),previous_status=slow,simulation_cpu_speedup=gain))
            save(a.slow/'status.json',dict(state='SUPERSEDED',successor=str(out)))
        elif slow['state']=='COMPLETE':
            state('SLOW_ALREADY_COMPLETE',evidence=str(a.slow));return
        state('MATRIX_RUNNING',simulation_cpu_speedup=gain)
        with ThreadPoolExecutor(max_workers=2) as pool:
            matrix=list(pool.map(lambda v:run(v,'imatmul',out/'imatmul.elf',10800),('baseline','shared')))
        if [r[:8] for r in matrix[0]['activity']]!=[r[:8] for r in matrix[1]['activity']]:raise ValueError('Matrix workload differs')
        comparisons=[]
        for case in ('dotproduct','imatmul'):
            logs=[(out/v/'imatmul/console.log' if case=='imatmul' else a.campaign/v/'cases'/case/'console.log').read_text(errors='replace') for v in ('baseline','shared')]
            regions=[app_regions(case,t) for t in logs]
            if regions[0].keys()!=regions[1].keys():raise ValueError('Application shape mismatch')
            if case=='imatmul' and set(regions[0])!={'n4','n8','n16','n32','n64','n128'}:raise ValueError('Matrix scale incomplete')
            for region,b in regions[0].items():comparisons.append(dict(app=case,region=region,
                baseline_cycles=b,shared_cycles=regions[1][region],delta_cycles=regions[1][region]-b))
        check_old()
        old_rows=read(a.campaign/'results.json')
        if len([r for r in old_rows if r['status']=='PASS' and r['case']!='imatmul'])!=34:raise ValueError('Original ISA/dot evidence incomplete')
        mixed=read(a.mixed/'results.json');llama=read(a.llama/'report.json')
        if read(a.mixed/'status.json')['state']!='PASS' or llama['functional_status']!='PASS':raise ValueError('Missing remaining acceptance')
        blocked=[sum(int(x[8]) for x in r['activity']) for r in matrix]
        clean=all(x['delta_cycles']<=0 for x in comparisons) and blocked[1]<=blocked[0] and llama['performance_status']=='PASS'
        clean=clean and mixed[0]['hw_cycles']==mixed[1]['hw_cycles']
        report=dict(functional_status='PASS',performance_status='PASS' if clean else 'REGRESSION',
            compiler_change='debug visibility disabled identically; control target timing identical',
            simulation_cpu_speedup=gain,apps=comparisons,matrix_activity=matrix,matrix_blocked=blocked,
            original_evidence=str(a.campaign),mixed=mixed,llama=llama,
            scope='Complete SoC integer multiplier acceptance; not physical/FPGA signoff')
        save(out/'report.json',report);state('COMPLETE',functional_status='PASS',performance_status=report['performance_status'])
    except Exception as exc:
        state('ERROR',reason=str(exc));raise


if __name__=='__main__':main()
