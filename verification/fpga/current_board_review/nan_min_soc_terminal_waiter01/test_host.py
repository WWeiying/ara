"""Tiny event-only Host; no simulated target, CSV scan or worker polling."""
from pathlib import Path
import subprocess
import sys
import tempfile
import waiter as w


def reject(fn):
    try: fn()
    except ValueError: return
    raise ValueError('Event-only negative accepted')


def main():
    child=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(0.05)'])
    fd=w.os.pidfd_open(child.pid)
    try: w.wait_fd(fd,2)
    finally: w.os.close(fd)
    rc=child.wait();w.require(rc==0,'Actual short scalar Host child exit')
    with tempfile.TemporaryDirectory(dir=w.HERE) as tmp:
        root=Path(tmp);group=root/w.GROUP.lstrip('/');group.mkdir(parents=True)
        (group/'cgroup.procs').write_text('')
        w.require(w.empty_cgroup(root)['state']=='empty','Empty cgroup positive')
        (group/'cgroup.procs').write_text('123\n');reject(lambda:w.empty_cgroup(root))
        (group/'cgroup.procs').unlink();reject(lambda:w.empty_cgroup(root))
    expected=w.read(w.RUN/'ready.json')['command']
    expected=[str(w.WORK/'parent_review.json') if s=='UNRESOLVED_PARENT_REVIEW_JSON' else
              w.PARENT_SHA if s=='UNRESOLVED_PARENT_REVIEW_SHA256' else s for s in expected]
    ready=dict(worker_start_ticks=123)
    w.identity(expected,'0::'+w.GROUP,123,ready)
    reject(lambda:w.identity(expected,'0::'+w.GROUP,124,ready))
    reject(lambda:w.identity(expected[:-1]+['wrong-parent'],'0::'+w.GROUP,123,ready))
    w.save(w.HERE/'host01.json',dict(status='PASS_EVENT_ONLY_HOST',actual_scalar_child_exit=rc,
        pidfd_exit_positive=True,identity_positive=True,negatives=4,active_CSV_reads=0,
        DUT_reference_launches=0))
    print('PASS_EVENT_ONLY_HOST')


if __name__=='__main__': main()
