"""Metadata-only pidfd waiter; no CSV read before original M8 worker exits."""
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time
HERE=Path(__file__).resolve().parent
WORKER=HERE.parent/'zero_stride_e64_m8_original16_vcs_m7_plan01'
OUT=WORKER/'prepared01'
def save(p,v):
    with p.open('x') as f:
        json.dump(v,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def main():
    ready=json.loads((OUT/'ready.json').read_text());launch=json.loads((OUT/'launch.json').read_text())
    pid=launch['owner']['pid'];proc=Path('/proc')/str(pid)
    fd=os.pidfd_open(pid)
    args=proc.joinpath('cmdline').read_bytes().decode().strip('\0').split('\0')
    expected=ready['command']
    assert args==expected,(args,expected)
    group=proc.joinpath('cgroup').read_text()
    assert launch['owner']['properties']['ControlGroup'] in group
    stats=proc.joinpath('stat').read_text().rsplit(')',1)[1].split()
    pins={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.py')}
    pins.update({str(OUT/n):hashlib.sha256((OUT/n).read_bytes()).hexdigest() for n in ('plan.json','ready.json','launch.json')})
    save(HERE/'waiter_attached.json',dict(status='WAITING_ORIGINAL_WORKER_METADATA_ONLY',pid=pid,start_ticks=int(stats[19]),argv=args,cgroup=group,pins=pins,CSV_read=False))
    poll=select.poll();poll.register(fd,select.POLLIN)
    ended=bool(poll.poll(10800000));os.close(fd)
    save(HERE/'worker_exit_event.json',dict(pid=pid,pidfd_exit_seen=ended,time=time.time(),CSV_read=False))
    assert ended,'Original worker did not exit within bounded waiter'
    for p,h in pins.items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,'Auditor/worker pin drift'
    # driver applies complete/raw numeric0/source/console gates before its one parse.
    cmd=[sys.executable,'-B',str(HERE/'driver.py')];begin=time.monotonic()
    child=subprocess.Popen(cmd);rc=child.wait()
    save(HERE/'waiter_child_wait.json',dict(actual_wait_exit=rc,child_pid=child.pid,elapsed_s=time.monotonic()-begin,command=cmd,no_retry=True))
    return rc
if __name__=='__main__':raise SystemExit(main())

