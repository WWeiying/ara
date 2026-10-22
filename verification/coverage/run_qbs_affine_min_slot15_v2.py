"""Correct exact guard dump binding; preserve the pre-simulation failed predecessor."""
import argparse
from pathlib import Path
from types import FunctionType, SimpleNamespace

import run_qbs_affine_min_slot15 as old

life,require = old.life,old.require
BASE,BASE_SHA,PRE,PRE_SHA,SCOPE = old.BASE,old.BASE_SHA,old.PRE,old.PRE_SHA,old.SCOPE
focused,STAGES = old.focused,old.STAGES


def configuration(stage):
    c = old.configuration(stage)
    require(c['ext_guard'] not in c['ext_dump_objects'],'Predecessor no longer has the reviewed defect')
    c['ext_dump_objects'].append(c['ext_guard'])
    return c


selection = FunctionType(old.selection.__code__,dict(old.selection.__globals__,configuration=configuration))
command = old.command


def prepare(out):
    dependencies = {str(path):life.digest(path) for path in (
        Path(old.__file__).resolve(),Path(__file__).resolve(),
        Path(__file__).with_name('test_run_qbs_affine_min_slot15_v2.py'))}
    def check(pins): return life.check(life.merge_pins(pins,dependencies))
    def save(path,value):
        if path.name.endswith('.prepared.json'):
            value = dict(value,pins=life.merge_pins(value['pins'],dependencies))
        life.save(path,value)
    private = SimpleNamespace(**dict(vars(life),check=check,save=save))
    ns = dict(old.prepare.__globals__,life=private,configuration=configuration,selection=selection,
              command=command,__file__=__file__)
    FunctionType(old.prepare.__code__,ns)(out)


def backend():
    b = old.backend()
    ns = dict(vars(b),configuration=configuration,selection=selection,command=command)
    for name in ('markers','run'):
        ns[name] = FunctionType(getattr(b,name).__code__,ns,name)
    return SimpleNamespace(**ns)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','run'))
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seal')
    a = p.parse_args()
    if a.mode == 'prepare': prepare(a.output.resolve())
    else:
        require(a.seal,'Prepared seal required')
        backend().run('min_scale',a.output.resolve(),a.seal)
