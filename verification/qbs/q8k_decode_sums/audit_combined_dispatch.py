#!/usr/bin/env python3
"""Audit the benign parent destructor record without rewriting worker failure."""
import argparse
import json
import os
from pathlib import Path
import time
from combined_decode_gate import check_dispatch
from run_combined_installed_model import check,hashes,atomic_json,digest


def normalize_parent(text):
    lines=text.splitlines()
    parent='Q8K_COMBINED_DISPATCH mode=invalid original=0 installed=0'
    suite='Q8K_MODEL_SUITE_PASS comparisons=6 performance=not_measured'
    if lines.count(parent)!=1 or lines.count(suite)!=1 or lines.count('GUEST_TEST_EXIT=0')!=1:
        raise ValueError('Not the proved zero-call parent-report case')
    if not lines.index(suite)<lines.index(parent)<lines.index('GUEST_TEST_EXIT=0'):
        raise ValueError('Parent report occurred before model acceptance')
    dispatch=[line for line in lines if line.startswith('Q8K_COMBINED_DISPATCH ')]
    if len(dispatch)!=3 or dispatch[-1]!=parent:
        raise ValueError('Unexpected dispatch report sequence')
    return '\n'.join(line for line in lines if line!=parent)


def audit(run):
    status=json.loads((run/'result.json').read_text())
    if status['state']!='FAIL' or status.get('error')!="ValueError('Missing quantizer dispatch evidence')":
        raise ValueError('Worker failed for a different reason')
    pins=json.loads((run/'manifest.json').read_text())
    if hashes(map(Path,pins))!=pins:raise ValueError('Original run input drift')
    text=(run/'qemu.log').read_text()
    normalized=normalize_parent(text)
    result=check(normalized)
    result['quantizer_dispatch']=check_dispatch(normalized,result['activity'])
    result.update(state='INDEPENDENT_MODEL_DISPATCH_AUDIT_PASS',original_worker_status='FAIL',
                  parent_record='mode=invalid original=0 installed=0 after complete model suite',
                  log_sha256=digest(run/'qemu.log'),manifest_sha256=digest(run/'manifest.json'),
                  scope='All original model/work checks and child dispatch checks; ignores only proved zero-call parent destructor')
    output=run/'combined-dispatch-audit.json'
    if output.exists():raise ValueError('Never overwrite an existing audit')
    atomic_json(output,result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--wait-pid',type=int)
    a=p.parse_args();run=a.run.resolve(strict=True)
    deadline=time.monotonic()+7200
    while not (run/'result.json').exists():
        if not a.wait_pid or time.monotonic()>deadline:raise ValueError('Result not ready')
        command=Path(f'/proc/{a.wait_pid}/cmdline').read_bytes()
        if str(run).encode() not in command and run.name.encode() not in command:
            raise ValueError('Expected worker handle is no longer present')
        os.kill(a.wait_pid,0)
        time.sleep(30)
    result=audit(run)
    print(json.dumps({k:result[k] for k in ('state','comparisons','logits_compared','quantizer_dispatch')},indent=2))


if __name__=='__main__':main()
