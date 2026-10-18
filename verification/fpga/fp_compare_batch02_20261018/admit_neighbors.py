#!/usr/bin/env python3
"""Wrap the sealed forty-case integer-neighbor manifest without editing it."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import run as base


def main():
    source=HERE/'neighbors';manifest=source/'programs.json';seal=source/'seal.json'
    receipt=json.loads(seal.read_text())
    assert receipt['state']=='sealed_ready_for_fixed_vcs'
    assert base.sha(manifest)==receipt['manifest_sha256']
    plan=json.loads(manifest.read_text())
    for group in ('pins','files'):
        for path,digest in plan[group].items():assert base.sha(path)==digest,path
    assert receipt['spike_exit_code']==0
    assert receipt['spike_count_at_replay_exit_decimal']==923143
    plan['pins'][str(manifest)]=base.sha(manifest)
    plan['pins'][str(seal)]=base.sha(seal)
    out=HERE/'neighbors_admitted01';out.mkdir(exist_ok=False)
    base.save(out/'prepared.json',plan)
    print('ADMITTED_NEW40_INTEGER_NEIGHBORS_NOT_DUT',flush=True)


if __name__=='__main__':main()
