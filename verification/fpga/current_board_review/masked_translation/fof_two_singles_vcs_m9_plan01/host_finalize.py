"""Persist focused exact-ABI Host outcomes; never executes a simulator."""
import json
import subprocess
import sys
import checker as c
import csv_check
import strict_csv

if __name__=='__main__':
    c.require(csv_check.analyze is strict_csv.analyze,'Actual worker routes to strengthened checker')
    with (c.HERE/'host_final.log').open('x') as log:
        r=subprocess.run([sys.executable,'-B','-m','unittest','-v','test_host','test_handler'],
                         cwd=c.HERE,stdout=log,stderr=subprocess.STDOUT,timeout=30)
    code=['checker.py','source_owners.py','successor.py','successor_handler.py','strict_csv.py',
          'csv_check.py','test_host.py','test_handler.py','host_finalize.py']
    result=dict(returncode=r.returncode,tests=22,status='PASS_HOST_ONLY' if r.returncode==0 else 'FAIL',
                code_pins={str(c.HERE/n):c.sha(c.HERE/n) for n in code},
                log_sha256=c.sha(c.HERE/'host_final.log'),new_DUT=False,reference_rerun=False)
    c.common.save(c.HERE/'host_final.json',result)
    print(json.dumps(result),flush=True)
    raise SystemExit(r.returncode)
