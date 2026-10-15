import json,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
start=time.monotonic()
with (HERE/'host01.log').open('x') as f:
    child=subprocess.Popen([sys.executable,'-B',str(HERE/'test_entry.py')],stdout=f,stderr=subprocess.STDOUT)
    timed=False
    try:rc=child.wait(timeout=120)
    except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
    with (HERE/'host01_execution.json').open('x') as g:json.dump(dict(returncode=rc,pid=child.pid,elapsed_s=time.monotonic()-start,timed_out=timed,retries=0),g,indent=2)
raise SystemExit(rc)

