#!/usr/bin/env python3
"""Pinned runner for the direct-pointer variant, not the older copy candidate."""
import argparse
import json
from pathlib import Path
import signal
import value_cache_run as worker
from value_cache_check import check_log as check_common


def check_log(text,golden,q4):
    result=check_common(text,golden,q4)
    result.update(variant='direct_cached_value_pointer',
        scope='Whole-call two-group Prefill direct V pointer versus original production; not whole model')
    return result


def validate_variant(build):
    report=json.loads((build/'build.json').read_text())
    if report.get('state')!='BUILT_NOT_EXECUTED' or report.get('value_pointer') is not True or \
       report.get('pointer_transport_source_verified') is not True:
        raise ValueError('A completed direct-pointer variant build is required')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--soc-build',type=Path,required=True)
    parser.add_argument('--expected-soc-sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--timeout',type=int,default=10800)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if not 1<=args.timeout<=10800:parser.error('Timeout must be 1..10800')
    validate_variant(args.build.resolve(strict=True))
    worker.check_log=check_log
    def interrupted(sig,_frame):raise InterruptedError(f'Signal {sig}')
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,interrupted)
    worker.run(args)
