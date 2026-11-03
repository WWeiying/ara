#!/usr/bin/env python3
"""Final raw-log/hash audit; does not rely solely on supervisor PASS labels."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from collect_shared_mul_soc import app_regions
from run_shared_mul_llama_soc import parse as micro_regions


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('campaign',type=Path);p.add_argument('mixed',type=Path)
    p.add_argument('llama',type=Path);p.add_argument('fast',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();root=Path(__file__).resolve().parents[2]
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    evidence={}
    def digest(f):return hashlib.sha256(f.read_bytes()).hexdigest()
    def read(f):
        evidence[str(f.resolve())]=digest(f)
        return json.loads(f.read_text())
    def require(condition,why):
        if not condition:raise ValueError(why)
    def logcheck(folder,variant):
        f=folder/'console.log';evidence[str(f.resolve())]=digest(f)
        log=f.read_text(errors='replace')
        require('Core Test *** SUCCESS ***' in log,'No successful firmware exit: '+str(f))
        require(not re.search(r'Fatal:|Error:|\bFAIL(?:ED)?\b',log),'Reported failure: '+str(f))
        require(log.count('MUL_SOC_MODE '+variant)==4,'Wrong compiled mode')
        rows=re.findall(r'MUL_SOC_ACTIVITY .*accepted=(\d+),(\d+),(\d+),(\d+) completed=(\d+),(\d+),(\d+),(\d+) blocked=(\d+)',log)
        require(len(rows)==4 and all(r[:4]==r[4:8] for r in rows),'Unbalanced Lane counters')
        require(sum(int(x) for r in rows for x in r[:4])>0,'No multiply executed')
        command=read(folder/'inputs.json') if (folder/'inputs.json').exists() else read(folder/'command.json')
        elf=Path(next(s.split('=',1)[1] for s in command['command'] if s.startswith('+PRELOAD=')))
        require(digest(elf)==command['elf_sha256'],'Executed ELF drift')
        evidence[str(elf.resolve())]=digest(elf)
        return log,rows
    try:
        selection=read(root/'verification/timing/shared_mul_selected.json')
        for f,h in selection['source_sha256'].items():require(digest(root/f)==h,'Selected RTL drift')
        for f,h in read(a.campaign/'source-pins.json').items():require(digest(Path(f))==h,'Source drift')
        for v in ('baseline','shared'):
            for image_root in (a.campaign,a.fast):
                manifest=read(image_root/v/'sim/vcs_source_manifest.json')
                for row in manifest['files']:require(digest(Path(row['path']))==row['sha256'],'Build input drift')
                image=read(image_root/v/'image.json')
                require(digest(image_root/v/'sim/simv')==image.get('simv_sha256',image.get('sha256')),'Image drift')
        names={'rv64uv-ara-'+n for n in ('vmul','vmulh','vmulhu','vmulhsu','vsmul',
            'vmacc','vmadd','vnmsac','vnmsub','vwmul','vwmulu','vwmulsu','vwmacc','vwmaccu','vwmaccsu','vwmaccus')}
        results=read(a.campaign/'results.json')
        for name in sorted(names):
            pair=[]
            for v in ('baseline','shared'):
                recorded=[r for r in results if r['case']==name and r['variant']==v]
                require(len(recorded)==1 and recorded[0]['status']=='PASS' and recorded[0]['returncode']==0,'ISA record incomplete')
                log,activity=logcheck(a.campaign/v/'cases'/name,v)
                require('PASSED' in log,'Missing ISA golden checks')
                pair.append(activity)
            require(pair[0]==pair[1],'ISA workload/backpressure differs: '+name)
        applications=[]
        for name in ('dotproduct','imatmul'):
            logs=[];activities=[]
            for v in ('baseline','shared'):
                folder=a.fast/v/'imatmul' if name=='imatmul' else a.campaign/v/'cases'/name
                log,activity=logcheck(folder,v);logs.append(log);activities.append(activity)
            require(activities[0]==activities[1],'Application workload/backpressure differs')
            regions=[app_regions(name,t) for t in logs]
            require(regions[0]==regions[1],'Application region cycles differ')
            if name=='imatmul':require(set(regions[0])=={'n4','n8','n16','n32','n64','n128'},'Incomplete matrix sweep')
            else:require(len(regions[0])==9,'Incomplete dotproduct sweep')
            applications.extend(dict(app=name,region=n,baseline_cycles=c,shared_cycles=c) for n,c in regions[0].items())
        mixed=[]
        for v in ('baseline','shared'):mixed.append(logcheck(a.mixed/v,v))
        require(mixed[0][1]==mixed[1][1],'Mixed activity/backpressure differs')
        mixed_cycles=[re.findall(r'\[hw-cycles\]:\s*(\d+)',t[0]) for t in mixed]
        require(mixed_cycles==[['19256'],['19256']],'Mixed target cycles differ')
        llama=[]
        for v in ('baseline','shared'):
            log,activity=logcheck(a.llama/v,v);llama.append((micro_regions(log),activity))
        require(llama[0]==llama[1],'Llama cycles/numerics/activity differ')
        report=dict(status='PASS',selected=selection['selection'],isa_test_pairs=len(names),
            mixed_sew_phases=96,mixed_cycles=19256,applications=applications,
            llama=llama[0][0],raw_logs_checked=True,inputs_and_images_checked=True,
            scope='Selected shared multiplier full SoC functional/performance regression, not physical/FPGA signoff')
        (out/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
        (out/'evidence_hashes.json').write_text(json.dumps(evidence,indent=2)+'\n')
        print(json.dumps(report,indent=2))
    except Exception as exc:
        (out/'failed.json').write_text(json.dumps(dict(reason=str(exc)),indent=2)+'\n');raise


if __name__=='__main__':main()
