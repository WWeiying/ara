"""One full Host successor; keeps the initial300s timeout and exact tests."""
import json
from pathlib import Path
import subprocess
import sys
import time
HERE=Path(__file__).resolve().parent

def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')

if __name__=='__main__':
    if sys.argv[1:]==['--child']:
        import unittest
        import test_host as t
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(t.Host))
        pins={str(HERE/n):t.c.sha(HERE/n) for n in ('checker.py','replay.py','test_host.py',
            'host_records.py','reset_profile.json','host_successor02.py')}
        save(HERE/'host02.json',dict(status='PASS_HOST_ONLY' if result.wasSuccessful() else 'FAIL_HOST_ONLY',
            tests=result.testsRun,failures=len(result.errors)+len(result.failures),pins=pins,
            actual_abi_entry_checked=result.wasSuccessful(),full4095_streams=1,
            full_positive_shapes=[t.c.SHAPE] if result.wasSuccessful() else [],CSV_reads=0,DUT_reference_build_runs=0,
            fixture='Same constructed source/actual-machine-site rows as first attempt; no captured DUT'))
        raise SystemExit(not result.wasSuccessful())
    assert not sys.argv[1:]
    import hashlib
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    pins={str(HERE/n):sha(HERE/n) for n in ('checker.py','replay.py','test_host.py',
        'host_records.py','reset_profile.json','host_successor02.py')}
    command=[sys.executable,'-B',str(Path(__file__).resolve()),'--child']
    save(HERE/'host02_command.json',dict(command=command,timeout_s=900,input_pins=pins))
    began=time.monotonic();timed=False
    with (HERE/'host02.log').open('x') as stream:
        child=subprocess.Popen(command,cwd=HERE,stdout=stream,stderr=subprocess.STDOUT)
        try:rc=child.wait(timeout=900)
        except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
    unchanged=all(sha(Path(path))==digest for path,digest in pins.items())
    save(HERE/'host02_process_exit.json',dict(returncode=rc,timed_out=timed,elapsed_s=time.monotonic()-began,
        pid=child.pid,pins_unchanged=unchanged,attempt_for_this_successor=1))
    print(dict(returncode=rc,timed_out=timed,pins_unchanged=unchanged),flush=True)
    raise SystemExit(rc if not timed and unchanged else 124)
