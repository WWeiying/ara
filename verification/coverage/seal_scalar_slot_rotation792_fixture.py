"""Publish successor preflight for immutable-commit negative tests, same ELF/gold."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import build_scalar_slot_rotation792 as b

PRE=b.OUT/'scalar-slot-rotation792-preflight-agent-20261008-02'
SEAL='0f51226da7eff4c7bd79ad579002a9b252a0eaf3b1cd3c7e1dd46aa72dc5e2c5'


def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True); out=p.parse_args().output.absolute()
    b.require(out.parent==b.OUT and not out.exists() and b.sha(PRE/'preflight-manifest.json')==SEAL,'Fresh exact02 successor')
    m=json.loads((PRE/'preflight-manifest.json').read_bytes()); b.shared.check(m['pins']); b.shared.check(m['output_pins'])
    s=b.elf_shape(PRE/'input.elf'); ledger=b.traps((PRE/'spike.trace').read_text(),s)
    b.require(b.validate(b.reference(PRE/'spike.trace',s),s,ledger)==m['validation'],'Complete preserved gold')
    pins=b.shared.merge_pins(m['pins'],m['output_pins'])
    files=[PRE/'preflight-manifest.json',Path(__file__).resolve(),Path(__file__).with_name('test_scalar_slot_rotation792_fixture.py')]
    pins=b.shared.merge_pins(pins,{str(f):b.sha(f) for f in files}); out.mkdir()
    env=dict(os.environ,SLOT_PREFLIGHT=str(PRE),PYTHONDONTWRITEBYTECODE='1')
    command=[sys.executable,'-B','-m','unittest','test_scalar_slot_rotation792_fixture','-v']
    with (out/'fixture-tests.log').open('x') as log: subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=60,check=True)
    for name in ('input.elf','spike.trace','spike.stdout','compile-command.json','compile.log','spike-command.json','spike-validation.json'):
        shutil.copyfile(PRE/name,out/name)
    b.shared.check(pins)
    m.update(input_elf=str(out/'input.elf'),pins=pins,output_pins={str(f):b.sha(f) for f in out.iterdir()},
        predecessor_seal=SEAL,fixture_tests=dict(executed=4,skipped=0,command=command),
        correction='Frozen SpikeCommit mutation uses dataclasses.replace; no source/ELF/gold changes')
    b.save(out/'preflight-manifest.json',m)
    print(json.dumps(dict(output=str(out),seal=b.sha(out/'preflight-manifest.json'))))


if __name__=='__main__': main()
