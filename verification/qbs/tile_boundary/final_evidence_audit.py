#!/usr/bin/env python3
"""Rehash the finite optimization-round evidence; never rerun simulations."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'verification/out'
OLD='576304613df34547c7d80b04739a4a0164febd719cfcbc463d6465db6d966978'
NEW='999d250d97945c09c5034ce9924e3262351fb12d07cc0345169ceb8367c3dc92'


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda:stream.read(1048576),b''):h.update(data)
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    target=parser.parse_args().output.resolve()
    if target.exists() or not target.is_relative_to(OUT):raise ValueError('Fresh output required')
    verified={};runs={}
    def check(path,expected):
        path=Path(path)
        actual=digest(path)
        if actual!=expected:raise ValueError('Evidence drift: '+str(path))
        verified[str(path)]=actual
    def receipt(directory,historical=False,protocol=False):
        directory=Path(directory);path=directory/'result.json';d=json.loads(path.read_text())
        if d['state']!='PASS':raise ValueError('Unaccepted receipt '+str(path))
        verified[str(path)]=digest(path)
        pins=directory/'source-pins.json'
        if 'source_pins_sha256' in d:check(pins,d['source_pins_sha256'])
        exceptions=[]
        if pins.exists():
            for name,expected in json.loads(pins.read_text()).items():
                p=Path(name)
                if historical and p==ROOT/'hardware/src/vlsu/qbs/qbs_profile_engine_int.sv' and expected==OLD:
                    check(p,NEW)
                    archived=OUT/'qbs-retire-historical-integer-20261029-01/qbs_profile_engine_int.sv'
                    check(archived,OLD);exceptions.append(name)
                else:check(p,expected)
        if protocol:
            p=directory/'work/uvm_result.json';u=json.loads(p.read_text())
            if u['status']!='PASS' or u.get('issues'):raise ValueError('Protocol failure')
            verified[str(p)]=digest(p)
        runs[str(directory)]=dict(state='PASS',historical_rtl_exceptions=exceptions,
            measured=d.get('measured'),protocol_rechecked=protocol)
        return d
    for name,historical in [('qbs-retire-projection-vcs-20261029-01',False),
        ('register-retirement-final-20261029-01',False),
        ('prefill-production-q4-vcs-20261028-01',True),
        ('prefill-production-q8-vcs-20261028-01',True),
        ('value-pointer-q4-vcs-20261029-01',False),('value-pointer-q8-vcs-20261029-01',False)]:
        receipt(OUT/name,historical,True)
    receipt(OUT/'qbs-retire-ordinary-vcs-20261029-01')
    pipeline=OUT/'m4-sums-models-20261029-01';d=json.loads((pipeline/'result.json').read_text())
    if d['state']!='PASS' or not d['pipeline_pins_match']:raise ValueError('Model pipeline')
    verified[str(pipeline/'result.json')]=digest(pipeline/'result.json')
    for stage in d['stages'].values():
        directory=Path(stage['directory']);check(directory/'result.json',stage['result_sha256']);receipt(directory)
    snapshot=OUT/'optimization-runtime-snapshot-20261029-02'
    d=json.loads((snapshot/'result.json').read_text())
    if d['state']!='TESTED_RUNTIME_SOURCE_SNAPSHOT' or d['source_count']!=814:raise ValueError('Snapshot')
    for name,expected in d['artifacts'].items():check(snapshot/name,expected)
    verified[str(snapshot/'result.json')]=digest(snapshot/'result.json')
    rejected={}
    for name in ('value-cache-q4-vcs-20261029-01','value-cache-q8-vcs-20261029-01'):
        path=OUT/name/'result.json';d=json.loads(path.read_text())
        if d['state']!='FAIL' or 'TimeoutExpired' not in d.get('error',''):raise ValueError('Timeout record')
        rejected[name]=dict(state='FAIL',reason='timeout, rejected; not verified performance')
        verified[str(path)]=digest(path)
    for variant in ('value-cache-q4','value-cache-q8','value-pointer-q4','value-pointer-q8','register-retirement-final'):
        unit='ara-'+variant+'-20261029-01'
        state=subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','--value'],text=True).strip()
        if state!='0':raise ValueError('Worker still active: '+unit)
    result=dict(state='ROUND_EVIDENCE_REHASHED',scope='Finite optimization exit evidence, not universal processor signoff',
        verified_files=verified,runs=runs,rejected=rejected,functional_simulations_rerun=False,
        historical_prefill_rtl_explicit=True,current_prefill_baseline_checked_in_pointer_runs=True)
    target.write_text(json.dumps(result,indent=2)+'\n')
    print('ROUND_EVIDENCE_REHASHED unique_files='+str(len(verified)))


if __name__=='__main__':main()
