"""Actual terminal-only Host receipt, reusing preserved full21 code/oracle proof."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import checker as c


def save(path,data):
    with path.open('x') as stream:
        json.dump(data,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())


def main():
    out=c.HERE/'host_terminal03';c.require(not out.exists(),'Fresh terminal Host output')
    proof=c.read(c.HERE/'successor_proof.json')
    pins=dict(proof['old_input_pins'])
    pins.update({str(p):c.sha(p) for p in list(c.HERE.glob('*.py'))+
        [c.HERE/'reset_profile.json',c.HERE/'successor_proof.json',c.HERE/'worker_delta.diff']})
    c.common.base.verify_pins(pins)
    out.mkdir();start=time.monotonic()
    command=[sys.executable,'-B','test_terminal.py','-v']
    with (out/'stdout.log').open('xb') as stdout,(out/'stderr.log').open('xb') as stderr:
        child=subprocess.run(command,cwd=c.HERE,stdout=stdout,stderr=stderr,timeout=30)
    text=(out/'stderr.log').read_text();m=re.search(r'Ran (\d+) tests',text)
    tests=int(m[1]) if m else 0;unchanged=all(c.sha(p)==h for p,h in pins.items())
    report=dict(status='PASS' if child.returncode==0 and tests==10 and '\nOK\n' in text and unchanged else 'FAIL',
        actual_child_returncode=child.returncode,actual_process_waited=True,elapsed_s=time.monotonic()-start,
        command=command,tests=tests,errors=0 if child.returncode==0 else None,
        failures=0 if child.returncode==0 else None,pins_unchanged=unchanged,code_pins=pins,
        inherited_full_matrix_tests=21,inherited_full_matrix_host=str(c.HERE.parent/'vcs_m8_plan01/host02.json'),
        inherited_full_matrix_host_sha256=c.sha(c.HERE.parent/'vcs_m8_plan01/host02.json'),
        full_matrix_not_rerun=True,no_DUT_reference_or_compile=True,
        scope='Terminal-only successor actual filesystem/timer/SIGTERM tests; checker/model/ELF unchanged')
    save(out/'execution.json',report)
    save(c.HERE/'host03.json',dict(report,receipt_sha256=c.sha(out/'execution.json'),
        stdout_sha256=c.sha(out/'stdout.log'),stderr_sha256=c.sha(out/'stderr.log')))
    print(json.dumps({k:report[k] for k in ('status','tests','actual_child_returncode','elapsed_s')}),flush=True)
    return int(report['status']!='PASS')


if __name__=='__main__':raise SystemExit(main())
