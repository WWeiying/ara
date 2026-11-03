#!/usr/bin/env python3
"""Strict, read-only SoC acceptance and application cycle comparison."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time


def text(path): return path.read_text(errors='replace')


def app_regions(app,log):
    if app=='dotproduct':
        pattern=r'Calulating (\d+)b dotp with vectors with length = (\d+)\s+Vector runtime: (\d+)\s+Scalar runtime: (\d+)'
        rows=re.findall(pattern,log)
        if not rows or 'SUCCESS.' not in log: raise ValueError('Missing checked DOTP regions')
        if {int(r[0]) for r in rows}!={8,16,32,64}: raise ValueError('Incomplete DOTP SEW coverage')
        result={f'e{sew}_avl{n}':int(cyc) for sew,n,cyc,_ in rows}
    elif app=='imatmul':
        pattern=r'Calculating a \((\d+) x (\d+)\) x \((\d+) x (\d+)\) matrix multiplication\.\.\.(.*?)The execution took (\d+) cycles\.'
        rows=re.findall(pattern,log,re.S)
        if not rows or 'Verifying result...' not in log or 'Passed.' not in log:
            raise ValueError('Missing checked IMATMUL result')
        if any(not(r[0]==r[1]==r[2]==r[3]) for r in rows):raise ValueError('Unexpected matrix shape')
        result={f'n{r[0]}':int(r[5]) for r in rows}
    else:raise ValueError(app)
    if len(result)!=len(rows) or any(c<=0 for c in result.values()):raise ValueError('Invalid timing regions')
    return result


def audit(campaign,mixed):
    state=json.loads((campaign/'status.json').read_text())
    if state['state']!='INITIAL_MATRIX_PASS':raise ValueError('Initial matrix is not complete')
    if json.loads((mixed/'status.json').read_text())['state']!='PASS':raise ValueError('Mixed-SEW test not PASS')
    results=json.loads((campaign/'results.json').read_text())
    if len(results)!=36 or any(r['status']!='PASS' for r in results):raise ValueError('Incomplete matrix')
    sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
    for f,expected in json.loads((campaign/'source-pins.json').read_text()).items():
        if sha(Path(f))!=expected:raise ValueError('Source drift: '+f)
    elves=json.loads((campaign/'elf_hashes.json').read_text())
    for name,expected in elves.items():
        if sha(campaign/'inputs'/name)!=expected:raise ValueError('ELF drift')
    for v in ('baseline','shared'):
        image=campaign/v/'sim/simv'
        if sha(image)!=json.loads((campaign/v/'image.json').read_text())['simv_sha256']:
            raise ValueError('Image drift')
        manifest=json.loads((campaign/v/'sim/vcs_source_manifest.json').read_text())
        for row in manifest['files']:
            if sha(Path(row['path']))!=row['sha256']:raise ValueError('Build input drift')
    comparisons=[]
    for name in elves:
        pair=[next(r for r in results if r['variant']==v and r['case']==name) for v in ('baseline','shared')]
        if [r[:8] for r in pair[0]['activity']] != [r[:8] for r in pair[1]['activity']]:
            raise ValueError('Instruction workload differs: '+name)
        if name not in ('dotproduct','imatmul'):continue
        regions=[app_regions(name,text(campaign/v/'cases'/name/'console.log')) for v in ('baseline','shared')]
        if regions[0].keys()!=regions[1].keys():raise ValueError('Region mismatch')
        blocked=[sum(int(row[8]) for row in r['activity']) for r in pair]
        for region,b in regions[0].items():
            s=regions[1][region]
            comparisons.append(dict(app=name,region=region,baseline_cycles=b,shared_cycles=s,
                delta_cycles=s-b,shared_over_baseline=s/b,
                whole_run_baseline_blocked=blocked[0],whole_run_shared_blocked=blocked[1]))
    mixed_rows=json.loads((mixed/'results.json').read_text())
    if len(mixed_rows)!=2 or any(r['status']!='PASS' for r in mixed_rows):raise ValueError('Mixed incomplete')
    b,s=mixed_rows
    if b['variant']!='baseline' or s['variant']!='shared':raise ValueError('Mixed pair identity')
    if [r[:8] for r in b['activity']] != [r[:8] for r in s['activity']]:raise ValueError('Mixed workload differs')
    no_regression=all(r['delta_cycles']<=0 and r['whole_run_shared_blocked']<=r['whole_run_baseline_blocked'] for r in comparisons)
    return dict(functional_status='PASS',performance_status='PASS' if no_regression else 'REGRESSION',
        scope='complete SoC integer multiply integration and checked dotproduct/imatmul; not physical/FPGA signoff',
        apps=comparisons,mixed=mixed_rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('campaign',type=Path);p.add_argument('mixed',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--wait',action='store_true')
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    try:
        if a.wait:
            deadline=time.monotonic()+21600
            while True:
                c=json.loads((a.campaign/'status.json').read_text())['state']
                m=json.loads((a.mixed/'status.json').read_text())['state']
                if c in ('ERROR','CASE_FAILED') or m in ('ERROR','FAIL'):raise ValueError(f'Failed worker: {c}/{m}')
                if c=='INITIAL_MATRIX_PASS' and m=='PASS':break
                if time.monotonic()>deadline:raise ValueError('Collector wait bound reached')
                time.sleep(30)
        report=audit(a.campaign,a.mixed)
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        lines=['app,region,baseline_cycles,shared_cycles,delta_cycles,shared_over_baseline']
        for r in report['apps']:
            lines.append(','.join(str(r[k]) for k in lines[0].split(',')))
        (out/'application_cycles.csv').write_text('\n'.join(lines)+'\n')
        print(json.dumps(report,indent=2),flush=True)
    except Exception as exc:
        (out/'audit_failed.json').write_text(json.dumps(dict(reason=str(exc)),indent=2)+'\n')
        raise


if __name__=='__main__':main()
