"""Exact tuple/list receipt closure only; replay frozen verifier without writes."""
import argparse
import inspect
import json
from pathlib import Path

import cvxif_padding_native776_v2 as frozen

life, require = frozen.life, frozen.require
CAPTURE = life.OUT / 'cvxif-padding-native776-parent-20261007-01'
CONFIG_SHA = 'b8a9d69555ba6e5e49629ad86a9de0bb07ef65b13f3541d99121c464b0e6b065'
RECEIPT_SHA = 'f65038f4f544545c87180a3a25085a000b60e587a3ef511d89777d01b0afeecd'
MESSAGE = 'Existing qualification receipt differs'


def counts(value, runtime=False):
    require(type(value) is list and len(value) == 2, 'Exact two native scope counts')
    result = []
    for row in value:
        require(type(row) in ((tuple,list) if runtime else (list,)) and len(row) == 2 and
                all(type(n) is int and n >= 0 for n in row) and row[0]-row[1] == 5,
                'Count schema: integers only, five target vectors per scope')
        result.append(list(row))
    return result


def audit_pair(value):
    require(type(value) in (tuple,list) and len(value)==2 and
            all(type(n) is int and n>=0 for n in value) and value[0]-value[1]==5,
            'Audit pair: exact integers and five target vectors')
    return list(value)


def exact(a, b):
    require(type(a) is type(b), 'Non-count field type changed')
    if type(a) is dict:
        require(a.keys() == b.keys(), 'Receipt keys differ')
        for key in a: exact(a[key],b[key])
    elif type(a) is list:
        require(len(a) == len(b), 'Non-count list length changed')
        for x,y in zip(a,b): exact(x,y)
    else: require(a == b, 'Non-count field value changed')


def reconcile(saved, actual):
    require(type(saved) is dict and type(actual) is dict and saved.keys() == actual.keys(), 'Exact receipt schema')
    require('native_inventory_counts' in saved, 'Missing count field')
    require(counts(saved['native_inventory_counts']) == counts(actual['native_inventory_counts'],True), 'Counts differ')
    exact({k:v for k,v in saved.items() if k!='native_inventory_counts'},
          {k:v for k,v in actual.items() if k!='native_inventory_counts'})


def closure():
    saved = life.read_bound(CAPTURE/'capture-result.json',RECEIPT_SHA)
    require(inspect.getsource(frozen.base.verify).count(MESSAGE)==1, 'Unique frozen final comparison')
    calls=[]
    def closed_audit(instance, stages):
        return audit_pair(frozen.base.audit(instance,stages))
    def final_gate(ok, message):
        if message != MESSAGE: return require(ok,message)
        frame=inspect.currentframe().f_back
        require(frame.f_code is frozen.base.verify.__code__, 'Exact original verifier callsite')
        actual=frame.f_locals['result']; del frame
        require(ok is True, 'Original full receipt comparison must pass after count normalization')
        reconcile(saved,actual);calls.append(counts(actual['native_inventory_counts']))
        return require(ok,message)
    # Every original source/tool/terminal/cgroup/EL/low-bit/protection/snapshot
    # gate runs unchanged. Only each audit count pair's JSON representation changes.
    frozen.clone(frozen.base.verify,require=final_gate,audit=closed_audit)(CAPTURE,CONFIG_SHA)
    require(len(calls)==1 and life.digest(CAPTURE/'capture-result.json')==RECEIPT_SHA, 'Once replay; original receipt immutable')
    pins=dict(saved['pins']);pins[str(CAPTURE/'capture-result.json')]=RECEIPT_SHA
    for file in (Path(__file__).resolve(),Path(__file__).with_name('test_close_cvxif_padding776_offline.py').resolve()):
        pins[str(file)]=life.digest(file)
    return dict(status='PASSIVE_CVXIF_PADDING10_NATIVE_OFFLINE_RECEIPT_CLOSED_NOT_APPLIED',
        config_seal=CONFIG_SHA,original_capture_result_sha256=RECEIPT_SHA,
        normalization_only='native_inventory_counts tuple pairs -> JSON list pairs',
        native_inventory_counts=calls[0],all_original_gates_replayed=True,pins=pins,
        objects=10,directions=18516,protected_objects=76,semantic_reload=True,final_reset=True,
        DUT_functional_gain=False,population_application=False,EDA_launched=False,
        original_files_modified=False,official_denominator_verified=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();require(out.parent==life.OUT and not out.exists(),'Fresh independent closure file')
    result=closure();life.save(out,result)
    print(json.dumps(dict(output=str(out),seal=life.digest(out),status=result['status'])))
