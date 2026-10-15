#!/usr/bin/env python3
"""Durable actual child outcome for the single Host/compile invocation."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
HERE=Path(__file__).resolve().parent
def save(name,value):
    with (HERE/name).open('x') as stream:json.dump(value,stream,indent=2)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source-review',required=True)
    parser.add_argument('--source-review-sha256',required=True);args=parser.parse_args()
    command=[sys.executable,'-B',str(HERE/'prepare.py'),'--source-review',args.source_review,
             '--source-review-sha256',args.source_review_sha256]
    save('execution_command.json',dict(command=command,timeout_s=600,reference=False,DUT=False))
    start=time.monotonic();timeout=False
    with (HERE/'execution.log').open('x') as log:
        child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        save('execution_pid.json',dict(pid=child.pid));print('Host/compile PID',child.pid,flush=True)
        try:rc=child.wait(timeout=600)
        except subprocess.TimeoutExpired:timeout=True;child.kill();rc=child.wait()
    save('execution_receipt.json',dict(returncode=rc,timed_out=timeout,elapsed_s=time.monotonic()-start))
    print('Host/compile actual',rc,'timeout',timeout,flush=True)
    raise SystemExit(124 if timeout else rc)
if __name__=='__main__':main()
