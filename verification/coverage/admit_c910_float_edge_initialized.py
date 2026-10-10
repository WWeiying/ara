"""One qualified initialized float run appended to an explicit latest formal ledger."""
import argparse
import hashlib
import json
from pathlib import Path
import collect_c910_float_edge_initialized777 as case
from admit_stride_metadata768 import dedup

life, require, runner, bitmap, toggle = case.life, case.require, case.runner, case.bitmap, case.toggle
RUN = life.OUT / 'c910-float-edge-initialized-vcs777-agent-20261007-01'
RUN_SEAL = 'a2a75e1bebe45ec2bbd0aeab11aff629ca5b0979fff453048e97ee4c53978444'
COUNTS = dict(line=1892, cond=2023, branch=2155, fsm=92)


def full_union(before, single, original):
    count = len(before['tests'])
    require(count >= 777 and len(set(before['tests'])) == count and
        before['tests'][:777] == original['tests'] and single['tests'] == [str(RUN/'code.vdb')]
        and single['tests'][0] not in before['tests'], 'Exact777 prefix/latest unique candidate')
    after = bitmap.combine(before, single)
    require(after['tests'] == before['tests'] + single['tests'] and
        before['design'] == single['design'] == after['design'], 'Exact latest prefix/design')
    require(set(before['metrics']) == set(single['metrics']) == set(after['metrics']) == set(COUNTS), 'Four metric families')
    for metric, count in COUNTS.items():
        old, add, final = (x['metrics'][metric] for x in (before,single,after))
        require(len(old) == count and set(old) == set(add) == set(final), 'All6162 instance universe')
        for scope,row in old.items():
            b,c = add[scope],final[scope]
            require((row['width'],row['checksum']) == (b['width'],b['checksum']) == (c['width'],c['checksum']), 'Exact shape')
            values = [int(x['bits'],16) for x in (row,b,c)]
            require(min(values)>=0 and max(values).bit_length()<=row['width'] and values[2]==values[0]|values[1], 'Independent6162 mathematical OR')
    return after


def native_gate(n):
    primary, full = n['primary'], n['complete_vector_diff']
    require(primary['operations'] == dict(load_a=48,load_b=48,div=48,store=48)
        and primary['defined_bytes'] == 4608 and primary['skipped_bytes'] == 0
        and len(primary['writers']) == 144 and primary['initialization']['compared_bytes'] == 3072
        and primary['initialization']['unknown_bytes'] == 0
        and len(primary['initialization']['requests']) == 3, 'Original48 operations plus3072 initialized bytes')
    require(full['status']=='PASS' and full['stopped_at_spike_index'] is None and full['first_mismatch'] is None
        and full['vector_destination_requests']==full['prefix_vector_destination_requests']==full['compared_instructions']==147
        and len(full['instructions'])==147 and full['compared_bytes']>=7680
        and all(full[k]==0 for k in ('skipped_unknown_bytes','non_bit_exact_instructions','unobservable_instructions'))
        and all(not full[k] for k in ('incomplete_requests','unretired_requests','trapped_requests'))
        and all(row['status']=='PASS' and row['unknown_write_bytes']==row['skipped_unknown_bytes']==row['mismatch_count']==0
            for row in full['instructions']), 'All-request no-stop zero-unknown generic native comparison')


