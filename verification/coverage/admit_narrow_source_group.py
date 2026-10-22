"""One parent-plan-bound narrowing candidate, exact736 to737; prepare is not admission. No EDA."""
import argparse
import hashlib
import json
from pathlib import Path

import prepare_narrow_source_group_gain as gain

life,require,OUT=gain.life,gain.require,gain.OUT
GAIN_SHA='ace911d24dbdf0d25f2c2da27a95f5d9250bc233102048b0645807616d988ca4'
BASE=OUT/'sv39-masked-offline-admitted-736-parent-20261006-01'
BASE_SEAL='a46222989c3c88436c5e2f431eaafa3b8790ffa9fa05bd65920dc695b6088784'
PLAN=OUT/'narrow-source-group-gain-plan-736-parent-20261006-01/plan.json'
PLAN_SEAL='6693e705bbce1fa15e3679d83408c4b5fb22455bdcacc14c8c274d9dc0273f38'
CANDIDATE=OUT/'narrow-source-group-raw-gain-736-parent-20261006-01'
CANDIDATE_SEAL='04869a7a3dc48b53748b9043b00a27fd63df6670b1cb1155b073801af4761541'
SCHEMA='NARROW_SOURCE_GROUP_HISTORICAL_ADMISSION_V1'


def serialized(value):return (json.dumps(value,indent=2)+'\n').encode()


def gate(record):
    require(record['output']==str(CANDIDATE) and record['status']==gain.POSITIVE and record['primary_fresh_gain'] is True and
        record['qualification']==str(gain.QUAL) and record['qualification_seal']==gain.QUAL_SEAL and
        record['full_OR_instances']==6162 and record['exact735_prefix'] is True and
        record['baseline']==str(BASE) and record['baseline_seal']==BASE_SEAL and
        record['plan']==str(PLAN) and record['plan_seal']==PLAN_SEAL and
        record['baseline_tests']==736 and record['proposed_population']==737,
        'Only exact qualified positive primary candidate allowed')
    require(set(record['raw_delta'])==set(gain.bitmap.METRICS) and
        all(type(v) is int and v>=0 for v in record['raw_delta'].values()) and
        sum(record['raw_delta'].values())>0,'Actual positive raw gain required; zero gain HOLD')
    for key in ('coverage_admitted','application_approval','DVE_native_exclusion_qualified',
                'native_cycle_qualified'):
        require(record[key] is False,'Candidate boundary promoted: '+key)


def evaluate(directory,seal):
    require(directory==CANDIDATE and seal==CANDIDATE_SEAL,'Exact parent candidate/seal required')
    require(directory.parent==OUT and directory.resolve()==directory,'Direct candidate directory required')
    require(life.digest(Path(gain.__file__))==GAIN_SHA,'Frozen gain helper drift')
    header=life.read_bound(directory/'candidate.json',seal);gate(header)
    record=gain.verify(directory,seal);gate(record)
    pins=json.loads((directory/'evidence-pins.json').read_bytes())
    pins=life.merge_pins(pins,record['output_pins'])
    pins=life.merge_pins(pins,{str(directory/'candidate.json'):seal})
    def read(name):
        path=directory/name
        return life.read_bound(path,record['output_pins'][str(path)])
    single,combined,delta,hits=read('single-bits.json'),read('combined-bits.json'),read('raw-delta.json'),read('target-hits.json')
    gain.validate_targets(hits)
    require(delta['metrics']==record['raw_delta'] and any(h['before_hit'] is False and
            h['single_hit'] is True and h['fresh_target_gain'] is True for h in hits),
            'Actual source-bound CSR target gain witness differs')
    qual=life.read_bound(gain.QUAL,gain.QUAL_SEAL);gain.qualification(qual)
    gain.rejected_proof(life.read_bound(gain.QUAL.parent/'lifecycle.json',
                        qual['pins'][str(gain.QUAL.parent/'lifecycle.json')]))
    pins=life.merge_pins(pins,qual['pins'])
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_narrow_source_group.py')):
        pins=life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    status=dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',baseline=record['baseline_tests'],
        aggregate_passed=record['proposed_population'],new_passed=1,coverage_admitted=True,
        exact735_prefix=True,exact736_prefix=True,full_OR_instances=6162,raw_delta=record['raw_delta'],
        case=gain.p.NAME,checks=2130,full_memory_bytes=2112,native_known_write_bytes=1032,expected_traps=1,
        cause=2,exact_opcode_tval_and_mepc=True,preserved_CSR_values=12,RD_sentinels=1,rejected_backend_uops=0,rejected_VRF_activities=0,UVM_errors=0,UVM_override_applied=False,
        terminal_source='FOREGROUND_RUNNER_OS_RETURN_RECEIPT',OS_returncode=0,
        full_ISA_reference_verified=False,whole_ISA_qualified=False,
        qualification_scope='Exact sealed narrowing source-alignment rejection with zero backend/VRF; full scalar Spike/vector/CSR/trap/memory recovery for this case only',
        native_cycle_qualified=False,DVE_native_exclusion_qualified=False,
        historical_fixed_image_only=True,new_RTL_signoff=False,official_denominator_verified=False,
        application_approval=False,rtl_changed=False,simulations_started=False,
        qualification_seal=gain.QUAL_SEAL,candidate_seal=seal)
    products={'combined-bits.json':combined,'single-bits.json':single,'raw-delta.json':delta,
        'target-hits.json':hits,'qualified-runtime-audit.json':qual,'evidence-pins.json':pins,'status.json':status}
    text='\n'.join([str(gain.DESIGN),*combined['tests']])+'\n'
    require(text==(directory/'combined-inputs.txt').read_text(),'Exact candidate prefix text differs')
    return record,products,text


