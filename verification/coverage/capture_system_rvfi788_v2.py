"""Namespace-only successor; frozen 01 proof, inventory and semantic verifier unchanged."""
import argparse
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

import capture_system_rvfi788 as original

life,require=original.life,original.require
HERE=Path(__file__).resolve().parent
HOOK=HERE/'capture_system_rvfi788_v2.tcl'


def prepare(out):
    dependencies=(Path(__file__).resolve(),HERE/'test_capture_system_rvfi788_v2.py',
        Path(original.__file__).resolve(),original.HOOK,HERE/'export_dve_coverage.tcl')
    pins={str(p):life.digest(p) for p in dependencies}
    def save(path,value):
        if path==out/'config.json':
            value['pins']=life.merge_pins(value['pins'],pins)
            value['successor']='global-selection-namespace-only'
            value['original_failure_preserved']=str(life.OUT/'system-rvfi788-native-agent-20261007-01')
            life.check(value['pins'])
        life.save(path,value)
    private=SimpleNamespace(**dict(vars(life),save=save))
    worker=FunctionType(original.prepare.__code__,dict(original.prepare.__globals__,life=private,
        HOOK=HOOK,__file__=__file__))
    worker(out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','run','verify','el','inventory'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--file',choices=('first.el','second.el'))
    p.add_argument('--stage');a=p.parse_args();out=a.output.absolute()
    if a.mode=='prepare':prepare(out)
    elif a.mode in ('el','inventory'):
        c=json.loads((out/'config.json').read_bytes());life.check(c['pins'])
        if a.mode=='el':require(a.file,'EL required');print('EXACT788 '+str(len(original.records((out/a.file).read_text(),c))))
        else:print('FULL_NATIVE_INVENTORY '+str(len(original.inventory(out,c,a.stage))))
    else:
        require(a.seal,'Config seal required');(original.run if a.mode=='run' else original.verify)(out,a.seal)
