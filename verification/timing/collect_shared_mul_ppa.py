#!/usr/bin/env python3
"""Collect only completed, hash-verified local multiplier DC results."""
import argparse
import hashlib
import json
import math
import time
from pathlib import Path

def collect(root):
    rows={}
    manifests={}
    for name in ('baseline','shared'):
        d=root/name
        status=json.loads((d/'status.json').read_text())
        if status['state']!='PASS':
            raise ValueError(f'{name}: {status["state"]}; comparison is not complete')
        manifest=json.loads((d/'manifest.json').read_text())
        manifests[name]=manifest
        for file,sha in manifest['hashes'].items():
            if hashlib.sha256((d/file).read_bytes()).hexdigest()!=sha:
                raise ValueError(f'{name}: changed input {file}')
        rows[name]={k:float(v) for k,v in (l.split('\t') for l in (d/'metrics.tsv').read_text().splitlines())}
        for key in ('area_um2','clk_i_slack_ns','clk_i_arrival_ns'):
            if key not in rows[name] or not math.isfinite(rows[name][key]):
                raise ValueError(f'{name}: invalid metric {key}')
        if rows[name]['area_um2'] <= 0:
            raise ValueError(f'{name}: nonpositive cell area')
    for key in ('hashes','period_ns','setup_uncertainty_ns'):
        if manifests['baseline'][key]!=manifests['shared'][key]:
            raise ValueError(f'Comparison mismatch: {key}')
    b,s=rows['baseline'],rows['shared']
    result={'scope':'local_integer_bank_not_soc','period_ns':1,'setup_uncertainty_ns':0.15,
            'results':rows,'area_reduction_percent':100*(1-s['area_um2']/b['area_um2']),
            'clk_i_slack_delta_ns':s['clk_i_slack_ns']-b['clk_i_slack_ns'],
            'power_measured':False,'application_cycles_measured':False}
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path)
    p.add_argument('--wait',action='store_true',help='Background collector: wait for both bounded workers')
    a=p.parse_args()
    if a.wait:
        bounds=[json.loads((a.directory/n/'manifest.json').read_text()).get('timeout_seconds',3600)
                for n in ('baseline','shared')]
        deadline=time.monotonic()+max(bounds)+600
        while True:
            states=[json.loads((a.directory/n/'status.json').read_text())['state'] for n in ('baseline','shared')]
            if any(s=='FAIL' for s in states):
                raise SystemExit('A DC worker failed; inspect status.json and dc.log. No comparison published.')
            if states==['PASS','PASS']:break
            if time.monotonic()>deadline:raise SystemExit('Timed out waiting for bounded DC workers')
            time.sleep(30)
    result=collect(a.directory.resolve())
    text=json.dumps(result,indent=2)+'\n'
    (a.directory/'comparison.json').write_text(text)
    rows=result['results']
    csv='variant,area_um2,clk_i_slack_ns,clk_i_arrival_ns\n'
    for name in ('baseline','shared'):
        r=rows[name];csv+=f'{name},{r["area_um2"]},{r["clk_i_slack_ns"]},{r["clk_i_arrival_ns"]}\n'
    (a.directory/'comparison.csv').write_text(csv)
    print(text)
