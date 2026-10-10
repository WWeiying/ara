"""Qualification-gated singleton raw gain candidate; never simulation/admission."""
import argparse
from collections import Counter
from pathlib import Path
from types import FunctionType, SimpleNamespace
import json

import qualify_sv39_masked_unit_fault_terminal_v3 as qualified
import collect_operand_index_snapshot_raw_724 as mapping

life,require=qualified.life,qualified.require
p=qualified.v2.p
bitmap=mapping.bitmap
BASE=life.OUT/'readonly-csr-offline-admitted-735-parent-20261006-01'
BASE_SEAL='4fb3c0219a791c9a669ad9403d97634042f57b423e0e94d7c65bdf57cfa59397'
DESIGN=p.BUILD/'sim/simv.vdb'


def qualification_gate(q):
    result=q['result']
    qualified.v2.old.runner.exact(result,dict(
        status='SV39_MASKED_UNIT_FAULT_FULL_SCALAR_RVC_NATIVE_GOLD_PASS_NOT_ADMITTED',
        baseline=735,baseline_seal=BASE_SEAL,checks=85,whole_scalar_memory_qualified=True,
        full_scalar_differential_qualified=True,native_DUT_vector_qualified=True,
        bitmap_not_collected=True,coverage_admitted=False,rtl_changed=False),
        'Complete v3 native/scalar qualification required')


def population(before,single):
    mapping.validate_bitmap(before);mapping.validate_bitmap(single)
    require(len(before['tests'])==len(set(before['tests']))==735 and
            single['tests']==[str(qualified.v2.RUN/'code.vdb')], 'Exact735 plus sole qualified sample required')
    life.merge_pins(before['input_hashes'],single['input_hashes'])
    proposed=bitmap.combine(before,single)
    require(proposed['tests'][:-1]==before['tests'] and len(set(proposed['tests']))==736,
            'Exact735 prefix/unique736 union required')
    delta=bitmap.delta(before,proposed)
    require(set(delta['metrics'])==set(bitmap.METRICS) and all(type(n) is int and n>=0
            for n in delta['metrics'].values()) and sum(delta['metrics'].values())>0,
            'Zero/malformed gain cannot prepare admission candidate')
    return proposed,delta


def qualification(path,seal):
    require(path.parent==life.OUT and path.resolve()==path and not (path/'failure.json').exists(),
            'Fresh successful canonical qualification required')
    q=life.read_bound(path/'qualification-seal.json',seal);qualification_gate(q)
    require(all(Path(x).parent==path for x in q['output_pins']), 'Foreign qualification output')
    life.check(q['input_pins']);life.check(q['output_pins'])
    pins=life.merge_pins(q['input_pins'],q['output_pins'])
    pins=life.merge_pins(pins,{str(path/'qualification-seal.json'):seal})
    planpaths=[Path(x) for x in q['input_pins'] if Path(x).name=='successor-plan.json']
    require(len(planpaths)==1,'Unique sealed v3 plan required')
    qualified.verify(planpaths[0],q['input_pins'][str(planpaths[0])])
    vector=life.read_bound(path/'vector-comparison.json',q['output_pins'][str(path/'vector-comparison.json')])
    proof=vector['case_only_fault_proof']
    require(vector['status']=='PASS' and vector['verified_identity_write_traps']==
            [dict(arch_seq=243,compared_bytes=128)] and proof['maintenance_known_bytes']==128 and
            proof['load_accepted_bytes']==0 and proof['zero_write_fault_claimed'] is False,
            'Missing exact maintenance identity/load-fault qualification')
    vdb=qualified.v2.RUN/'code.vdb'
    require(not any(x.is_symlink() for x in vdb.rglob('*')) and
            sorted(str(x) for x in vdb.rglob('*') if x.is_file())==
            sorted(x for x in q['input_pins'] if Path(x).is_relative_to(vdb)),
            'Qualified VDB membership changed')
    return pins,q


