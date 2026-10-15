"""One reviewed software phase; persist actual child wait before checking."""
import argparse,json,os
from pathlib import Path
import subprocess,sys,time
HERE=Path(__file__).resolve().parent
def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
parser=argparse.ArgumentParser();parser.add_argument('--review',type=Path,required=True);parser.add_argument('--review-sha',required=True)
args=parser.parse_args()
command=[sys.executable,'-B',str(HERE/'prepare.py'),'software',str(args.review.resolve()),args.review_sha]
save(HERE/'software_command.json',dict(command=command,timeout_s=300,attempt=1,DUT_runs=0))
start=time.monotonic();timed=False
with (HERE/'software.log').open('x') as log:
    child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
    try:rc=child.wait(timeout=300)
    except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
    save(HERE/'software_execution.json',dict(actual_wait_returncode=rc,pid=child.pid,
        elapsed_s=time.monotonic()-start,timed_out=timed,retries=0,validated=False))
raise SystemExit(rc if not timed else 124)
