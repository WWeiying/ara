#!/usr/bin/env python3
"""Separately audit completed evidence with an explicit successor checker."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):
            h.update(b)
    return h.hexdigest()


def save(p,v):
    p.write_text(json.dumps(v,indent=2)+'\n')


def verify(pins):
    for p,h in pins.items():
        if sha(p)!=h:
            raise ValueError('Input/evidence drift: '+p)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',type=Path,required=True)
    p.add_argument('--case',required=True)
    p.add_argument('--checker',type=Path,required=True)
    p.add_argument('--checker-pins',type=Path,required=True)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--reason',required=True)
    a=p.parse_args();a.output.mkdir()
    result=dict(state='FAIL',scope='Separate successor numerical/protocol audit of completed evidence',
        original_worker=str(a.campaign),original_case=a.case,reason=a.reason,
        original_worker_relabelled=False,simulator_rerun=False,whole_model=False)
    try:
        original=json.loads((a.campaign/'result.json').read_text())
        if not original['post_source_image_pins_match']:
            raise ValueError('Original image/source identities are not clean')
        plan=json.loads((a.campaign/'plan.json').read_text())
        case=next(x for x in plan['cases'] if x['id']==a.case)
        work=a.campaign/'runs'/a.case
        text=(work/'run.vcs.log').read_text(errors='strict')
        if 'Core Test *** SUCCESS ***' not in text:
            raise ValueError('Incomplete or failed original simulator evidence')
        pins=json.loads((a.campaign/'source-pins.json').read_text())
        successor=json.loads(a.checker_pins.read_text())
        for name,h in successor.items():
            if name in pins and pins[name]!=h:
                raise ValueError('Conflicting successor input '+name)
        pins.update(successor)
        for f in (a.checker,a.checker_pins,a.campaign/'result.json',a.campaign/'plan.json',
                  work/'run.vcs.log',work/'vector.csv',work/'commit.csv',Path(__file__).resolve()):
            pins[str(f)]=sha(f)
        verify(pins)
        save(a.output/'source-pins.json',pins)
        env=dict(plan['environment'],PYTHONPATH=str(Path(plan['soc'])/'source/verification'),
                 PYTHONDONTWRITEBYTECODE='1')
        numeric=[sys.executable,'-B',str(a.checker),'--build',str(a.build),'--log',str(work/'run.vcs.log'),
                 '--commit',str(work/'commit.csv'),'--output',str(a.output/'numerical.json')]
        with (a.output/'numerical.log').open('x') as f:
            subprocess.run(numeric,stdout=f,stderr=subprocess.STDOUT,env=env,check=True,timeout=600)
        measured=json.loads((a.output/'numerical.json').read_text())
        if measured.get('state')!='PASS':
            raise ValueError('Successor numerical check did not pass')
        proto=[sys.executable,'-B','-m','ara_verify.uvm_dut','--require-events','--require-backend',
            '--require-axi','--require-axi-write','--vector-trace',str(work/'vector.csv'),
            '--log',str(work/'run.vcs.log'),'--simv',plan['simv'],'--elf',case['elf'],
            '--output',str(a.output/'protocol.json')]
        with (a.output/'protocol.log').open('x') as f:
            subprocess.run(proto,stdout=f,stderr=subprocess.STDOUT,env=env,check=True,timeout=1200)
        proof=json.loads((a.output/'protocol.json').read_text())
        if proof['status']!='PASS' or proof['issues'] or proof['elf_sha256']!=case['elf_sha256'] or \
            proof['simv_sha256']!=pins[plan['simv']] or proof['log_sha256']!=sha(work/'run.vcs.log') or \
            proof['vector_trace_sha256']!=sha(work/'vector.csv') or \
            any(proof['contract_counts'][k] for k in ('exceptions','protocol_errors','outstanding')):
            raise ValueError('Independent protocol/identity failure')
        verify(pins)
        save(a.output/'commands.json',dict(numerical=numeric,protocol=proto))
        result.update(state='PASS',measured=measured,independent_protocol_checked=True,
                      post_source_image_pins_match=True,evidence_run=str(work),configuration=plan['configuration'])
    except Exception as exc:
        result['error']=repr(exc)
    save(a.output/'result.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='measured'}))
    return result['state']!='PASS'


if __name__=='__main__':
    raise SystemExit(main())
