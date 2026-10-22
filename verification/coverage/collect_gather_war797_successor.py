"""Offline checker successor; original run, prepared seal and helper stay immutable."""
import argparse
import inspect
from pathlib import Path
from types import FunctionType, SimpleNamespace

import gather_war797 as g

ORIGINAL_SHA = 'fb12449e20e802cbf00ac504e3ff71924a03cd0c99f19c0e8f9e2910db9d6fea'
RUN = g.OUT/'gather-war797-old-image-parent-20261008-01'
SEAL = 'e344e4f083ab58c3f6a30ae6ad7f34cd3991678abffee914403d700bd149cd5f'
PRE = g.OUT/'gather-war797-preflight-agent-20261008-02/preflight.json'
PRE_SHA = 'cd05bebfca68cba72358c6b5185bbb75897ba0dd6bafb2fcab69d6283ccd4371'


def source_pins():
    original=Path(g.__file__).resolve()
    g.require(g.life.digest(original)==ORIGINAL_SHA, 'Immutable original checker drift')
    bookpath=g.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    book=g.life.read_bound(bookpath,'6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b')
    pins={str(original):ORIGINAL_SHA,str(bookpath):g.life.digest(bookpath)}
    code={}
    for rel in ('hardware/src/ara_sequencer.sv','hardware/src/lane/operand_requester.sv',
                'hardware/src/ara_system.sv','hardware/tb/ara_commit_monitor.sv'):
        path=g.ROOT/rel
        g.require(g.life.digest(path)==book[str(path)], 'Frozen monitor/route source drift: '+rel)
        pins[str(path)]=book[str(path)];code[rel]=path.read_text()
    requester=code['hardware/src/lane/operand_requester.sv']
    g.require('verify_wb_id_o[2]    = masku_result_id;' in requester and
              'verify_wb_wdata_o[2] = masku_result_wdata;' in requester and
              'ldu_result_gnt, sldu_result_gnt, masku_result_gnt,' in requester,
              'Exact accepted-write MASKU source2 binding')
    g.require('[VRGATHER:VCOMPRESS]:\n        for (int i = 0; i < NrVFUs; i++)\n          if (i == VFU_Alu || i == VFU_MaskUnit)' in code['hardware/src/ara_sequencer.sv'], 'Frozen Gather route')
    g.require('assign verify_wb_valid[lane] = i_ara.gen_lanes[lane].i_lane.verify_wb_valid_o;' in code['hardware/src/ara_system.sv'] and
              'for (int unsigned source = 0; source < 5; source++)' in code['hardware/tb/ara_commit_monitor.sv'] and
              'cycle_q, uop_arch_seq_q[id], id, lane, source,' in code['hardware/tb/ara_commit_monitor.sv'], 'Monitor source-index transport')
    return pins


def corrected_native():
    source_pins()
    code=inspect.getsource(g.native)
    old="(16,case(phase)['snapshots'][1],3) if role=='gw_gather'"
    new="(16,case(phase)['snapshots'][1],2) if role=='gw_gather'"
    context="        require(activity.vstart==0 and activity.vl==1024, 'Exact full active group')\n"
    marker="        reg,data,producer="
    g.require(code.count(old)==code.count(context)==code.count(marker)==1, 'Exact two-fix successor boundary')
    code=code.replace(old,new).replace(context,'').replace(marker,context+marker)
    ns=dict(g.__dict__)
    exec(compile(code,str(Path(__file__).resolve())+':native','exec'),ns)
    return ns['native']


def collect(run,seal,out):
    g.require(run==RUN and seal==SEAL, 'Only original immutable run/seal')
    pins=source_pins()
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_collect_gather_war797_successor.py').resolve()):
        pins[str(path)]=g.life.digest(path)
    g.life.check(pins)
    inherited=g.mature.mature.evidence_pins
    def evidence_pins(r,s,m):
        return g.life.merge_pins(inherited(r,s,m),pins)
    # Only collector globals change; g.prepare still reconstructs the original seal.
    evidence=SimpleNamespace(**vars(g.mature.mature))
    evidence.evidence_pins=evidence_pins
    mature=SimpleNamespace(**vars(g.mature));mature.mature=evidence
    ns=dict(g.collect.__globals__,native=corrected_native(),mature=mature)
    FunctionType(g.collect.__code__,ns,argdefs=g.collect.__defaults__)(run,seal,out)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run',type=Path,required=True);ap.add_argument('--seal',required=True)
    ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    collect(a.run.resolve(),a.seal,a.output.resolve())
