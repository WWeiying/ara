"""One offline candidate bitmap, exact725 prefix; explicit parent gates, no EDA."""
import argparse
from collections import Counter
import json
from pathlib import Path

import qualify_vnclipu_maintenance_successor as qualified
import collect_operand_index_snapshot_raw_724 as raw

old, life, require, bitmap = qualified.old, qualified.life, qualified.require, raw.bitmap
BASE, BASE_SEAL = old.p.BASE, old.p.BASE_SEAL
QUAL = life.OUT/'vnclipu-maintenance-qualified-parent-20261006-01'
QUAL_SEAL = 'b8f42476e14ac0ffeaa5519c92a9ceb344ab2a6b2e63fdaf2906e6a4657cc5ce'
DESIGN = Path(str(life.IMAGE)+'.vdb')
VDB = old.RUN/'code.vdb'
TARGETS = {('line',557), ('line',564), ('cond',265), ('branch',921), ('branch',925)}
AUTH = 'PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'
PRODUCTS = {'single-raw-bits.json','combined-bits.json','combined-inputs.txt','raw-delta.json',
            'target-reconciliation725.json','gained-compiled-points.json','status.json','evidence-pins.json'}


def eligibility(q, proof, scalar, vector, pre):
    require(q['status']=='VNCLIPU_FULL_DUT_MAINTENANCE_QUALIFIED_NOT_ADMITTED' and
            q['baseline']==725 and q['coverage_admitted'] is False and q['rtl_changed'] is False and
            q['simulations_started'] is False and q['raw_coverage_increment_not_collected'] is True and
            q['original_failure_preserved'] is True and q['generic_skipped_counter']==128 and
            q['proven_known_source_maintenance_bytes']==128 and q['genuinely_unknown_bytes']==0,
            'Incomplete real successor qualification')
    expected = dict(arch_seq=124, pc='0x80002754', instruction='0xba804857',
        known_source_maintenance_bytes=128, destination_prestate_maintenance_bytes=128,
        destination_poststate_bytes=128, legal_result_bytes=4, source_register=8, destination_register=16,
        genuinely_unknown_bytes=0, independent_expected_byte_oracle=True, generic_skipped_counter=128,
        generic_counter_is_not_true_unknown=True, other_skipped_bytes=0, coverage_admitted=False)
    require(proof==expected, 'Different/noncomplete sealed maintenance proof')
    old.common.scalar_exact(scalar, pre['reference_counts'])
    require(vector['status']=='PASS' and vector['compared_instructions']==33 and
            vector['compared_bytes']==4224 and vector['skipped_unknown_bytes']==128 and
            vector['non_bit_exact_instructions']==vector['unobservable_instructions']==0 and
            vector['first_mismatch'] is None and vector['trapped_requests']==[81] and
            vector['incomplete_requests']==vector['unretired_requests']==[], 'Incomplete sealed vector result')
    records = vector['instructions']
    require(len(records)==33 and all(r['status']=='PASS' and r['compared_bytes']==128 and
            r['unknown_write_bytes']==r['mismatch_count']==0 and r['first_mismatch'] is None and
            r['skipped_unknown_bytes']==(128 if i==32 else 0) for i,r in enumerate(records)) and
            records[-1]['arch_seq']==124 and int(records[-1]['pc'],16)==qualified.PC and
            int(records[-1]['instruction'],16)==qualified.WORD,
            'Unproved skip/unknown/mismatch in sealed vector result')


def population(before, single):
    raw.validate_bitmap(before); raw.validate_bitmap(single)
    require(len(before['tests'])==len(set(before['tests']))==725 and
            single['tests']==[str(VDB)] and str(VDB) not in before['tests'], 'Wrong/duplicate population')
    life.merge_pins(before['input_hashes'], single['input_hashes'])
    proposed = bitmap.combine(before, single)
    require(proposed['tests']==[*before['tests'],str(VDB)] and len(set(proposed['tests']))==726,
            'Broken exact725 prefix/one candidate')
    return proposed, bitmap.delta(before, proposed)