def fingerprints(out,products,text):
    pins={str(out/n):hashlib.sha256(serialized(v)).hexdigest() for n,v in products.items()}
    pins[str(out/'combined-inputs.txt')]=hashlib.sha256(text.encode()).hexdigest()
    return pins


def approval(record,seal,proposal,authorized):
    require(authorized is True and seal is not None,'Separate parent authorization and prepared seal required')
    require(life.read_bound(record,seal)==proposal,'Reviewed admission proposal drift')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','admit','verify'))
    parser.add_argument('--candidate',type=Path,required=True);parser.add_argument('--candidate-seal',required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--seal')
    parser.add_argument('--parent-authorized',action='store_true');a=parser.parse_args(argv)
    require((a.mode!='prepare')==bool(a.seal),'External seal required for admit/verify')
    require((a.mode=='admit')==a.parent_authorized,'Only separately authorized admit uses --parent-authorized')
    out=a.output.absolute();sidecar=out.with_name(out.name+'.prepared.json');directory=a.candidate.absolute()
    require(out.parent==OUT and out.resolve()==out,'Direct independent output required')
    if a.mode!='verify':
        require(not out.exists(),'Fresh formal output required')
        if a.mode=='prepare':require(not sidecar.exists(),'Fresh reviewed sidecar required')
    record,products,text=evaluate(directory,a.candidate_seal)
    hashes=fingerprints(out,products,text)
    proposal=dict(schema=SCHEMA+'_PREPARED',output=str(out),candidate=str(directory),candidate_seal=a.candidate_seal,
        baseline=record['baseline'],baseline_seal=record['baseline_seal'],qualification=str(gain.QUAL),
        qualification_seal=gain.QUAL_SEAL,input_pins=products['evidence-pins.json'],output_pins=hashes,
        raw_delta=record['raw_delta'],population=record['proposed_population'],checks=2130,
        exact735_prefix=True,exact736_prefix=True,full_OR_instances=6162,application_approval=False,simulations_started=False)
    if a.mode=='prepare':
        life.save(sidecar,proposal)
        print(json.dumps(dict(prepared=str(sidecar),seal=life.digest(sidecar),coverage_admitted=False)));return
    if a.mode=='verify':
        manifest=life.read_bound(out/'admission-manifest.json',a.seal)
        require(manifest['schema']==SCHEMA and manifest['output']==str(out) and
            manifest['candidate']==str(directory) and manifest['candidate_seal']==a.candidate_seal and
            manifest['qualification_seal']==gain.QUAL_SEAL and manifest['output_pins']==hashes and
            manifest['baseline']==str(BASE) and manifest['baseline_seal']==BASE_SEAL and
            manifest['prepared']==str(sidecar),
            'Formal admission replay differs')
        require(life.read_bound(sidecar,manifest['prepared_seal'])==proposal,'Reviewed prepared lineage differs')
        life.check(hashes);print('OFFLINE_HISTORICAL_ADMISSION_REVERIFIED');return
    approval(sidecar,a.seal,proposal,a.parent_authorized)
    life.check(products['evidence-pins.json']);require(not out.exists(),'Output appeared during replay');out.mkdir()
    for n,v in products.items():life.save(out/n,v)
    (out/'combined-inputs.txt').write_text(text)
    life.check(products['evidence-pins.json']);life.check(hashes)
    life.save(out/'admission-manifest.json',dict(schema=SCHEMA,output=str(out),candidate=str(directory),
        candidate_seal=a.candidate_seal,baseline=record['baseline'],baseline_seal=record['baseline_seal'],
        qualification_seal=gain.QUAL_SEAL,prepared=str(sidecar),prepared_seal=a.seal,output_pins=hashes))
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'admission-manifest.json'))))


if __name__=='__main__':main()
