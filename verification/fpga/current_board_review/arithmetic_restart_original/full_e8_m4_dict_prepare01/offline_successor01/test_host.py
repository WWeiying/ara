#!/usr/bin/env python3
"""Small actual-ELF lifecycle negatives, no raw log read or simulator."""
import json
from pathlib import Path
import subprocess
import sys
import time
import observer
HERE=Path(__file__).resolve().parent

def main():
    body='import json,observer; s=json.loads((observer.SOURCE/"spike/symbols.json").read_text()); '
    body+='a,d=observer.audit_function(); n=observer.boundary_tests(s,d["setup_start"],d["setup_end"]); '
    body+='print(json.dumps(dict(status="PASS",checks=n,raw_reads=0,Spike_runs=0,observer_delta=d)))'
    command=[sys.executable,'-B','-c',body]
    observer.save(HERE/'host_command.json',dict(command=command,timeout_s=30,observer_sha256=observer.sha(HERE/'observer.py')))
    start=time.monotonic()
    with (HERE/'host.log').open('x') as stream:
        child=subprocess.Popen(command,cwd=HERE,stdout=stream,stderr=subprocess.STDOUT)
        rc=child.wait(timeout=30)
        observer.save(HERE/'host_execution.json',dict(actual_wait_returncode=rc,pid=child.pid,elapsed_s=time.monotonic()-start))
    if rc:raise ValueError('Lifecycle Host failed; original evidence retained')
    report=json.loads((HERE/'host.log').read_text())
    if report['status']!='PASS' or report['checks']!=16:raise ValueError('Incomplete lifecycle Host')
    report['actual_execution_sha256']=observer.sha(HERE/'host_execution.json')
    observer.save(HERE/'host_result.json',report)
    print('PASS 16 lifecycle checks; no raw/Spike',flush=True)

if __name__=='__main__':main()
