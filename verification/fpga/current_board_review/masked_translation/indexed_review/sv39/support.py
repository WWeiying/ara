"""Read-only reuse of accepted image gates without colliding reference modules."""
import importlib.util
from pathlib import Path
import sys
import reference as ref

HERE=Path(__file__).resolve().parent
EXT=HERE.parents[1]/'sv39_extended'


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def accepted_helpers():
    names=('reference','csv_check','prepare_vcs_plan')
    previous={n:sys.modules.get(n) for n in names}
    try:
        for n in names:
            sys.modules[n]=load(EXT/(n+'.py'),'nf7_accepted_'+n)
        return load(EXT/'successor.py','nf7_accepted_successor')
    finally:
        for n,module in previous.items():
            if module is None:
                sys.modules.pop(n,None)
            else:
                sys.modules[n]=module


def read(path):
    import json
    return json.loads(Path(path).read_text())


def save(path,value):
    import json
    with Path(path).open('x') as stream:
        json.dump(value,stream,indent=2)
        stream.write('\n')