def reconcile(before, single, proposed, targets):
    require(len(targets)==5 and {(t['metric'],t['raw_index']) for t in targets}==TARGETS and
            all(t['scope']==old.p.SCOPE for t in targets), 'Not exact2line/1cond/2branch targets')
    result = []
    for t in targets:
        metric, scope, index = t['metric'], t['scope'], t['raw_index']
        values = [v['metrics'][metric][scope] for v in (before,single,proposed)]
        require(all((r['width'],r['checksum'])==(t['width'],t['checksum']) for r in values), 'Target shape drift')
        flags = [raw.hit(r,index) for r in values]
        require(flags[0] is False and flags[2]==flags[1], 'Target zero/union mismatch')
        result.append(dict(t, baseline725_hit=False, sample_hit=flags[1], proposed_hit=flags[2],
                           native_GUI_ID_qualification=False))
    return result


def positive(delta, points):
    counts = delta['metrics']
    require(set(counts)==set(bitmap.METRICS) and all(type(v) is int and v>=0 for v in counts.values()) and
            sum(counts.values())>0, 'Measured positive raw gain required')
    coordinates = [(r['scope'],r['metric'],r['point']['raw_index']) for r in points]
    require(len(coordinates)==len(set(coordinates)) and all(r['baseline_hit'] is False and
            r['sample_hit'] is True and r['proposed_hit'] is True and r['source_sha256'] and
            r['native_GUI_ID_qualification'] is False for r in points), 'Unproved/duplicate compiled gain')
    measured = Counter(r['metric'] for r in points if r['scope']==delta['scope'] or
                       r['scope'].startswith(delta['scope']+'.'))
    require(all(measured[m]==counts[m] for m in bitmap.METRICS), 'Compiled gained identity/count mismatch')


def context(qualification_seal):
    require(qualification_seal==QUAL_SEAL, 'Exact parent verified qualification seal required')
    q = life.read_bound(QUAL/'qualification.json', qualification_seal)
    require(not (QUAL/'failure.json').exists(), 'Failed qualification is not eligible')
    pins = life.merge_pins(q['pins'], {str(QUAL/'qualification.json'):qualification_seal})
    def read(path):
        require(str(path) in pins, 'Missing evidence pin: '+str(path))
        return life.read_bound(path,pins[str(path)])
    pre = read(old.p.PRE/'preflight-manifest.json')
    require(pins[str(old.p.PRE/'preflight-manifest.json')]==old.PRE_SEAL, 'Foreign preflight')
    eligibility(q, read(QUAL/'maintenance-proof.json'), read(QUAL/'scalar-comparison.json'),
                read(QUAL/'vector-comparison-unmodified.json'), pre)
    manifest = life.read_bound(BASE/'admission-manifest.json', BASE_SEAL)
    require(manifest['output']==str(BASE) and set(manifest['output_pins']) and
            all(Path(p).parent==BASE for p in manifest['output_pins']), 'Foreign725 products')
    pins = life.merge_pins(pins, manifest['output_pins'])
    pins = life.merge_pins(pins, {str(BASE/'admission-manifest.json'):BASE_SEAL})
    inherited = read(BASE/'evidence-pins.json'); pins = life.merge_pins(pins,inherited)
    state, before = read(BASE/'status.json'), read(BASE/'combined-bits.json')
    require(state['status']=='PASS_RAW_UNION_HISTORICAL_ONLY' and state['aggregate_passed']==725 and
            state['coverage_admitted'] is True and len(before['tests'])==len(set(before['tests']))==725 and
            (BASE/'combined-inputs.txt').read_text().splitlines()==[str(DESIGN),*before['tests']] and
            all(pins.get(p)==h for p,h in before['input_hashes'].items()), 'Not complete pinned formal725')
    elf_hash = pre['pins'][pre['input_elf']]
    require(not any(h==elf_hash for h in inherited.values()) and str(VDB) not in before['tests'],
            'Duplicate historical ELF/VDB')
    old.binding(pre, read(old.PREPARED), read(old.REVIEW))
    old.terminal(read(old.RUN/'simulation-status.json'), read(old.RUN/'manifest.json'),read(old.PREPARED))
    for relative, h in before['design'].items():
        pins = life.merge_pins(pins, {str(DESIGN/'snps/coverage/db'/relative):h})
    files = sorted(p for p in VDB.rglob('*') if p.is_file())
    require(files and not VDB.is_symlink() and VDB.resolve()==VDB and
            not any(p.is_symlink() for p in VDB.rglob('*')), 'Missing/aliased candidate VDB')
    pins = life.merge_pins(pins, {str(p):life.digest(p) for p in files})
    dependencies = [Path(__file__).resolve(), Path(__file__).with_name('test_prepare_vnclipu_admission726.py'),
        Path(raw.__file__).resolve(), Path(bitmap.__file__).resolve(),Path(raw.shape.__file__).resolve(),
        life.ROOT/'verification/coverage/inventory_operand_debug.py']
    pins = life.merge_pins(pins, {str(p):life.digest(p) for p in dependencies})
    life.check(pins)
    return pins, before, pre, [str(p) for p in files]