def prepare(qualification_path,qualification_seal,output):
    require(output.parent==life.OUT and output.resolve()==output and not output.exists(), 'Fresh direct output required')
    pins,q=qualification(qualification_path,qualification_seal)
    binding,basepins=p.bind_baseline(BASE,BASE_SEAL)
    manifest=life.read_bound(BASE/'admission-manifest.json',BASE_SEAL)
    require(manifest['schema']=='READONLY_CSR_HISTORICAL_ADMISSION_V1','Exact735 formal schema required')
    pins=life.merge_pins(pins,basepins)
    inherited=life.read_bound(BASE/'evidence-pins.json',pins[str(BASE/'evidence-pins.json')])
    pins=life.merge_pins(pins,inherited)
    before=life.read_bound(BASE/'combined-bits.json',pins[str(BASE/'combined-bits.json')])
    require(all(pins.get(x)==h for x,h in before['input_hashes'].items()), 'Inherited metric pins missing')
    dependencies=(Path(__file__).resolve(),Path(__file__).with_name('test_prepare_sv39_masked_unit_fault_gain.py'),
                  Path(mapping.__file__).resolve(),Path(bitmap.__file__).resolve(),Path(mapping.shape.__file__).resolve())
    pins=life.merge_pins(pins,{str(x):life.digest(x) for x in dependencies});life.check(pins)
    output.mkdir()
    try:
        (output/'single-inputs.txt').write_text(str(DESIGN)+'\n'+str(qualified.v2.RUN/'code.vdb')+'\n')
        single=bitmap.collect(output/'single-inputs.txt')
        require(len(single['input_hashes'])==4 and all(q['input_pins'].get(x)==h for x,h in
                single['input_hashes'].items()),'Unqualified sample metric bytes')
        proposed,delta=population(before,single)
        gain=FunctionType(mapping.gain_points.__code__,dict(mapping.gain_points.__globals__,
            DESIGN=DESIGN,qualified=SimpleNamespace(BUILD=p.BUILD)),mapping.gain_points.__name__,mapping.gain_points.__defaults__)
        pins,points=gain(before,single,proposed,pins)
        counts=Counter(x['metric'] for x in points if x['scope']==delta['scope'] or x['scope'].startswith(delta['scope']+'.'))
        require(all(counts[m]==delta['metrics'][m] for m in bitmap.METRICS),'Compiled product delta differs')
        target=binding['targets'][0]
        flags=[mapping.hit(v['metrics']['cond'][p.SCOPE],493) for v in (before,single,proposed)]
        require(flags[0] is False and flags[1]==flags[2],'Exact target zero/union mismatch')
        result=dict(status='SV39_MASKED_FAULT_POSITIVE_RAW735_CANDIDATE_NOT_ADMITTED',
            baseline=735,proposed_tests=736,raw_delta=delta['metrics'],target493_hit=flags[1],
            coverage_admitted=False,new_RTL_signoff=False,official_DVE_report=False,simulations_started=False)
        artifacts={'single-raw-bits.json':single,'combined-bits.json':proposed,'raw-delta.json':delta,
            'gained-compiled-points.json':points,'target-reconciliation.json':dict(target,before=flags[0],
            sample=flags[1],proposed=flags[2]),'status.json':result}
        for name,value in artifacts.items():life.save(output/name,value)
        (output/'combined-inputs.txt').write_text('\n'.join([str(DESIGN),*proposed['tests']])+'\n')
        life.check(pins)
        life.save(output/'candidate-seal.json',dict(input_pins=pins,
            output_pins={str(x):life.digest(x) for x in output.iterdir() if x.is_file()},
            qualification=str(qualification_path),qualification_seal=qualification_seal,
            baseline=str(BASE),baseline_seal=BASE_SEAL,result=result,coverage_admitted=False))
        print(json.dumps(dict(output=str(output),seal=life.digest(output/'candidate-seal.json'),result=result)))
    except Exception as error:
        life.save(output/'failure.json',dict(status='REJECTED_NOT_ADMITTED',reason=str(error)));raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qualification',type=Path,required=True);parser.add_argument('--qualification-seal',required=True)
    parser.add_argument('--output',type=Path,required=True);a=parser.parse_args()
    prepare(a.qualification.absolute(),a.qualification_seal,a.output.absolute())


if __name__=='__main__':main()
