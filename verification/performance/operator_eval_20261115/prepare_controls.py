#!/usr/bin/env python3
"""Prepare ordered qualification/performance pairs, without starting simulators."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

OUT=Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.parent!=OUT:
        raise ValueError('Fresh owned control index required')
    a.output.mkdir()
    reuse=OUT/'operator_qbs_reuse_prepare_20261115_release_01/native-manifest.json'
    attention=OUT/'operator_attention_real_prepare_20261115_handoff_01/run-plan.json'
    files=[reuse,attention,Path(__file__).resolve(),Path(__file__).with_name('campaign.py')]
    pins={str(f):sha(f) for f in files}
    selected={'qbs_reuse_q4_rows4_n64_m4','qbs_reuse_q4_rows8_n64_m8',
              'qbs_reuse_q4_rows8_n64_2xm4'}
    cases=[c for c in json.loads(reuse.read_text())['cases'] if c['id'] in selected]
    if {c['id'] for c in cases}!=selected:
        raise ValueError('Missing matched M4/M8 experiments')
    stages=[]
    for variant in ('loan_off','queue_zero','shared_fma_off'):
        qualification=OUT/f'operator_campaign_20261115_control_{variant}_qual_05'
        q=json.loads((qualification/'plan.json').read_text())
        if (qualification/'attempt.json').exists() or not q['soc'].endswith('/'+variant):
            raise ValueError('Qualification must be unexecuted and match this variant')
        chosen=[json.loads(attention.read_text())['cases'][0]] if variant=='shared_fma_off' else cases
        manifest=a.output/(variant+'-cases.json')
        manifest.write_text(json.dumps(dict(cases=chosen),indent=2)+'\n')
        campaign=OUT/f'operator_campaign_20261115_control_{variant}_perf_08'
        subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('campaign.py')),'prepare',
            '--soc',q['soc'],'--manifest',str(manifest),'--output',str(campaign),
            '--parallel',str(min(4,len(chosen)))],check=True,timeout=300)
        for path in (qualification,campaign):
            for name,h in json.loads((path/'source-pins.json').read_text()).items():
                if name in pins and pins[name]!=h:
                    raise ValueError('Conflicting source/image input '+name)
                pins[name]=h
        pins[str(manifest)]=sha(manifest)
        stages.append(dict(variant=variant,qualification=str(qualification),performance=str(campaign),
            qualified=False,executed=False,requires_preceding_stage_pass=True))
    for name,h in pins.items():
        if sha(name)!=h:
            raise ValueError('Frozen preparation input drift '+name)
    (a.output/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    (a.output/'plan.json').write_text(json.dumps(dict(state='PREPARED_NOT_EXECUTED',
        prerequisite=str(OUT/'operator_campaign_20261115_reuse_06'),
        stages=stages,global_simulator_limit=4,parallel_stage_execution=False,
        automatic_retry=False,scope='Same-production-source single-switch attribution, not PPA'),indent=2)+'\n')
    print(str(a.output/'plan.json'))


if __name__=='__main__':
    main()
