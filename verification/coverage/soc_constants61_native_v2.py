"""Exact protected singleton alias successor; native run requires parent review."""
import argparse
import inspect
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

import soc_constants61_native as old

RUN=old.life.OUT/'soc-constants61-native-parent-20261008-01'
SEAL='70f9a405e6d930590295e7bdf3718f24e039c047ecfade0c26bf78620ba15abb'
OLD_SHA='5cc7b57c8004a8dd709218510b7d7aebb89d590bbf069fb533cd674396a36f1c'


class Resolver(old.primitive.indexed.Resolver):
    def __init__(self, instance):
        super().__init__(instance)
        self.targets={s['name'] for s in instance['signals']}

    def matches(self, label, row_type):
        matches=super().matches(label,row_type)
        if matches:return matches
        n=self.names.get(label)
        if (n and n['kind']=='vectornode' and n.get('type') in ('1','3')
                and n.get('portnode')=='0' and row_type=='signal'
                and n['left']==n['right'] and label not in self.targets):
            return [(n,('aggregate',None))]
        return []


def bind(instance, text):
    # Keep every original completeness, role, MDA and target-label guard.
    indexed=SimpleNamespace(**dict(vars(old.primitive.indexed),Resolver=Resolver))
    primitive=SimpleNamespace(**dict(vars(old.primitive),indexed=indexed))
    fn=old.frozen.bind
    return FunctionType(fn.__code__,dict(fn.__globals__,primitive=primitive))(instance,text)


def replay():
    old.need(old.life.digest(old.__file__)==OLD_SHA,'Frozen predecessor source drift')
    c=old.life.read_bound(RUN/'config.json',SEAL)
    old.need(c['instances']==old.instances(old.life.read_bound(old.SOURCE,old.SOURCE_SHA)),
             'Actual compiled/source identity differs')
    aliases=[];rows=0;pins={str(RUN/'config.json'):SEAL}
    for index,i in enumerate(c['instances']):
        path=RUN/('native_before_%d.tsv'%index)
        bound=bind(i,path.read_text());rows+=len(bound);pins[str(path)]=old.life.digest(path)
        original=old.primitive.indexed.Resolver(i)
        for label,row in bound.items():
            if not original.matches(label,row['type']):
                n=Resolver(i).matches(label,row['type'])[0][0]
                aliases.append(dict(scope=i['scope'],label=label,compiled=n,
                                    native=row,protected=True,target=False))
    return dict(status='ALL18_BEFORE_TYPED_BOUND_NOT_NATIVE_QUALIFICATION',
                rows=rows,scopes=len(c['instances']),aliases=aliases,pins=pins,
                EDA_started=False,prepared=False,excluded=False)


def context():
    old.need(old.life.digest(old.__file__)==OLD_SHA,'Frozen predecessor source drift')
    env=dict(vars(old),__file__=__file__,bind=bind,
             SCHEMA='SOC_CONSTANTS61_LOCAL_NATIVE_PREPARED_V2')
    for name in ('before_gate','selection','host_hook','check','verify','run'):
        fn=getattr(old,name)
        env[name]=FunctionType(fn.__code__,env,name,fn.__defaults__)
    # The frozen prepare pins the test explicitly. Change only that filename;
    # the Tcl entry and its complete source closure remain frozen and pinned.
    body=inspect.getsource(old.prepare)
    anchor="test=HERE/'test_soc_constants61_native.py'"
    old.need(body.count(anchor)==1,'Exact frozen prepare test-pin anchor')
    body=body.replace(anchor,"test=HERE/'test_soc_constants61_native_v2.py'")
    exec(compile(body,__file__,'exec'),env)
    return env


def prepare(out):return context()['prepare'](out)
def check(out,seal):return context()['check'](out,seal)
def verify(out,seal):return context()['verify'](out,seal)
def run(out,seal,reviewed):return context()['run'](out,seal,reviewed)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',nargs='?',default='replay',
                   choices=('replay','prepare','check','before','first','second','verify','run'))
    p.add_argument('--output',type=Path);p.add_argument('--seal');p.add_argument('--parent-reviewed-seal')
    a=p.parse_args()
    if a.mode=='replay':print(json.dumps(replay(),indent=2))
    else:
        old.need(a.output is not None,'Explicit fresh/bound output required')
        out=a.output.resolve();env=context()
        if a.mode=='prepare':prepare(out)
        elif a.mode=='run':run(out,a.seal,a.parent_reviewed_seal)
        else:
            c=check(out,a.seal)
            if a.mode=='before':env['before_gate'](out,c)
            elif a.mode in ('first','second'):old.el_gate((out/(a.mode+'.el')).read_text(),c)
            elif a.mode=='verify':verify(out,a.seal)
            print(a.mode+'_PASS')
