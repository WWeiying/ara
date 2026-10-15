"""Persist actual systemd stop environment; never substitute GC defaults."""
import argparse
import os
import time
from scope import HERE,Path,require
from replay import durable

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    out=a.out.resolve();require(out.parent==HERE,'Owned stop receipt')
    durable(out/'service_exit.json',dict(kind='ACTUAL_SYSTEMD_EXEC_STOP_POST',observed_at=time.time(),
        hook_pid=os.getpid(),**{k:os.environ.get(k) for k in ('SERVICE_RESULT','EXIT_CODE','EXIT_STATUS')}))
if __name__=='__main__': main()
