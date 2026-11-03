#!/usr/bin/env python3
"""Compare the existing real-data llama micro ELF on both verified SoC images."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

EXPECTED={
    'quantize_f32_to_q8_k_k1536','quantize_f32_to_q8_k_k8960',
    'q4_k_x_q8_k_dot_n1536_nrc1','q4_k_x_q8_k_dot_n8960_nrc1',
    'q6_k_x_q8_k_dot_n1536_nrc1','q6_k_x_q8_k_dot_n8960_nrc1'}


def parse(log):
    if 'Q4_K_M micro verification: PASS (0/6 failed)' not in log:
        raise ValueError('Missing complete independent micro result checks')
    rows=re.findall(r'^MICRO (\S+) PASS cycles=(\d+)([^\n]*)',log,re.M)
    if len(rows)!=6 or {r[0] for r in rows}!=EXPECTED:
        raise ValueError('Expected six unique checked timing regions')
    if any(int(r[1])<=0 for r in rows):raise ValueError('Nonpositive timing')
    return {n:dict(cycles=int(c),detail=d.strip()) for n,c,d in rows}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('campaign',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[2]
    sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
    def save(name,obj):
        temp=out/(name+'.tmp');temp.write_text(json.dumps(obj,indent=2)+'\n');temp.replace(out/name)
    try:
        shutil.copy2(root/'apps/bin/llama_q4km_micro',out/'input.elf')
        snapshots={str(f):sha(f) for f in [Path(__file__).resolve(),out/'input.elf',
            root/'apps/llama_q4km_micro/main.c',root/'apps/llama_q4km_micro/data.S']}
        save('source-pins.json',snapshots)
        save('status.json',dict(state='RUNNING'))
        def run(v):
            d=out/v;d.mkdir();image=a.campaign/v/'sim/simv'
            ident=json.loads((a.campaign/v/'image.json').read_text())
            if sha(image)!=ident['simv_sha256']:raise ValueError('Image drift')
            subprocess.run([sys.executable,'-m','ara_verify.vcs_source_manifest','--output',
                str(a.campaign/v/'sim/vcs_source_manifest.json'),'--check'],cwd=root/'verification',check=True)
            cmd=[str(image.resolve()),'-no_save','-l','run.vcs.log',f'+PRELOAD={out}/input.elf',
                 '+TESTCASE=llama_q4km_micro','+NO_FSDB','+ntb_random_seed=1']
            (d/'inputs.json').write_text(json.dumps(dict(command=cmd,elf_sha256=sha(out/'input.elf'),image=ident),indent=2)+'\n')
            with (d/'console.log').open('w') as log:
                rc=subprocess.run(cmd,cwd=d,stdout=log,stderr=subprocess.STDOUT,timeout=3600).returncode
            text=(d/'console.log').read_text(errors='replace')
            if rc or 'Core Test *** SUCCESS ***' not in text or re.search(r'Fatal:|Error:|\bFAIL(?:ED)?\b',text):
                raise ValueError(v+': firmware did not pass')
            activities=re.findall(r'MUL_SOC_ACTIVITY .*accepted=(\d+),(\d+),(\d+),(\d+) completed=(\d+),(\d+),(\d+),(\d+) blocked=(\d+)',text)
            if text.count('MUL_SOC_MODE '+v)!=4 or len(activities)!=4:
                raise ValueError('Missing actual hardware activity')
            if any(r[:4]!=r[4:8] for r in activities) or not sum(int(x) for r in activities for x in r[:4]):
                raise ValueError('Unbalanced or absent multiply activity')
            result=dict(variant=v,status='PASS',regions=parse(text),activity=activities)
            (d/'result.json').write_text(json.dumps(result,indent=2)+'\n')
            return result
        with ThreadPoolExecutor(max_workers=2) as pool:b,s=list(pool.map(run,('baseline','shared')))
        if [r[:8] for r in b['activity']]!=[r[:8] for r in s['activity']]:raise ValueError('Workload differs')
        comparison=[]
        for name in sorted(EXPECTED):
            br,sr=b['regions'][name],s['regions'][name]
            if br['detail']!=sr['detail']:raise ValueError('Numerical output changed: '+name)
            comparison.append(dict(region=name,baseline_cycles=br['cycles'],shared_cycles=sr['cycles'],
                                   delta_cycles=sr['cycles']-br['cycles'],detail=br['detail']))
        for f,h in snapshots.items():
            if sha(Path(f))!=h:raise ValueError('Input drift')
        blocked=[sum(int(r[8]) for r in result['activity']) for result in (b,s)]
        report=dict(functional_status='PASS',regions=comparison,blocked=blocked,
                    performance_status='PASS' if all(r['delta_cycles']<=0 for r in comparison) and blocked[1]<=blocked[0] else 'REGRESSION')
        save('report.json',report);save('status.json',dict(state='COMPLETE',**report))
    except Exception as exc:
        save('status.json',dict(state='ERROR',reason=str(exc)));raise


if __name__=='__main__':main()
