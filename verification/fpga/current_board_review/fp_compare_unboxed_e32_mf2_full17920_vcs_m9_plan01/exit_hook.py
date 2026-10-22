"""Actual systemd main exit then a bounded metadata-only collector, no CSV parse."""
import argparse
import os
import subprocess
import time
from scope import *
from replay import durable

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    out=a.out.resolve();require(out.parent==HERE,'Owned stop receipt')
    durable(out/'service_exit.json',dict(kind='ACTUAL_SYSTEMD_EXEC_STOP_POST',observed_at=time.time(),hook_pid=os.getpid(),
        **{k:os.environ.get(k) for k in ('SERVICE_RESULT','EXIT_CODE','EXIT_STATUS')}))
    plan=read(out/'plan.json');c=plan['service_terminal_contract']
    path=HERE/'collect.py'
    require(c['RemainAfterExit'] is False and c['exit_hook_sha256']==sha(Path(__file__)) and
            plan['pins'][str(path)]==c['collector_sha256']==sha(path),'Exact automatic exit/collector contract')
    cmd=[sys.executable,'-B',str(path),'--out',str(out)]
    durable(out/'collector.command.json',dict(command=cmd,timeout_s=180,plan_sha256=sha(out/'plan.json')))
    start=time.monotonic();timed=False
    with (out/'collector.log').open('x') as f:
        child=subprocess.Popen(cmd,cwd=HERE,stdout=f,stderr=subprocess.STDOUT)
        try:rc=child.wait(timeout=180)
        except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
    durable(out/'collector.wait.json',dict(actual_wait_exit=rc,timed_out=timed,pid=child.pid,
                                          elapsed_s=time.monotonic()-start,log_sha256=sha(out/'collector.log')))
    result=out/'collector_result.json'
    accepted=(type(rc)is int and rc==0 and not timed and result.is_file() and
              read(result)['status']=='PASS_FULL17920_FP32_M9_METADATA_COLLECTED_NOT_LINUX')
    durable(out/'terminal_event.json',dict(status='TERMINAL_COLLECTOR_ACCEPTED' if accepted else 'NOT_ACCEPTED',
        collector_wait_sha256=sha(out/'collector.wait.json'),
        collector_result_sha256=sha(result) if result.is_file() else None,
        actual_collector_wait=rc,timed_out=timed,no_DUT_retry=True))
    return 124 if timed else rc
if __name__=='__main__':raise SystemExit(main())
