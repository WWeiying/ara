#!/usr/bin/env python3
"""Persist actual final checker/worker Host process receipt; no target execution."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import checker as c


def save(path,data):
    with path.open('x') as stream:
        json.dump(data,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())


def main():
    out=c.HERE/'host_final02';c.require(not out.exists(),'Fresh actual Host receipt')
    paths=list(c.HERE.glob('*.py'))+[c.HERE/'reset_profile.json',c.REF/'model.json',
        c.REF/'soc/program.json',c.REF/'soc/program.dis',c.REF/'READY.json',c.LEGACY,c.GENERIC,
        c.transport.TRANSPORT,c.G.parents[1]/'ara_verify/trace.py',
        c.G.parents[1]/'coverage/scoped_rv64c_memory.py']
    pins={str(p):c.sha(p) for p in paths}
    out.mkdir();started=time.monotonic()
    command=[sys.executable,'-B','-m','unittest','-v','test_owner','test_memory','test_worker']
    with (out/'stdout.log').open('xb') as stdout,(out/'stderr.log').open('xb') as stderr:
        q=subprocess.run(command,cwd=c.HERE,stdout=stdout,stderr=stderr,timeout=180)
    elapsed=time.monotonic()-started
    text=(out/'stderr.log').read_text()
    import re
    match=re.search(r'Ran (\d+) tests',text)
    tests=int(match[1]) if match else 0
    unchanged=all(c.sha(p)==h for p,h in pins.items())
    report=dict(status='PASS' if q.returncode==0 and tests==21 and '\nOK\n' in text and unchanged else 'FAIL',
        command=command,actual_child_returncode=q.returncode,actual_process_waited=True,elapsed_s=elapsed,
        tests=tests,errors=0 if q.returncode==0 else None,failures=0 if q.returncode==0 else None,
        code_pins=pins,pins_unchanged=unchanged,
        no_DUT_reference_or_compiler_executed=True,
        scope='Synthetic full482 RVFI, exact compiled ABI, per-arch-owner negatives, monitor/gates')
    save(out/'execution.json',report)
    save(c.HERE/'host02.json',dict(report,receipt_sha256=c.sha(out/'execution.json'),
        stdout_sha256=c.sha(out/'stdout.log'),stderr_sha256=c.sha(out/'stderr.log')))
    print(json.dumps({k:report[k] for k in ('status','tests','actual_child_returncode','elapsed_s')}),flush=True)
    return int(report['status']!='PASS')


if __name__=='__main__':raise SystemExit(main())
