#!/usr/bin/env python3
"""Wait for one existing campaign owner, then collect; never starts simulations."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',type=Path,required=True)
    p.add_argument('--unit',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    a.output.mkdir()
    own=a.output/'inputs';own.mkdir()
    pins={}
    for name in ('collect.py','monitor_metrics.py','finalize.py'):
        source=Path(__file__).with_name(name)
        dest=own/name;shutil.copyfile(source,dest)
        pins[str(dest)]=sha(dest)
    (a.output/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    state='FAIL'; error=None
    try:
        deadline=time.monotonic()+14400
        while not (a.campaign/'result.json').is_file():
            active=subprocess.run(['systemctl','--user','show',a.unit,'-p','ActiveState','--value'],
                stdout=subprocess.PIPE,text=True,check=True).stdout.strip()
            if active not in ('active','activating','reloading'):
                raise RuntimeError('Campaign owner is terminal without result: '+active)
            if time.monotonic()>deadline:
                raise RuntimeError('Collection wait budget exceeded; original worker not restarted')
            time.sleep(30)
        subprocess.run([sys.executable,'-B',str(own/'collect.py'),'--campaign',str(a.campaign),
            '--output',str(a.output/'report')],check=True,timeout=1200)
        state='COLLECTED'
    except Exception as exc:
        error=repr(exc)
    (a.output/'result.json').write_text(json.dumps(dict(state=state,error=error),indent=2)+'\n')
    return state!='COLLECTED'


if __name__=='__main__':
    raise SystemExit(main())
