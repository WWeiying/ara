#!/usr/bin/env python3
"""Directly own a successor batch after an existing batch passes; never retry."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):
            h.update(block)
    return h.hexdigest()


def save(path,value):
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,indent=2)+'\n')
    tmp.replace(path)


def verify(pins):
    for path,expected in pins.items():
        if sha(path)!=expected:
            raise ValueError('Frozen chain input drift: '+path)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('prepare','execute'))
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--prerequisite',type=Path)
    p.add_argument('--unit')
    p.add_argument('--soc',type=Path)
    p.add_argument('--manifest',type=Path)
    p.add_argument('--campaign',type=Path)
    a=p.parse_args(); out=a.output.resolve()
    if a.action=='prepare':
        if out.exists() or not all((a.prerequisite,a.unit,a.soc,a.manifest,a.campaign)):
            raise ValueError('Fresh complete chain description required')
        out.mkdir(); inputs=out/'inputs'; inputs.mkdir()
        pins={}
        for name in ('chain.py','campaign.py','collect.py','monitor_metrics.py'):
            source=Path(__file__).with_name(name); dest=inputs/name
            shutil.copyfile(source,dest); pins[str(dest)]=sha(dest)
        pins[str(a.manifest.resolve())]=sha(a.manifest)
        for c in json.loads(a.manifest.read_text())['cases']:
            path=Path(c['source_pins'])
            extra=json.loads(path.read_text())
            extra[str(path)]=sha(path); extra[c['elf']]=c['elf_sha256']
            for name,h in extra.items():
                if name in pins and pins[name]!=h:
                    raise ValueError('Conflicting frozen chain input '+name)
            pins.update(extra)
        verify(pins)
        plan=dict(prerequisite=str(a.prerequisite.resolve()),unit=a.unit,
            soc=str(a.soc.resolve()),manifest=str(a.manifest.resolve()),
            campaign=str(a.campaign.resolve()),parallel=4,automatic_retry=False)
        save(out/'plan.json',plan); pins[str(out/'plan.json')]=sha(out/'plan.json')
        save(out/'source-pins.json',pins)
        save(out/'status.json',dict(state='PREPARED_NOT_RUN'))
        return 0
    if Path(__file__).resolve()!=out/'inputs/chain.py' or (out/'attempt.json').exists():
        raise ValueError('Only the frozen one-shot service worker can execute')
    save(out/'attempt.json',dict(owner_pid=__import__('os').getpid(),started=time.time()))
    plan=json.loads((out/'plan.json').read_text())
    pins=json.loads((out/'source-pins.json').read_text())
    result=dict(state='FAIL',automatic_retry=False)
    try:
        verify(pins)
        prerequisite=Path(plan['prerequisite'])
        save(out/'status.json',dict(state='WAITING_FOR_PREREQUISITE',campaign=str(prerequisite)))
        deadline=time.monotonic()+28800
        while not (prerequisite/'result.json').exists():
            process=subprocess.run(['systemctl','--user','show',plan['unit'],'-p','ActiveState','--value'],
                stdout=subprocess.PIPE,text=True,check=True,timeout=30)
            if process.stdout.strip() not in ('active','activating','reloading'):
                raise ValueError('Prerequisite owner stopped without a result')
            if time.monotonic()>deadline:
                raise TimeoutError('Prerequisite wait exceeded; no restart')
            time.sleep(60)
        prior=json.loads((prerequisite/'result.json').read_text())
        pins[str(prerequisite/'result.json')]=sha(prerequisite/'result.json')
        if not prior.get('post_source_image_pins_match'):
            raise ValueError('Prerequisite image/source identity failed')
        verify(json.loads((prerequisite/'source-pins.json').read_text()))
        collect=[sys.executable,'-B',str(out/'inputs/collect.py'),'--campaign',str(prerequisite),
                 '--output',str(out/'prerequisite-report')]
        subprocess.run(collect,check=True,timeout=1200)
        if prior['state']!='PASS':
            raise ValueError('Prerequisite contains failures; successor not dispatched')
        verify(pins)
        campaign=Path(plan['campaign'])
        save(out/'status.json',dict(state='PREPARING_SUCCESSOR',campaign=str(campaign)))
        command=[sys.executable,'-B',str(out/'inputs/campaign.py'),'prepare','--soc',plan['soc'],
            '--manifest',plan['manifest'],'--output',str(campaign),'--parallel',str(plan['parallel'])]
        subprocess.run(command,check=True,timeout=1200)
        save(out/'status.json',dict(state='SUCCESSOR_EXECUTING',campaign=str(campaign)))
        with (out/'campaign.stdout.log').open('x') as stream:
            completed=subprocess.run([sys.executable,'-B','-u',str(campaign/'inputs/campaign.py'),
                'execute','--output',str(campaign)],stdout=stream,stderr=subprocess.STDOUT)
        verify(pins)
        final=json.loads((campaign/'result.json').read_text())
        if final.get('post_source_image_pins_match'):
            subprocess.run([sys.executable,'-B',str(out/'inputs/collect.py'),'--campaign',str(campaign),
                '--output',str(out/'successor-report')],check=True,timeout=1200)
        if completed.returncode or final['state']!='PASS':
            raise ValueError('Successor incomplete; retained original failures, no automatic retry')
        result.update(state='PASS',cases=len(final['cases']),campaign=str(campaign))
    except Exception as exc:
        result['error']=repr(exc)
    save(out/'result.json',result); save(out/'status.json',result)
    print(json.dumps(result),flush=True)
    return result['state']!='PASS'


if __name__=='__main__':
    raise SystemExit(main())
