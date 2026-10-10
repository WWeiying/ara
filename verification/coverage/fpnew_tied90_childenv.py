"""Environment-only fresh successor; exact frozen binder and five-stage gates."""
import argparse
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace
import fpnew_tied90_local as frozen

HERE=Path(__file__).resolve().parent
TCL=HERE/'fpnew_tied90_childenv.tcl'
CHILD_PATH=str(frozen.life.ROOT/'verification/tools/soc-venv/lib/python3.9/site-packages')
FROZEN_SHA='28adbc9ab37b6296ac4b0c08f3d8e293471a894d47a39b467f17edf960e04e0b'
FROZEN_TCL_SHA='1770cb668fc8c3d05b9f7f4113cbd43603a6a7d3b3d1a0dfa96c2bd73a163757'
OFFLINE=frozen.life.OUT/'fpnew90-before-offline-binding-agent-20261008-01.json'


def boundary():
    frozen.need(frozen.life.digest(frozen.__file__)==FROZEN_SHA and
                frozen.life.digest(frozen.TCL)==FROZEN_TCL_SHA,'Exact environment-only predecessor')
    text=TCL.read_text()
    frozen.need(text.count('PYTHONPATH=$child_path')==1 and
                'set child_path {'+CHILD_PATH+'}' in text and '/usr/bin/env' in text,
                'Single exact sealed child path; no inherited path')
    files=[Path(__file__).resolve(),TCL,HERE/'test_fpnew_tied90_childenv.py',Path('/usr/bin/env'),OFFLINE]
    files+=sorted((Path(CHILD_PATH)/'elftools').rglob('*.py'))
    frozen.need(len(files)>5,'Real elftools package source required')
    pins={str(p):frozen.life.digest(p) for p in files}
    q=json.loads(OFFLINE.read_bytes());frozen.life.check(q['pins'])
    frozen.need(q['status']=='EXACT90_REAL_BEFORE_TYPED_BINDING_PASS_NOT_FIVE_STAGE_QUALIFICATION' and
                q['local_qualified'] is False and q['native_rows']==3286 and len(q['targets'])==90,
                'Actual all70 before binding; never local qualification')
    return pins


def context():
    namespace=dict(vars(frozen),TCL=TCL,__file__=__file__)
    namespace['host_hook']=FunctionType(frozen.host_hook.__code__,namespace)
    base_check=FunctionType(frozen.check.__code__,namespace)
    def check(out,seal):
        c=base_check(out,seal)
        frozen.need(c.get('child_environment')=={'PYTHONPATH':CHILD_PATH} and
                    c.get('frozen_predecessor_sha256')==FROZEN_SHA,'Exact successor environment contract')
        for path,sha in boundary().items():
            frozen.need(c['pins'].get(path)==sha,'Required successor dependency: '+path)
        return c
    namespace['check']=check
    namespace['verify']=FunctionType(frozen.verify.__code__,namespace)
    namespace['run']=FunctionType(frozen.run.__code__,namespace)
    return namespace


def prepare(out):
    pins=boundary();namespace=context()
    def save(path,value):
        if path==out/'config.json':
            value=dict(value,child_environment={'PYTHONPATH':CHILD_PATH},frozen_predecessor_sha256=FROZEN_SHA,
                       pins=frozen.life.merge_pins(value['pins'],pins))
        frozen.life.save(path,value)
    namespace['life']=SimpleNamespace(**dict(vars(frozen.life),save=save))
    FunctionType(frozen.prepare.__code__,namespace)(out)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','check','before','first','second','verify','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--parent-reviewed-seal')
    a=p.parse_args();out=a.output.resolve()
    if a.mode=='prepare':prepare(out)
    else:
        ns=context();c=ns['check'](out,a.seal)
        if a.mode=='before':frozen.before_gate(out,c)
        elif a.mode in ('first','second'):frozen.el_gate((out/(a.mode+'.el')).read_text(),c)
        elif a.mode=='verify':ns['verify'](out,a.seal)
        elif a.mode=='run':ns['run'](out,a.seal,a.parent_reviewed_seal)
        print(a.mode+'_PASS')