def evaluate(qualification, qsha, base_dir, bsha):
    q = life.read_bound(qualification,qsha); life.check(q['input_pins'])
    require(q['status']=='C910_INITIALIZED_FLOAT_EDGE_FULL_SCALAR_NATIVE_CSR_RAW777_PASS_NOT_ADMITTED'
        and q['run']==str(RUN) and q['prepared_seal']==RUN_SEAL and q['coverage_admitted'] is False
        and q['EDA_launched'] is False and q['RTL_modified'] is False, 'Exact qualified initialized run')
    native_gate(q['native'])
    pre=runner.preflight(); reference=case.reference_prefix(pre)
    case.common.scalar_exact(q['scalar'],case.common.reference_counts(reference,pre['symbols']))
    require(q['signature']['checks']==1440 and q['signature']['failures']==0 and
        q['signature']['retirements']==36997 and q['signature']['CSR_values']==288
        and q['signature']['required_read_bytes']==11520 and q['signature']['source_destination_guard_bytes']==9216
        and len(q['signature']['per_division_fcsr'])==48, 'Full independent memory/CSR oracle')
    require(q['scalar_memory']==dict(instructions=36997,scalar_memory_accesses=8983,
        compressed_memory_accesses=5119,unmodeled_memory_effects=0), 'Every scalar memory access')
    require(q['lifecycle']['requests']==q['lifecycle']['responses'] and q['lifecycle']['exceptions']==0
        and not q['lifecycle']['rejected_arch_seqs'] and q['lifecycle']['rejected_backend_uops']==0
        and q['lifecycle']['rejected_vrf_activities']==0, 'All protocol/lifecycle checks')
    for phase, row in enumerate(q['signature']['per_division_fcsr']):
        expected=(phase//8%2)*32+case.p.gold(16<<(phase//16),phase%8,phase//8%2)[3]
        require(row['phase']==phase and row['fcsr']==expected, 'Every48 fflags/rm value')
    record=RUN.with_name(RUN.name+'.prepared.json'); manifest=life.read_bound(record,RUN_SEAL)
    require(manifest==runner.prepare(RUN,existing=True) and case.terminal(RUN,manifest)==q['terminal'], 'Exact run/actual zero terminal')
    base=life.read_bound(base_dir/'admission-manifest.json',bsha)
    require(base['coverage_admitted'] is True and base['output']==str(base_dir), 'Explicit formal baseline')
    life.check(base['input_pins']); life.check(base['output_pins'])
    before=life.read_bound(base_dir/'combined-bits.json',base['output_pins'][str(base_dir/'combined-bits.json')])
    ledger_path=base_dir/'combined-inputs.txt'
    require(life.digest(ledger_path)==base['output_pins'][str(ledger_path)], 'Formal ledger seal')
    ledger=ledger_path.read_text().splitlines()
    require(ledger[1:]==before['tests'] and len(ledger)==len(set(ledger))==len(before['tests'])+1, 'Full unique baseline ledger')
    status=life.read_bound(base_dir/'status.json',base['output_pins'][str(base_dir/'status.json')])
    require(status['coverage_admitted'] is True and status['aggregate_passed']==len(before['tests']), 'Formal population status')
    _,original,original_ledger=runner.baseline()
    require(ledger[:778]==original_ledger, 'Sealed777 exact prefix')
    def document(name):
        path=qualification.parent/name
        return life.read_bound(path,q['input_pins'][str(path)])
    inputs=qualification.parent/'single-inputs.txt'
    require(q['input_pins'][str(inputs)]==life.digest(inputs) and
        inputs.read_text().splitlines()==[ledger[0],str(RUN/'code.vdb')], 'One qualified input VDB')
    single=bitmap.collect(inputs)
    require(single==document('single-bits.json') and
        all(q['input_pins'].get(path)==sha for path,sha in single['input_hashes'].items()), 'Exact single native recollection ownership')
    old_after=full_union(original,single,original)
    require(old_after==document('proposed-combined-bits.json') and
        bitmap.delta(original,old_after)==document('raw-delta.json'), 'Qualified original777 union/delta')
    after=full_union(before,single,original); delta=bitmap.delta(before,after)
    cache,pins=case.checked_cache(); scopes=list(cache['instances'])
    old={s:{k:r[k] for k in ('width','checksum','bits')} for s,r in cache['instances'].items()}
    prior=next(Path(path) for path in cache['input_pins'] if path.endswith('/inputs.txt'))
    require(ledger[:742]==prior.read_text().splitlines(), 'Exact741 cached prefix')
    for db in ledger[742:]:
        paths=list((Path(db)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(paths)==1,'One Toggle test per admitted suffix')
        sample,sha=toggle.rows(paths[0],scopes)
        require(base['input_pins'].get(str(paths[0]))==sha,'Historical Toggle baseline ownership')
        pins[str(paths[0])]=sha; old=toggle.union(old,sample)
    folder=RUN/'code.vdb/snps/coverage/db/testdata'/runner.NAME
    meta=case.coverage_identity(folder,RUN,manifest,Path(ledger[0])); pins=life.merge_pins(pins,meta)
    sample,sha=toggle.rows(folder/'tgl.verilog.data.xml',scopes)
    require(q['input_pins'].get(str(folder/'tgl.verilog.data.xml'))==sha,'Qualified Toggle input')
    gained=toggle.gains(old,toggle.union(old,sample)); toggle_count=sum(map(len,gained.values()))
    metric_count=sum(delta['metrics'].values())
    require(toggle_count+metric_count>0,'No positive gain against explicit latest baseline')
    audit=dedup(ledger,runner.ELF_SHA,base['input_pins'])
    require(audit['ledger_members']==len(before['tests']) and not audit['duplicate'] and
        all(base['input_pins'].get(path)==sha for path,sha in audit['pins'].items()), 'Historical ELF/command ownership; no duplicate ELF')
    for extra in (base['input_pins'],base['output_pins'],q['input_pins'],audit['pins']): pins=life.merge_pins(pins,extra)
    fixed={qualification:qsha,base_dir/'admission-manifest.json':bsha,record:RUN_SEAL}
    for module in (case,runner,bitmap,toggle):
        path=Path(module.__file__).resolve(); fixed[path]=life.digest(path)
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_c910_float_edge_initialized.py'),Path(dedup.__code__.co_filename).resolve()): fixed[path]=life.digest(path)
    pins=life.merge_pins(pins,{str(path):sha for path,sha in fixed.items()}); life.check(pins)
    retained={}
    for path,sha in base['output_pins'].items():
        path=Path(path)
        if path.parent==base_dir and path.suffix=='.json' and ('toggle-gain' in path.name or path.name.startswith('retained-')):
            retained[path.name]=life.read_bound(path,sha)
    population=len(after['tests'])
    products=dict(retained,**{'combined-bits.json':after,'single-bits.json':single,'raw-delta.json':delta,
        'float-edge-toggle-gain.json':dict(baseline=len(before['tests']),gained=gained,new_raw_slots=toggle_count,
            official_percentage_claimed=False,prior777_gain_not_recounted=True), 'elf-ledger-dedup.json':audit,
        'evidence-pins.json':pins,'status.json':dict(aggregate_passed=population,coverage_admitted=True,
            baseline=len(before['tests']),exact_previous_prefix=True,full_OR_metric_instances=6162,
            unique_new_vdb=True,duplicate_ELF=False,new_toggle_raw_slots=toggle_count,raw_delta=delta['metrics'],
            all_scalar_native_memory_CSR_lifecycle_verified=True,initialization_bytes=3072,unknown_bytes=0,
            historical_fixed_image_only=True,official_percentage_claimed=False,new_RTL_signoff=False)})
    return products,'\n'.join([ledger[0],*after['tests']])+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('mode',choices=('prepare','verify','admit'))
    parser.add_argument('--qualification',type=Path,required=True); parser.add_argument('--qualification-seal',required=True)
    parser.add_argument('--baseline',type=Path,required=True); parser.add_argument('--baseline-seal',required=True)
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--seal'); parser.add_argument('--parent-authorized',action='store_true')
    args=parser.parse_args(); out=args.output.resolve()
    require((args.mode=='admit')==args.parent_authorized and (args.mode!='prepare')==bool(args.seal),'Explicit admission approval/seal')
    require(out.parent==life.OUT and not out.exists(),'Fresh admission output')
    products,text=evaluate(args.qualification.resolve(),args.qualification_seal,args.baseline.resolve(),args.baseline_seal)
    hashes={str(out/name):hashlib.sha256((json.dumps(value,indent=2)+'\n').encode()).hexdigest() for name,value in products.items()}
    for name in ('combined-inputs.txt','generic-coverage-inputs.txt'): hashes[str(out/name)]=hashlib.sha256(text.encode()).hexdigest()
    proposal=dict(output=str(out),baseline=str(args.baseline.resolve()),baseline_seal=args.baseline_seal,
        qualification=str(args.qualification.resolve()),qualification_seal=args.qualification_seal,
        input_pins=products['evidence-pins.json'],output_pins=hashes,coverage_admitted=False)
    record=out.with_name(out.name+'.prepared.json')
    if args.mode=='prepare': life.save(record,proposal); print('PREPARED_NOT_ADMITTED',life.digest(record),flush=True); return
    require(life.read_bound(record,args.seal)==proposal,'Prepared admission drift')
    if args.mode=='verify': print('VERIFY_PASS_NO_ADMISSION',flush=True); return
    out.mkdir()
    for name,value in products.items(): life.save(out/name,value)
    for name in ('combined-inputs.txt','generic-coverage-inputs.txt'):
        with (out/name).open('x') as stream: stream.write(text)
    life.check(proposal['input_pins']); life.check(hashes)
    life.save(out/'admission-manifest.json',dict(proposal,coverage_admitted=True,prepared=str(record),prepared_seal=args.seal,
        authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'))
    print('ADMITTED',life.digest(out/'admission-manifest.json'),flush=True)


if __name__=='__main__': main()
