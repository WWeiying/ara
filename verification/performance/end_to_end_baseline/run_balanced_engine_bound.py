#!/usr/bin/env python3
"""Identity-only successor; preserve the original preparation failure."""
import argparse
import hashlib
import inspect
import json
from pathlib import Path
import sys

from audit import digest, require
import run_balanced_engine as parent

SOURCE_SHA='2d051f2aa0a7bcaf2ee31c056458f11772dcd6782e6620a3d9c2cb7f86591985'
FIRST=parent.RUNS/'e2e_balanced_engine_20261106_01'
FIRST_SHA='79575524cd6cce63debdb6c5f81c2bcc54518a4c28b477936b9c26c0daadbe8a'
BEFORE='pin(pins,probe,inventories[BASE][str(probe)])'
AFTER='pin(pins,probe,inventories[PRIOR][str(probe)])'


def patched_function(source):
    require(source.count(BEFORE)==1 and AFTER not in source,'Single probe-inventory identity repair required')
    fixed=source.replace(BEFORE,AFTER,1)
    anchor='    try:\n        for root,sha in'
    added='''    try:
        pin(pins,IDENTITY_SUCCESSOR['first_result'],IDENTITY_SUCCESSOR['first_result_sha256'])
        save('identity-successor.json',IDENTITY_SUCCESSOR)
        for root,sha in'''
    require(fixed.count(anchor)==1,'Successor evidence insertion anchor')
    fixed=fixed.replace(anchor,added,1)
    require(fixed.replace(added,anchor,1).replace(AFTER,BEFORE,1)==source,'Nonreversible successor')
    return fixed


def build():
    require(digest(parent.__file__)==SOURCE_SHA and digest(FIRST/'result.json')==FIRST_SHA,
            'Sealed producer/failure identity differs')
    first=json.loads((FIRST/'result.json').read_text())
    require(first['state']=='FAIL' and first['error']==
            "KeyError('/home/wangwy/openproject/ara_dsa/verification/performance/end_to_end_baseline/matrix_replay_probe.svh')" and
            json.loads((FIRST/'commands.json').read_text())==[],
            'Only the no-EDA preparation failure may use this successor')
    source=inspect.getsource(parent.run);fixed=patched_function(source)
    report=dict(original_helper=str(Path(parent.__file__).resolve()),original_helper_sha256=SOURCE_SHA,
        first_result=str(FIRST/'result.json'),first_result_sha256=FIRST_SHA,original_failure_relabelled=False,
        functional_change='None; bind unchanged probe to accepted fault-audit inventory, not missing default-build entry',
        before=BEFORE,after=AFTER,original_function_sha256=hashlib.sha256(source.encode()).hexdigest(),
        generated_function_sha256=hashlib.sha256(fixed.encode()).hexdigest(),source_reversible=True)
    namespace=dict(vars(parent),__file__=str(Path(__file__).resolve()),IDENTITY_SUCCESSOR=report,
                   TESTS=(*parent.TESTS,'test_balanced_engine_bound'))
    exec(compile(fixed,str(Path(__file__).resolve()),'exec'),namespace)
    return namespace['run'],report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--execute-reviewed',action='store_true')
    args=parser.parse_args();function,_=build();sys.exit(function(args.output,args.execute_reviewed))
