"""Independent cached735->736 preparation; explicit parent authorization for admit."""
import argparse
from pathlib import Path
from types import FunctionType, SimpleNamespace
import json

import prepare_sv39_masked_unit_fault_gain as gain

life,require=gain.life,gain.require
AUTHORIZATION='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'
PRODUCTS={'single-raw-bits.json','combined-bits.json','combined-inputs.txt','raw-delta.json',
          'gained-compiled-points.json','target-reconciliation.json','status.json','evidence-pins.json'}


def gate(state,delta,target):
    gain.qualified.v2.old.runner.exact(state,dict(
        status='SV39_MASKED_FAULT_POSITIVE_RAW735_CANDIDATE_NOT_ADMITTED',baseline=735,proposed_tests=736,
        coverage_admitted=False,new_RTL_signoff=False,official_DVE_report=False,simulations_started=False),
        'Incomplete qualified positive candidate')
    require(state['raw_delta']==delta['metrics'] and set(delta['metrics'])==set(gain.bitmap.METRICS) and
            all(type(n) is int and n>=0 for n in delta['metrics'].values()) and sum(delta['metrics'].values())>0,
            'Zero or malformed gain rejected')
    require(target['scope']==gain.p.SCOPE and target['metric']=='cond' and target['raw_index']==493 and
            target['width']==1140 and target['checksum']=='1370170966' and target['before'] is False and
            type(target['sample']) is bool and target['proposed'] is target['sample'] and
            state['target493_hit'] is target['sample'],'Wrong exact target/hit claim')


def fresh(path):
    require(path.parent==life.OUT and path.resolve()==path and not path.exists(),'Fresh canonical output required')


def candidate(path,seal):
    require(path.parent==life.OUT and path.resolve()==path and not (path/'failure.json').exists(),
            'Canonical successful candidate required')
    receipt=life.read_bound(path/'candidate-seal.json',seal)
    require(receipt['baseline']==str(gain.BASE) and receipt['baseline_seal']==gain.BASE_SEAL and
            receipt['coverage_admitted'] is False and
            set(receipt['output_pins'])=={str(path/n) for n in PRODUCTS-{'evidence-pins.json'}|{'single-inputs.txt'}},
            'Candidate identity/products differ')
    life.check(receipt['input_pins']);life.check(receipt['output_pins'])
    qp=Path(receipt['qualification'])
    qpins,q=gain.qualification(qp,receipt['qualification_seal'])
    pins=life.merge_pins(receipt['input_pins'],qpins)
    pins=life.merge_pins(pins,receipt['output_pins'])
    pins=life.merge_pins(pins,{str(path/'candidate-seal.json'):seal})
    def read(name):return life.read_bound(path/name,receipt['output_pins'][str(path/name)])
    before=life.read_bound(gain.BASE/'combined-bits.json',pins[str(gain.BASE/'combined-bits.json')])
    single=read('single-raw-bits.json')
    require(all(q['input_pins'].get(x)==h for x,h in single['input_hashes'].items()) and
            len(single['input_hashes'])==4,'Unqualified raw metric cache')
    combined,delta=gain.population(before,single)
    require(combined==read('combined-bits.json') and delta==read('raw-delta.json'),
            'Independent735 prefix/OR/delta differs')
    mapper=FunctionType(gain.mapping.gain_points.__code__,dict(gain.mapping.gain_points.__globals__,
        DESIGN=gain.DESIGN,qualified=SimpleNamespace(BUILD=gain.p.BUILD)),
        gain.mapping.gain_points.__name__,gain.mapping.gain_points.__defaults__)
    pins,points=mapper(before,single,combined,pins)
    require(points==read('gained-compiled-points.json'),'Independent compiled gain differs')
    state,target=read('status.json'),read('target-reconciliation.json');gate(state,delta,target)
    for value,key in [(before,'before'),(single,'sample'),(combined,'proposed')]:
        require(target[key] is gain.mapping.hit(value['metrics']['cond'][gain.p.SCOPE],493), 'Target cache differs')
    require((path/'single-inputs.txt').read_text().splitlines()==[str(gain.DESIGN),str(gain.qualified.v2.RUN/'code.vdb')]
            and (path/'combined-inputs.txt').read_text().splitlines()==[str(gain.DESIGN),*combined['tests']],
            'Exact full membership differs')
    require(receipt['result']==state,'Candidate result differs');life.check(pins)
    return receipt,pins


