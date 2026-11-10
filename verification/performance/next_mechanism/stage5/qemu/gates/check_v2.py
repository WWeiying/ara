#!/usr/bin/env python3
"""Scoped successor: cross-check INFO trace results; preserve build03/check.py."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
BASE_SHA='32ae013e8a2ac995adfd23b2944e80cfe767210a26496d7c8bf85e118a22a31f'
BASE=HERE/'check.py'
if hashlib.sha256(BASE.read_bytes()).hexdigest()!=BASE_SHA:
    raise ValueError('Unreviewed original directed checker')
spec=importlib.util.spec_from_file_location('stage5_directed_original_checker',BASE)
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def info_results(text,manifest):
    words=[1|1<<8|64<<16|8<<24|8<<32|1<<40|15<<48,
           0x5b|2<<8|3<<11|4<<14|5<<17|6<<20,
           2|64<<8|8<<16|6<<24|127<<32|1<<40,
           0x5b|6<<8|7<<11|128<<16|1<<24,0]
    expected=[dict(index=c['a'],result=words[c['a']]) for c in manifest['cases']
              if c['op']=='info' and not c['cause']]
    actual=[r for tag,r in base.trace_rows(text) if tag=='info']
    base.require(actual==expected,'INFO trace result/index/count differs from independent capability words')
    return dict(records=len(expected),trace_results_checked=True)


def check(build,mode,log,trace):
    base.require(hashlib.sha256(BASE.read_bytes()).hexdigest()==BASE_SHA,'Original checker drift')
    result=base.check(build,mode,log,trace)
    receipt=base.read(Path(build)/'build.json')
    variant=next(v for v in receipt['variants'] if v['mode']==mode)
    result['info_trace']=info_results(Path(trace).read_text(),base.read(variant['expected']))
    result['checker_successor']='info-result-v2'
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--build',type=Path,required=True);p.add_argument('--mode',type=int,choices=(0,1,2),required=True)
    p.add_argument('--log',type=Path,required=True);p.add_argument('--trace',type=Path,required=True)
    a=p.parse_args();print(json.dumps(check(a.build,a.mode,a.log,a.trace),indent=2,sort_keys=True))
