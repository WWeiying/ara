#!/usr/bin/env python3
"""Use two spare slots while freezing only the downstream dispatch service."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from chain_owner_v2 import bind, inventory, save, verify


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); out=a.output.resolve(); out.mkdir(exist_ok=True)
    with (out/'attempt.json').open('x') as f:
        f.write(json.dumps(dict(owner_pid=os.getpid(),started=time.time()))+'\n')
    pins={}; inventory(pins,a.campaign)
    for f in (Path(__file__).resolve(),Path(__file__).with_name('chain_owner_v2.py'),
              Path(__file__).with_name('collect.py'),Path(__file__).with_name('monitor_metrics.py')):
        bind(pins,f)
    save(out/'source-pins.json',pins)
    unit='operator-chain-20261115-formats-04.service'
    held=False; started=False
    result=dict(state='FAIL',automatic_retry=False,held_unit=unit)
    try:
        verify(pins)
        plan=json.loads((a.campaign/'plan.json').read_text())
        if plan['parallel']!=2 or len(plan['cases'])!=2 or (a.campaign/'attempt.json').exists():
            raise ValueError('Exactly two fresh probe cases required')
        state=json.loads((out.parent/'operator_chain_20261115_formats_04/status.json').read_text())
        if state['state']!='WAITING_FOR_PREREQUISITE':
            raise ValueError('Only the waiting successor dispatcher may be held')
        subprocess.run(['systemctl','--user','freeze',unit],check=True,timeout=30)
        held=True
        frozen=subprocess.run(['systemctl','--user','show',unit,'-p','FreezerState','--value'],
            check=True,text=True,stdout=subprocess.PIPE,timeout=30).stdout.strip()
        if frozen!='frozen':
            raise ValueError('Dispatch cgroup not frozen; no simulator started')
        save(out/'status.json',dict(state='TWO_SLOT_PROBE_EXECUTING',held_unit=unit))
        started=True
        with (out/'campaign.log').open('x') as f:
            run=subprocess.run([sys.executable,'-B','-u',str(a.campaign/'inputs/campaign.py'),
                'execute','--output',str(a.campaign)],stdout=f,stderr=subprocess.STDOUT)
        report=json.loads((a.campaign/'result.json').read_text()); verify(pins)
        if run.returncode or report['state']!='PASS' or not report['post_source_image_pins_match']:
            raise ValueError('Probe failed; downstream stays held for triage')
        subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('collect.py')),
            '--campaign',str(a.campaign),'--output',str(out/'report')],check=True,timeout=1200)
        verify(pins)
        result.update(state='PASS',campaign=str(a.campaign),post_source_image_pins_match=True)
    except Exception as exc:
        result['error']=repr(exc)
    finally:
        if held and (result['state']=='PASS' or not started):
            thaw=subprocess.run(['systemctl','--user','thaw',unit],timeout=30)
            result['dispatch_resumed']=thaw.returncode==0
            if thaw.returncode:
                result.update(state='FAIL',error='Could not resume dispatcher')
        else:
            result['dispatch_resumed']=False
        save(out/'result.json',result); save(out/'status.json',result)
    print(json.dumps(result),flush=True)
    return result['state']!='PASS'


if __name__=='__main__':
    raise SystemExit(main())
