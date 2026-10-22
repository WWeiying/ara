"""JSON representation-only prelaunch correction; frozen capture/proof/Tcl unchanged."""
import argparse
import json
from pathlib import Path
from types import FunctionType

import capture_tlb_rvh0_726 as frozen


def proof():
    instances,induction,pins=frozen.proof()
    # JSON converts reviewed writer tuples into arrays; no field/value is removed.
    induction=json.loads(json.dumps(induction))
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_launch_tlb_rvh0_726.py'),Path(frozen.__file__).resolve()):
        pins=frozen.life.merge_pins(pins,{str(p):frozen.life.digest(p)})
    return instances,induction,pins


contract=FunctionType(frozen.contract.__code__,dict(vars(frozen),proof=proof))
verify=FunctionType(frozen.verify.__code__,dict(vars(frozen),contract=contract))
prepare=FunctionType(frozen.prepare.__code__,dict(vars(frozen),proof=proof,__file__=__file__))


def run(out,seal):
    FunctionType(frozen.csr.original.base.runner.run.__code__,dict(vars(frozen.csr.original.base.runner),
                 contract=contract,inspect=verify,HERE=frozen.Route()))(out,seal)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','run','verify','inventory','el'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--stage',choices=frozen.STAGES);p.add_argument('--index',type=int)
    a=p.parse_args();out=a.output.absolute()
    if a.mode=='prepare':prepare(out)
    elif a.mode in ('inventory','el'):
        c=json.loads((out/'config.json').read_bytes());frozen.life.check(c['pins'])
        frozen.require(a.stage in frozen.STAGES,'Five actual stages')
        if a.mode=='inventory':
            frozen.require(a.index in (0,1),'Two actual TLB scopes');print(len(frozen.inventory(out,c,a.stage,a.index)))
        else:
            text=(out/frozen.EL_FILES[a.stage]).read_text()
            if a.stage in ('selected','reloaded'):print(len(frozen.records(text,c)))
            else:frozen.require(text=='','Global empty reset');print(0)
    else:frozen.require(a.seal,'Config seal');(run if a.mode=='run' else verify)(out,a.seal)
