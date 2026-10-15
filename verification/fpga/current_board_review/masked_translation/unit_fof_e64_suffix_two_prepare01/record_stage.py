"""Persist actual outer software-process wait results, including parser failures."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser()
p.add_argument('stage',choices=['build','host','reference1','reference2'])
args=p.parse_args()
command=[sys.executable,'-B',str(HERE/'prepare.py')]
command += ['reference','--scenario',args.stage[-1]] if args.stage.startswith('reference') else [args.stage]
receipt=HERE/(args.stage+'.wait.json')
log=HERE/(args.stage+'.outer.log')
if receipt.exists() or log.exists():raise SystemExit('Fresh stage only; no automatic retries')
started=time.monotonic()
with log.open('x') as stream:
    child=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT)
    rc=child.wait()
with receipt.open('x') as stream:
    json.dump(dict(command=command,actual_outer_wait_returncode=rc,
                   elapsed_s=time.monotonic()-started,log=str(log)),stream,indent=2)
    stream.write('\n')
print(args.stage, 'actual_outer_wait_returncode',rc,flush=True)
raise SystemExit(rc)