def evaluate(before, single, pre, pins):
    expected = {str(VDB/'snps/coverage/db/testdata'/old.p.NAME/(m+'.verilog.data.xml')) for m in bitmap.METRICS}
    require(set(single['input_hashes'])==expected and all(pins.get(p)==h for p,h in single['input_hashes'].items()),
            'Foreign/incomplete single metric inputs')
    proposed, delta = population(before,single)
    targets = reconcile(before,single,proposed,pre['targets'])
    pins, points = raw.gain_points(before,single,proposed,pins)
    positive(delta,points)
    return pins, {'single-raw-bits.json':single,'combined-bits.json':proposed,'raw-delta.json':delta,
        'target-reconciliation725.json':targets,'gained-compiled-points.json':points,
        'status.json':dict(status='VNCLIPU_RAW726_PREPARED_NOT_ADMITTED', baseline=725,aggregate_passed=725,
            proposed_tests=726,new_admitted=0,coverage_admitted=False,exact725_prefix=True,
            raw_delta=delta['metrics'],targets_total=5,targets_hit=sum(t['sample_hit'] for t in targets),
            targets_expected_only=True,all_five_targets_required=False,full_DUT_qualified=True,
            proven_known_source_maintenance_bytes=128,raw_union_historical_only=True,
            inherited725_recollected=False,rtl_changed=False,simulations_started=False)}


def fresh(path):
    require(path.parent==life.OUT and path.resolve()==path and not path.exists(), 'Fresh direct output required')


def prepare(output, formal_output, qualification_seal, parent_verified):
    require(parent_verified is True, 'Parent real qualification verification required before raw collect')
    fresh(output); fresh(formal_output); require(output!=formal_output, 'Prepare is not admit')
    pins,before,pre,members = context(qualification_seal)
    output.mkdir()
    try:
        with (output/'single-inputs.txt').open('x') as f: f.write(str(DESIGN)+'\n'+str(VDB)+'\n')
        single = bitmap.collect(output/'single-inputs.txt')
        pins, values = evaluate(before,single,pre,pins)
        for n,v in values.items(): life.save(output/n,v)
        with (output/'combined-inputs.txt').open('x') as f:
            f.write('\n'.join([str(DESIGN),*values['combined-bits.json']['tests']])+'\n')
        life.save(output/'evidence-pins.json',pins); life.check(pins)
        products = PRODUCTS|{'single-inputs.txt'}
        life.save(output/'prepared-seal.json',dict(schema='VNCLIPU_HISTORICAL726_PREPARE_V1',
            output=str(output),formal_output=str(formal_output),baseline_seal=BASE_SEAL,
            qualification_seal=qualification_seal,input_pins=pins,
            output_pins={str(output/n):life.digest(output/n) for n in products},vdb_members=members,
            provenance='PARENT_AGENT_INDEPENDENT_QUALIFICATION_VERIFICATION',coverage_admitted=False))
        return life.digest(output/'prepared-seal.json')
    except Exception as error:
        life.save(output/'failure.json',dict(status='VNCLIPU_RAW726_REJECTED_NOT_ADMITTED',
            reason=type(error).__name__+': '+str(error),coverage_admitted=False)); raise


