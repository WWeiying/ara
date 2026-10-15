"""Bounded short fixture correction; no full synthetic rerun or simulation."""
import hashlib,json,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')
names=('host02.json','host02.log','host02_command.json','host02_process_exit.json','host02_source/replay.py',
    'host_gate.py','test_host03.py','checker.py','replay.py','host_records.py','console_fixture_probe.py','console_fixture_probe01.json')
pins={str(HERE/n):hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in names}
command=[sys.executable,'-B',str(HERE/'test_host03.py')]
save(HERE/'host03_command.json',dict(command=command,input_pins=pins,timeout_s=60))
began=time.monotonic();timed=False
with (HERE/'host03.log').open('x') as log:
    child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
    try:rc=child.wait(timeout=60)
    except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
save(HERE/'host03_process_exit.json',dict(returncode=rc,timed_out=timed,pid=child.pid,elapsed_s=time.monotonic()-began))
raise SystemExit(rc if not timed else 124)
