"""One reviewed fault/recovery candidate; prepare is not admission. No EDA."""
import argparse
import hashlib
import json
from pathlib import Path

import prepare_store_fault_flush_gain as gain

life,require,OUT=gain.life,gain.require,gain.OUT
GAIN_SHA='810f57cea1c4f2d9d4c3e8293b01522f2cb99f14cc6b5296b9b3b5ccc7fae394'
SCHEMA='STORE_FAULT_FLUSH_HISTORICAL_ADMISSION_V1'


def serialized(value):return (json.dumps(value,indent=2)+'\n').encode()


def gate(record):
    require(record['status']==gain.POSITIVE and record['primary_fresh_gain'] is True and
        record['qualification']==str(gain.QUAL) and record['qualification_seal']==gain.QUAL_SEAL and
        record['full_OR_instances']==6162 and record['exact732_prefix'] is True and
        record['baseline_tests']>=732 and record['proposed_population']==record['baseline_tests']+1,
        'Only exact qualified positive primary candidate allowed')
    require(set(record['raw_delta'])==set(gain.bitmap.METRICS) and
        all(type(v) is int and v>=0 for v in record['raw_delta'].values()) and
        sum(record['raw_delta'].values())>0,'Actual positive raw gain required; zero gain HOLD')
    for key in ('coverage_admitted','application_approval','DVE_native_exclusion_qualified',
                'native_B_error_plus_addr_fault_timing_measured'):
        require(record[key] is False,'Candidate boundary promoted: '+key)


def evaluate(directory,seal):
    require(directory.parent==OUT and directory.resolve()==directory,'Direct candidate directory required')
    require(life.digest(Path(gain.__file__))==GAIN_SHA,'Frozen gain helper drift')
    record=gain.verify(directory,seal);gate(record)
    pins=json.loads((directory/'evidence-pins.json').read_bytes())
    pins=life.merge_pins(pins,record['output_pins'])
    pins=life.merge_pins(pins,{str(directory/'candidate.json'):seal})
    def read(name):
        path=directory/name
        return life.read_bound(path,record['output_pins'][str(path)])
    single,combined,delta,hits=read('single-bits.json'),read('combined-bits.json'),read('raw-delta.json'),read('target-hits.json')
    require(delta['metrics']==record['raw_delta'] and hits[0]['role']=='primary' and
            hits[0]['before_hit'] is False and hits[0]['single_hit'] is True and
            hits[0]['fresh_target_gain'] is True,'Actual primary gain witness differs')
    qual=life.read_bound(gain.QUAL,gain.QUAL_SEAL);gain.qualification(qual)
    pins=life.merge_pins(pins,qual['pins'])
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_store_fault_flush.py')):
        pins=life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    status=dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',baseline=record['baseline_tests'],
        aggregate_passed=record['proposed_population'],new_passed=1,coverage_admitted=True,
        exact732_prefix=True,full_OR_instances=6162,raw_delta=record['raw_delta'],
        case=gain.p.NAME,checks=134,source_destination_dump_words=100,expected_traps=1,
        cause=7,tval=gain.p.BAD,vstart=0,recovery_words=8,UVM_errors=0,UVM_override_applied=False,
        terminal_source='FOREGROUND_RUNNER_OS_RETURN_RECEIPT',OS_returncode=0,
        full_ISA_reference_verified=False,whole_ISA_qualified=False,
        qualification_scope='Exact sealed scalar/retirement/native VRF/memory/trap/source guards for this case only',
        native_B_error_plus_addr_fault_timing_measured=False,DVE_native_exclusion_qualified=False,
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
        raw_delta=record['raw_delta'],population=record['proposed_population'],checks=134,
        exact732_prefix=True,full_OR_instances=6162,application_approval=False,simulations_started=False)
    if a.mode=='prepare':
        life.save(sidecar,proposal)
        print(json.dumps(dict(prepared=str(sidecar),seal=life.digest(sidecar),coverage_admitted=False)));return
    if a.mode=='verify':
        manifest=life.read_bound(out/'admission-manifest.json',a.seal)
        require(manifest['schema']==SCHEMA and manifest['output']==str(out) and
            manifest['candidate']==str(directory) and manifest['candidate_seal']==a.candidate_seal and
            manifest['qualification_seal']==gain.QUAL_SEAL and manifest['output_pins']==hashes,
            'Formal admission replay differs')
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
