#!/usr/bin/env python3
"""Own the finite ordered control sequence; no simulator retries or detached children."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

OUT=Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):
            h.update(block)
    return h.hexdigest()


def save(path,value):
    tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(value,indent=2)+'\n'); tmp.replace(path)


def verify(pins):
    for path,h in pins.items():
        if sha(path)!=h:
            raise ValueError('Frozen control input drift: '+path)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('prepare','execute'))
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); out=a.output.resolve()
    if a.action=='prepare':
        if out.exists() or out.parent!=OUT:
            raise ValueError('Fresh owned output required')
        out.mkdir(); (out/'inputs').mkdir()
        stages=[]; pins={}
        for variant in ('loan_off','queue_zero','shared_fma_off'):
            for part,index in (('qual','05'),('coexist','10'),('perf','08')):
                path=OUT/f'operator_campaign_20261115_control_{variant}_{part}_{index}'
                plan=json.loads((path/'plan.json').read_text())
                if (path/'attempt.json').exists() or not plan['soc'].endswith('/'+variant) or not 1<=plan['parallel']<=4:
                    raise ValueError('Unexecuted matching bounded stage required')
                for name,h in json.loads((path/'source-pins.json').read_text()).items():
                    if name in pins and pins[name]!=h:
                        raise ValueError('Conflicting stage identity')
                    pins[name]=h
                stages.append(str(path))
        for name in ('run_controls_parent.py','collect.py','monitor_metrics.py'):
            target=out/'inputs'/name; shutil.copyfile(Path(__file__).with_name(name),target)
            pins[str(target)]=sha(target)
        plan=dict(stages=stages,prerequisite=str(OUT/'operator_campaign_20261115_coexist_10'),
            owner='operator-chain-20261115-coexist-10.service',parallel_stages=False,automatic_retry=False)
        save(out/'plan.json',plan); pins[str(out/'plan.json')]=sha(out/'plan.json')
        verify(pins); save(out/'source-pins.json',pins)
        save(out/'status.json',dict(state='PREPARED_NOT_RUN')); return 0
    if Path(__file__).resolve()!=out/'inputs/run_controls_parent.py' or (out/'attempt.json').exists():
        raise ValueError('Frozen one-shot controller required')
    save(out/'attempt.json',dict(owner_pid=__import__('os').getpid(),started=time.time()))
    plan=json.loads((out/'plan.json').read_text()); pins=json.loads((out/'source-pins.json').read_text())
    result=dict(state='FAIL',completed=[],automatic_retry=False)
    try:
        verify(pins); prior=Path(plan['prerequisite'])
        save(out/'status.json',dict(state='WAITING_FOR_PREREQUISITE',campaign=str(prior)))
        deadline=time.monotonic()+86400
        while not (prior/'result.json').exists():
            owner=subprocess.run(['systemctl','--user','show',plan['owner'],'-p','ActiveState','--value'],
                check=True,text=True,stdout=subprocess.PIPE,timeout=30).stdout.strip()
            if owner not in ('active','activating','reloading') or time.monotonic()>deadline:
                raise ValueError('Prerequisite owner stopped or wait expired; no restart')
            time.sleep(60)
        report=json.loads((prior/'result.json').read_text())
        if report['state']!='PASS' or not report['post_source_image_pins_match']:
            raise ValueError('Prerequisite not accepted')
        verify(json.loads((prior/'source-pins.json').read_text()))
        for i,name in enumerate(plan['stages']):
            stage=Path(name); verify(pins)
            if (stage/'attempt.json').exists():
                raise ValueError('Stage already attempted; never restart')
            save(out/'status.json',dict(state='EXECUTING',stage=name,completed=result['completed']))
            with (out/f'{i:02d}.log').open('x') as stream:
                run=subprocess.run([sys.executable,'-B','-u',str(stage/'inputs/campaign.py'),
                    'execute','--output',name],stdout=stream,stderr=subprocess.STDOUT)
            report=json.loads((stage/'result.json').read_text()); verify(pins)
            if report.get('post_source_image_pins_match'):
                subprocess.run([sys.executable,'-B',str(out/'inputs/collect.py'),'--campaign',name,
                    '--output',str(out/f'report-{i:02d}')],check=True,timeout=1200)
            if run.returncode or report['state']!='PASS':
                raise ValueError('Stage failed, successor not dispatched: '+name)
            result['completed'].append(dict(campaign=name,result_sha256=sha(stage/'result.json')))
        result['state']='PASS'
    except Exception as exc:
        result['error']=repr(exc)
    save(out/'result.json',result); save(out/'status.json',result)
    print(json.dumps(result),flush=True)
    return result['state']!='PASS'


if __name__=='__main__':
    raise SystemExit(main())
