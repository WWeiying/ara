#!/usr/bin/env python3
"""Run the mixed-SEW firmware against the complete SoC pair after build."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('campaign',type=Path);p.add_argument('elf',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args(); out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[2]
    sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
    def save(name,data):
        temp=out/(name+'.tmp');temp.write_text(json.dumps(data,indent=2)+'\n');temp.replace(out/name)
    try:
        save('status.json',dict(state='WAITING_FOR_IMAGES'))
        deadline=time.monotonic()+7200
        while not all((a.campaign/v/'image.json').is_file() for v in ('baseline','shared')):
            campaign=json.loads((a.campaign/'status.json').read_text())
            if campaign['state']=='ERROR':raise RuntimeError('SoC pair build failed')
            if time.monotonic()>deadline:raise RuntimeError('Image wait bound reached')
            time.sleep(30)
        def run(v):
            d=out/v;d.mkdir(); sim=a.campaign/v/'sim/simv'
            image=json.loads((a.campaign/v/'image.json').read_text())
            if sha(sim)!=image['simv_sha256']:raise RuntimeError('Image changed')
            manifest=a.campaign/v/'sim/vcs_source_manifest.json'
            subprocess.run([sys.executable,'-m','ara_verify.vcs_source_manifest','--output',str(manifest),'--check'],
                           cwd=root/'verification',check=True)
            cmd=[str(sim.resolve()),'-no_save','-l','run.vcs.log',f'+PRELOAD={a.elf.resolve()}',
                 '+TESTCASE=shared_mul_mixed_96','+NO_FSDB','+ntb_random_seed=1']
            (d/'inputs.json').write_text(json.dumps(dict(command=cmd,elf_sha256=sha(a.elf),
                image=image,source_manifest_sha256=sha(manifest)),indent=2)+'\n')
            with (d/'console.log').open('w') as log:
                rc=subprocess.run(cmd,cwd=d,stdout=log,stderr=subprocess.STDOUT,timeout=1800).returncode
            text=(d/'console.log').read_text(errors='replace')
            activities=re.findall(r'MUL_SOC_ACTIVITY .*accepted=(\d+),(\d+),(\d+),(\d+) completed=(\d+),(\d+),(\d+),(\d+) blocked=(\d+)',text)
            passed=rc==0 and 'Core Test *** SUCCESS ***' in text and not re.search(r'Fatal:|Error:|\bFAILED\b',text)
            passed=passed and text.count('MUL_SOC_MODE '+v)==4 and len(activities)==4
            passed=passed and all(all(int(x)>0 for x in r[:4]) and r[:4]==r[4:8] for r in activities)
            return dict(variant=v,status='PASS' if passed else 'FAIL',activity=activities,
                        hw_cycles=re.findall(r'\[hw-cycles\]:\s*(\d+)',text),returncode=rc)
        save('status.json',dict(state='RUNNING'))
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,('baseline','shared')))
        save('results.json',results)
        save('status.json',dict(state='PASS' if all(r['status']=='PASS' for r in results) else 'FAIL'))
    except Exception as exc:
        save('status.json',dict(state='ERROR',reason=str(exc)));raise


if __name__=='__main__':main()
