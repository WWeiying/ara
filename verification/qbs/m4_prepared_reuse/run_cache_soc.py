#!/usr/bin/env python3
"""Reuse the pinned current-image worker with the cache preparation checker."""
import argparse
import importlib.util
from pathlib import Path
import signal
import sys

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('m4_cache_soc_worker',HERE.parent/'combined_zvfh_m4/projection/run.py')
worker=importlib.util.module_from_spec(spec);sys.modules[spec.name]=worker
spec.loader.exec_module(worker)
worker.HERE=HERE


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--timeout',type=int,default=10800);p.add_argument('--execute-reviewed',action='store_true')
    def interrupted(signum,_frame):raise InterruptedError(f'Signal {signum}')
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,interrupted)
    worker.run(p.parse_args())
