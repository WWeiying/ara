"""Full frozen collect with only the reviewed scheduled-flush wave successor."""
import argparse
from pathlib import Path
from types import FunctionType, SimpleNamespace

import collect_scalar_div_subnormal794 as original
import scalar_div_subnormal794_flush_v2 as wave

life=original.life
BASE_SHA='02ee7424a6b21d8073097d8a6389be4393d76fc7a3ab31ce410f1c24f70de8cf'
WAVE_EVIDENCE=life.OUT/'scalar-div-subnormal794-flush-wave-agent-20261008-01.json'
WAVE_SHA='75519fd654e90d18b6882b6f1dcba3ae3e549a1f42a230df4d0d6ce4db1dd330'


def authority():
    source=wave.source_proof()
    evidence=life.read_bound(WAVE_EVIDENCE,WAVE_SHA)
    original.require(evidence['status']=='OFFLINE_WAVE_ONLY_NOT_FULL_QUALIFICATION', 'Exact wave authority')
    life.check(evidence['input_pins'])
    original.require(original.oracle.BASE_SHA==BASE_SHA,'Exact formal794 predecessor')
    base=life.read_bound(original.oracle.BASE/'admission-manifest.json',BASE_SHA)
    for name in ('combined-bits.json','combined-toggle-bits.json'):
        path=original.oracle.BASE/name
        life.read_bound(path,base['output_pins'][str(path)])
    files=(Path(__file__).resolve(),Path(__file__).with_name('test_collect_scalar_div_subnormal794_v2.py'),
        Path(wave.__file__).resolve(),WAVE_EVIDENCE,Path(original.coverage_identity.__globals__['__file__']).resolve())
    pins=life.merge_pins(source['pins'],evidence['input_pins'])
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in files})
    pins=life.merge_pins(pins,{str(original.oracle.BASE/'admission-manifest.json'):BASE_SHA})
    life.check(pins)
    return pins


def exact_toggle_union(before,single):
    original.require(len(before)==len(single)==2989,'Complete2989 Toggle population')
    result=original.toggle.union(before,single)
    original.require(len(result)==2989,'Complete Toggle OR result')
    return result


def publisher(pins):
    def save(path,value):
        if Path(path).name=='qualification.json':
            original.require(value['baseline']==794 and value['baseline_seal']==BASE_SHA,
                'Full qualification current794 binding')
            value=dict(value)
            value['input_pins']=life.merge_pins(value['input_pins'],pins)
            life.check(value['input_pins'])
            value['qualification_authority']=dict(original_collector_sha=wave.OLD_SHA,
                wave_evidence_sha=WAVE_SHA,successor='scheduled_flush_v2',
                cancellation_semantics='Same-edge valid/ready may both be1; flush clear has priority over pipeline-valid load (FFLARNC), so the request creates no surviving owner. Not a no-handshake claim.',
                prospective_admission_population=795,formal_admission_performed=False)
        return life.save(path,value)
    return save


def collect(run,out,seal):
    original.require(not out.exists(),'Fresh independent full qualification output')
    pins=authority()
    private_life=SimpleNamespace(**vars(life));private_life.save=publisher(pins)
    private_toggle=SimpleNamespace(**vars(original.toggle));private_toggle.union=exact_toggle_union
    ns=dict(original.collect.__globals__,wave_audit=wave.wave_audit,life=private_life,toggle=private_toggle)
    FunctionType(original.collect.__code__,ns,closure=original.collect.__closure__)(run,out,seal)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--prepared-seal',required=True)
    a=p.parse_args();collect(a.run.resolve(),a.output.resolve(),a.prepared_seal)