def prepare(path,seal,output,formal):
    fresh(output);fresh(formal);require(output!=formal,'Preparation is not admission')
    receipt,pins=candidate(path,seal)
    deps=(Path(__file__).resolve(),Path(__file__).with_name('test_prepare_sv39_masked_unit_fault_admission.py'))
    pins=life.merge_pins(pins,{str(x):life.digest(x) for x in deps});life.check(pins)
    output.mkdir()
    for name in PRODUCTS-{'evidence-pins.json','status.json'}:
        with (output/name).open('xb') as stream:stream.write((path/name).read_bytes())
    life.save(output/'evidence-pins.json',pins)
    life.save(output/'status.json',dict(receipt['result'],status='SV39_MASKED_FAULT_HISTORICAL736_PREPARED_NOT_ADMITTED'))
    life.check(pins)
    life.save(output/'prepared-seal.json',dict(schema='SV39_MASKED_FAULT_HISTORICAL736_PREPARE_V1',
        output=str(output),formal_output=str(formal),candidate=str(path),candidate_seal=seal,
        qualification=receipt['qualification'],qualification_seal=receipt['qualification_seal'],
        input_pins=pins,output_pins={str(output/n):life.digest(output/n) for n in PRODUCTS},coverage_admitted=False))
    return life.digest(output/'prepared-seal.json')


def check(path,seal):
    require(path.parent==life.OUT and path.resolve()==path,'Canonical preparation required')
    receipt=life.read_bound(path/'prepared-seal.json',seal)
    require(receipt['schema']=='SV39_MASKED_FAULT_HISTORICAL736_PREPARE_V1' and receipt['output']==str(path) and
            receipt['coverage_admitted'] is False and set(receipt['output_pins'])=={str(path/n) for n in PRODUCTS},
            'Prepared identity/products differ')
    life.check(receipt['input_pins']);life.check(receipt['output_pins'])
    original,pins=candidate(Path(receipt['candidate']),receipt['candidate_seal'])
    require(all(receipt['input_pins'].get(str(x))==life.digest(x) for x in
            (Path(__file__).resolve(),Path(__file__).with_name('test_prepare_sv39_masked_unit_fault_admission.py'))),
            'Admission helper/test binding missing')
    require(all(receipt['input_pins'].get(x)==h for x,h in pins.items()),'Inherited candidate pins omitted')
    for name in PRODUCTS-{'evidence-pins.json','status.json'}:
        require((path/name).read_bytes()==(Path(receipt['candidate'])/name).read_bytes(),'Prepared product differs')
    require(life.read_bound(path/'evidence-pins.json',receipt['output_pins'][str(path/'evidence-pins.json')])==receipt['input_pins']
            and life.read_bound(path/'status.json',receipt['output_pins'][str(path/'status.json')])==
            dict(original['result'],status='SV39_MASKED_FAULT_HISTORICAL736_PREPARED_NOT_ADMITTED'), 'Prepared state differs')
    return receipt


def admit(prepared,seal,output,authorization):
    require(authorization==AUTHORIZATION,'Explicit parent authorization required')
    receipt=check(prepared,seal);require(receipt['formal_output']==str(output),'Formal output differs');fresh(output)
    pins=life.merge_pins(receipt['input_pins'],receipt['output_pins'])
    pins=life.merge_pins(pins,{str(prepared/'prepared-seal.json'):seal});life.check(pins)
    output.mkdir()
    for name in PRODUCTS-{'evidence-pins.json','status.json'}:
        with (output/name).open('xb') as stream:stream.write((prepared/name).read_bytes())
    state=json.loads((prepared/'status.json').read_bytes())
    life.save(output/'status.json',dict(state,status='PASS_RAW_UNION_HISTORICAL_ONLY',baseline=735,
        aggregate_passed=736,new_passed=1,coverage_admitted=True,rtl_changed=False,
        full_scalar_differential_qualified=True,whole_scalar_memory_qualified=True,native_DUT_vector_qualified=True))
    life.save(output/'evidence-pins.json',pins);life.check(pins)
    life.save(output/'admission-manifest.json',dict(schema='SV39_MASKED_FAULT_HISTORICAL736_ADMISSION_V1',
        output=str(output),baseline=str(gain.BASE),baseline_seal=gain.BASE_SEAL,prepared=str(prepared),prepared_seal=seal,
        candidate=receipt['candidate'],candidate_seal=receipt['candidate_seal'],qualification=receipt['qualification'],
        qualification_seal=receipt['qualification_seal'],authorization=authorization,
        output_pins={str(output/n):life.digest(output/n) for n in PRODUCTS}))
    return life.digest(output/'admission-manifest.json')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('prepare','check','admit'))
    for name in ('candidate','output','formal-output','prepared'):parser.add_argument('--'+name,type=Path)
    for name in ('seal','authorization'):parser.add_argument('--'+name)
    a=parser.parse_args();require(a.seal,'Seal required')
    if a.mode=='prepare':
        require(a.candidate and a.output and a.formal_output,'Prepare arguments required')
        result=prepare(a.candidate.absolute(),a.seal,a.output.absolute(),a.formal_output.absolute())
    elif a.mode=='check':require(a.prepared,'Prepared path required');check(a.prepared.absolute(),a.seal);result='CHECK_PASS_NOT_ADMITTED'
    else:
        require(a.prepared and a.output and a.authorization,'Admit arguments required')
        result=admit(a.prepared.absolute(),a.seal,a.output.absolute(),a.authorization)
    print(json.dumps(dict(result=result)))


if __name__=='__main__':main()