def check(output, seal):
    receipt = life.read_bound(output/'prepared-seal.json',seal)
    require(receipt['schema']=='VNCLIPU_HISTORICAL726_PREPARE_V1' and receipt['output']==str(output) and
            receipt['baseline_seal']==BASE_SEAL and receipt['coverage_admitted'] is False and
            not (output/'failure.json').exists() and
            set(receipt['output_pins'])=={str(output/n) for n in PRODUCTS|{'single-inputs.txt'}}, 'Prepared drift/failure')
    life.check(receipt['input_pins']); life.check(receipt['output_pins'])
    pins,before,pre,members = context(receipt['qualification_seal'])
    require(members==receipt['vdb_members'], 'Candidate VDB member drift')
    single = life.read_bound(output/'single-raw-bits.json',receipt['output_pins'][str(output/'single-raw-bits.json')])
    _,values = evaluate(before,single,pre,pins)
    for n,v in values.items(): require(json.loads((output/n).read_bytes())==v, 'Cached proposal mismatch: '+n)
    require(json.loads((output/'evidence-pins.json').read_bytes())==receipt['input_pins'] and
            (output/'single-inputs.txt').read_text().splitlines()==[str(DESIGN),str(VDB)] and
            (output/'combined-inputs.txt').read_text().splitlines()==[str(DESIGN),*values['combined-bits.json']['tests']],
            'Pin ledger/prefix drift')
    return receipt


def admit(prepared, seal, output, authorization):
    require(authorization==AUTH, 'Separate parent admission authorization required')
    receipt = check(prepared,seal); fresh(output)
    require(str(output)==receipt['formal_output'], 'Different formal destination')
    pins = life.merge_pins(receipt['input_pins'],receipt['output_pins'])
    pins = life.merge_pins(pins,{str(prepared/'prepared-seal.json'):seal}); life.check(pins)
    output.mkdir()
    for n in PRODUCTS-{'status.json','evidence-pins.json'}:
        with (output/n).open('xb') as f: f.write((prepared/n).read_bytes())
    state=json.loads((prepared/'status.json').read_bytes())
    life.save(output/'status.json',dict(state,status='PASS_RAW_UNION_HISTORICAL_ONLY',aggregate_passed=726,
        new_passed=1,new_admitted=1,coverage_admitted=True))
    life.save(output/'evidence-pins.json',pins); life.check(pins)
    life.save(output/'admission-manifest.json',dict(schema='VNCLIPU_HISTORICAL726_ADMISSION_V1',output=str(output),
        baseline=str(BASE),baseline_seal=BASE_SEAL,prepared=str(prepared),prepared_seal=seal,
        qualification=str(QUAL),qualification_seal=receipt['qualification_seal'],authorization=authorization,
        output_pins={str(output/n):life.digest(output/n) for n in PRODUCTS}))
    return life.digest(output/'admission-manifest.json')


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('mode',choices=('prepare','verify','admit'))
    for n in ('output','formal-output','prepared'): p.add_argument('--'+n,type=Path)
    for n in ('qualification-seal','seal','authorization'): p.add_argument('--'+n)
    p.add_argument('--parent-qualified',action='store_true'); a=p.parse_args()
    if a.mode=='prepare':
        require(a.output and a.formal_output and a.qualification_seal and a.parent_qualified and
                not(a.prepared or a.seal or a.authorization), 'Prepare args/parent qualification required')
        print(prepare(a.output.absolute(),a.formal_output.absolute(),a.qualification_seal,a.parent_qualified))
    elif a.mode=='verify':
        require(a.prepared and a.seal and not(a.output or a.formal_output or a.qualification_seal or
                a.authorization or a.parent_qualified), 'Verify args')
        check(a.prepared.absolute(),a.seal); print('VERIFY_PASS_EXACT726_NOT_ADMITTED')
    else:
        require(a.prepared and a.seal and a.output and a.authorization and not(a.formal_output or
                a.qualification_seal or a.parent_qualified), 'Admit args')
        print(admit(a.prepared.absolute(),a.seal,a.output.absolute(),a.authorization))


if __name__=='__main__': main()
