"""Thin cached full8 run/offline-qualification adapter; one run, same gold and full checks."""
import argparse
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

import run_gap113_payload_full8 as frozen_run
import qualify_gap113_payload_full8 as frozen_qual

life=frozen_run.life
PRE=life.OUT/'gap113-payload-full8-cached-preflight-741-agent-20261007-01'
SEAL='8c4854090c2134d1c08f72e5b0467c98be29cb27d2f73ccca2dec9c8c521ef37'
NAME='qbs_gap113_payload_full8_cached'
ELF_SHA='ecf747a5c59d6c439819b2d7757a932684e52b16f183536660476d517b4165a5'
RUN=life.OUT/'gap113-payload-full8-cached-old-image-741-agent-20261007-01'


def run_adapter():
    namespace=dict(vars(frozen_run),PRE=PRE,SEAL=SEAL,NAME=NAME,ELF_SHA=ELF_SHA)
    for name in ('validate','prepare'):
        namespace[name]=FunctionType(getattr(frozen_run,name).__code__,namespace,name)
    return SimpleNamespace(**namespace)


def prepare():
    r=run_adapter();out,record=r.prepare(RUN)
    pre=record['preflight']
    if pre.get('initialization')!='STATIC_CONST_SAME_PINNED_FULL8_NATIVE_BYTES' or \
            pre.get('commands_changed') is not False or pre.get('scalar_oracle_checks_reduced') is not False:
        raise ValueError('Only input initialization caching allowed')
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_run_gap113_full8_cached.py'),
              Path(frozen_run.__file__),Path(frozen_qual.__file__)):
        record['pins']=life.merge_pins(record['pins'],{str(p):life.digest(p)})
    record['budget_basis']=('Original full8 timeout issued zero QBEXECs; 183389/200661 completed retirements '
                           'were initializer main. Same 7040 input bytes are now ELF constants; all runtime checks retained.')
    life.check(record['pins'])
    return out,record


def qualifier(run_seal):
    namespace=dict(vars(frozen_qual),RUN=RUN,RUN_SEAL=run_seal,runner=run_adapter())
    namespace['recipe']=SimpleNamespace(**dict(vars(frozen_qual.recipe),
        APP=life.ROOT/'apps/qbs_gap113_payload_full8_cached'))
    for name,value in vars(frozen_qual).items():
        if isinstance(value,FunctionType) and value.__module__==frozen_qual.__name__:
            namespace[name]=FunctionType(value.__code__,namespace,name,value.__defaults__,value.__closure__)
    return SimpleNamespace(**namespace)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','run','qualify'))
    p.add_argument('--prepared-seal');p.add_argument('--output',type=Path);a=p.parse_args()
    record_path=RUN.with_name(RUN.name+'.prepared.json')
    if a.mode=='prepare':
        if a.prepared_seal or a.output or record_path.exists():p.error('Fresh prepare only')
        out,record=prepare();life.save(record_path,record)
        print(json.dumps(dict(prepared=str(record_path),seal=life.digest(record_path),pins=len(record['pins']))))
    elif a.mode=='run':
        if not a.prepared_seal or a.output:p.error('Run requires exact prepared seal')
        out,record=prepare()
        if life.read_bound(record_path,a.prepared_seal)!=record:raise ValueError('Prepared run drift')
        frozen_run.reused.run(out,record)
    else:
        if not a.prepared_seal or not a.output:p.error('Offline qualify requires run seal and fresh output')
        record=life.read_bound(record_path,a.prepared_seal);life.check(record['pins'])
        q=qualifier(a.prepared_seal);plan=q.prepare();plan['pins']=life.merge_pins(plan['pins'],record['pins'])
        print(json.dumps(q.collect(plan,a.output.absolute())))


if __name__=='__main__':main()
