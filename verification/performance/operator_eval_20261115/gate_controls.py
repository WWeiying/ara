#!/usr/bin/env python3
"""Require completed owner acceptance before the unchanged sequential controls."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from chain_owner_v2 import bind, inventory, save, sha, verify, wait_owner


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('prepare','execute'))
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--child',type=Path)
    a=p.parse_args(); out=a.output.resolve()
    if a.action=='prepare':
        if out.exists() or not a.child or (a.child/'attempt.json').exists():
            raise ValueError('Fresh wrapper and unattempted child required')
        pins={}; inventory(pins,a.child.resolve()); verify(pins)
        out.mkdir(); (out/'inputs').mkdir()
        for name in ('gate_controls.py','chain_owner_v2.py'):
            target=out/'inputs'/name; shutil.copyfile(Path(__file__).with_name(name),target); bind(pins,target)
        root=out.parent
        plan=dict(child=str(a.child.resolve()),prerequisite=str(root/'operator_campaign_20261115_coexist_10'),
            owner_output=str(root/'operator_chain_20261115_coexist_10'),
            unit='operator-chain-20261115-coexist-10.service')
        save(out/'plan.json',plan); bind(pins,out/'plan.json')
        verify(pins); save(out/'source-pins.json',pins)
        save(out/'status.json',dict(state='PREPARED_NOT_RUN')); return 0
    if Path(__file__).resolve()!=out/'inputs/gate_controls.py':
        raise ValueError('Only the frozen wrapper executes')
    with (out/'attempt.json').open('x') as f:
        f.write(json.dumps(dict(owner_pid=os.getpid(),started=time.time()))+'\n')
    pins=json.loads((out/'source-pins.json').read_text())
    result=dict(state='FAIL',post_source_image_pins_match=False,automatic_retry=False)
    try:
        verify(pins); plan=json.loads((out/'plan.json').read_text())
        result['owner_gate']=wait_owner(plan,pins,out)
        child=Path(plan['child'])
        if (child/'attempt.json').exists():
            raise ValueError('Child already attempted; never retry')
        save(out/'status.json',dict(state='CONTROL_SEQUENCE_EXECUTING',child=str(child)))
        with (out/'child.log').open('x') as f:
            run=subprocess.run([sys.executable,'-B','-u',str(child/'inputs/run_controls_parent.py'),
                'execute','--output',str(child)],stdout=f,stderr=subprocess.STDOUT)
        verify(pins)
        child_result=json.loads((child/'result.json').read_text())
        if run.returncode or child_result['state']!='PASS':
            raise ValueError('Control child failed; successors must not dispatch')
        bind(pins,child/'result.json'); bind(pins,child/'attempt.json')
        verify(pins)
        result.update(state='PASS',child=str(child),completed=child_result['completed'],
                      post_source_image_pins_match=True)
    except Exception as exc:
        result['error']=repr(exc)
    save(out/'final-evidence-pins.json',pins)
    result['final_evidence_pins_sha256']=sha(out/'final-evidence-pins.json')
    save(out/'status.json',dict(state=result['state']))
    save(out/'result.json',result)
    print(json.dumps(result),flush=True)
    return result['state']!='PASS'


if __name__=='__main__':
    raise SystemExit(main())
