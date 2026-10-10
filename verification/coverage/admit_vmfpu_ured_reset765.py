"""Exact formal764 prefix plus one independently qualified reset case; offline only."""
import argparse
from pathlib import Path
import coverage_bitmap_delta as bitmap
import postprocess_vmfpu_ured_reset763 as post

life,require=post.life,post.require
BASE=life.OUT/'qbs-payload-phase-offline-admitted-764-agent-20261007-01'
BASE_SHA='167f82e2a614e34e7dd8606bdb9211370cb573ebc0ad414baa99f7da355398f1'
QUAL=post.OUT
QUAL_SHA='a58b07f93515bc3809cdda94b8201ab2e4a439af3a1c0246327d82f9bc618b8a'
RUN=post.old.RUN
OUT=life.OUT/'vmfpu-ured-reset-offline-admitted-765-agent-20261007-01'
SCHEMA='EXACT764_PLUS_ONE_URED_RESET765_V1'


def contract(q,scalar,vector,owners,frontend):
    expected=dict(status='FINITE_URED_FOUR_INTRA_EXTERNAL_RESET_ARCHITECTURE_PASS_NOT_ADMITTED',
        baseline=763,checks=680,full_vrf_bytes=4096,CSR_flags0=True,epoch_count=2,
        source_guards_checked=True,actual_reset_targets=4,epoch0_seed_bytes=4224,coverage_admitted=False)
    for key,value in expected.items():
        require(type(q.get(key)) is type(value) and q[key]==value,'Qualification field differs: '+key)
    require(q['plan_seal']==post.SEAL and q['backend']==[
        dict(allocations=35,completions=33,aborted=2,write_events=528,cancelled_arch_sequences=[37,38]),
        dict(allocations=68,completions=68,aborted=0,write_events=785,cancelled_arch_sequences=[])],
        'Exact two-epoch cancellation/completion differs')
    require([(r['vid'],r['arch_seq'],r['insn'],r['vd'],r['vl'],r['eew']) for r in owners]==
        [(0,37,0x5e02c457,8,128,3),(1,38,0x06809157,2,128,3)],'Cancelled native identities differ')
    pre=life.read_bound(post.old.PRE/'preflight.json',post.old.life.read_bound(post.old.PLAN,post.SEAL)['preseal'])
    require([r['pc'] for r in owners]==[pre['symbols']['ured_ones'],pre['symbols']['ured_reduce']],
            'Real seed/reduction PC differs')
    post.old.shared.scalar_exact(scalar,pre['counts'])
    require(vector['status']=='PASS' and vector['compared_instructions']==36 and vector['compared_bytes']==6280 and
        all(vector[k]==0 for k in ('skipped_unknown_bytes','non_bit_exact_instructions','unobservable_instructions')) and
        not vector['incomplete_requests'] and not vector['unretired_requests'] and vector['first_mismatch'] is None and
        all(r['unknown_write_bytes']==r['skipped_unknown_bytes']==r['mismatch_count']==0 for r in vector['instructions']),
        'Full independent vector comparison differs')
    require(frontend==q['frontend']==[
        dict(counts=dict(requests=39,responses=39,aborted=0),cancelled={}),
        dict(counts=dict(requests=77,responses=77,aborted=0),cancelled={})],'Frontend lifecycle differs')


def merge(before,single,prefix):
    require(len(before['tests'])==len(set(before['tests']))==764 and len(prefix['tests'])==763 and
        before['tests'][:763]==prefix['tests'] and single['tests']==[str(RUN/'code.vdb')] and
        str(RUN/'code.vdb') not in before['tests'],'Exact764 prefix/763 membership/unique candidate differs')
    combined=bitmap.combine(before,single);count=0
    require(combined['tests']==before['tests']+single['tests'] and len(set(combined['tests']))==765,
            'Exact765 append differs')
    for metric,rows in before['metrics'].items():
        for scope,row in rows.items():
            add=single['metrics'][metric][scope];new=combined['metrics'][metric][scope]
            require(type(row['width']) is int and row['width']>=0 and
                max(int(row['bits'],16).bit_length(),int(add['bits'],16).bit_length())<=row['width'] and
                int(new['bits'],16)==int(row['bits'],16)|int(add['bits'],16),'Independent all-instance OR differs')
            count+=1
    require(count==6162 and set(before['metrics'])==set(bitmap.METRICS),'Frozen four-metric shape differs')
    delta=post.old.audit.coverage.all_delta(before,combined)
    for path in post.old.states():
        scope=path.rsplit('.',1)[0];a=before['metrics']['fsm'][scope];b=combined['metrics']['fsm'][scope]
        require(a['width']==37 and a['checksum']=='3873291691' and
            ((int(b['bits'],16)&~int(a['bits'],16))&(1<<17))!=0,'Exact INTRA->NO reset arc not freshly hit')
    require(delta['metrics']==dict(line=0,cond=0,branch=0,fsm=4),'Fresh764 raw gain differs')
    return combined,delta


def evaluate():
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    qual=life.read_bound(QUAL/'qualification.json',QUAL_SHA)
    pins=life.merge_pins(base['input_pins'],base['output_pins'])
    pins=life.merge_pins(pins,qual['pins'])
    pins=life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SHA,str(QUAL/'qualification.json'):QUAL_SHA})
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_vmfpu_ured_reset765.py'),
              Path(bitmap.__file__).resolve()):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins)
    def read(p):return life.read_bound(p,pins[str(p)])
    status=read(BASE/'status.json')
    require(status['coverage_admitted'] is True and status['aggregate_passed']==764 and
        status['status']=='PASS_RAW_UNION_HISTORICAL_ONLY','Formal764 not admitted')
    before=read(BASE/'combined-bits.json');single=read(QUAL/'single-bits.json')
    prefix=read(post.old.BASE/'combined-bits.json')
    require((BASE/'combined-inputs.txt').read_text().splitlines()==[str(life.IMAGE)+'.vdb',*before['tests']],
            'Exact764 ordered native inputs differ')
    contract(qual,read(QUAL/'recovery-scalar.json'),read(QUAL/'recovery-vector.json'),
             read(QUAL/'cancelled-owner-bindings.json'),read(QUAL/'frontend-audit.json'))
    require(life.merge_pins(pins,single['input_hashes'])==pins,'Singleton raw pins missing')
    design=Path(str(life.IMAGE)+'.vdb')/'snps/coverage/db'
    require(all(pins.get(str(design/p))==sha for p,sha in single['design'].items()),'Frozen design identity differs')
    paths={}
    for metric in (*bitmap.METRICS,'tgl'):
        files=list((RUN/'code.vdb/snps/coverage/db/testdata').glob('*/'+metric+'.verilog.data.xml'))
        require(len(files)==1 and pins.get(str(files[0]))==life.digest(files[0]),'Missing/drift native '+metric)
        paths[metric]=files[0]
        if metric!='tgl':require(bitmap.read_metric(files[0])==single['metrics'][metric],'Native singleton content differs')
    reference=list((Path(before['tests'][0])/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(reference)==1 and pins.get(str(reference[0]))==life.digest(reference[0]),'Inherited Toggle pin differs')
    native=post.old.audit.coverage.native
    require(native.toggle_shape(paths['tgl'])==native.toggle_shape(reference[0]),
            'Full native Toggle binary/packed interval shape differs')
    combined,delta=merge(before,single,prefix)
    life.check(pins)
    return pins,dict(**{'single-bits.json':single,'combined-bits.json':combined,'raw-delta.json':delta,
        'raw-new-coordinates.json':delta['instances']},**{'status.json':dict(
        status='PASS_RAW_UNION_HISTORICAL_ONLY',aggregate_passed=765,baseline=764,new_passed=1,
        coverage_admitted=True,exact764_prefix=True,exact763_membership_included=True,full_OR_instances=6162,
        raw_delta=delta['metrics'],native_five_metrics_compatible=True,full_scalar_ISA_verified=True,
        full_vector_verified=True,full_vrf_bytes=4096,checks=680,fflags=0,epoch0_seed_bytes=4224,
        cancelled_backend_arch_sequences=[37,38],reset_cycles=4,forced_internal_state=False,
        historical_fixed_image_only=True,new_RTL_signoff=False,rtl_changed=False,simulation_rerun=False,
        DVE_launched=False,waiver_applied=False,official_percentage_claimed=False)})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent-authorized',action='store_true')
    p.add_argument('--verify-seal');args=p.parse_args()
    require(bool(args.parent_authorized)!=bool(args.verify_seal),'One explicit mode required')
    if args.parent_authorized:require(not OUT.exists(),'Preserve all sealed outputs')
    pins,values=evaluate()
    ledger='\n'.join([str(life.IMAGE)+'.vdb',*values['combined-bits.json']['tests']])+'\n'
    if args.verify_seal:
        manifest=life.read_bound(OUT/'admission-manifest.json',args.verify_seal)
        require(manifest['schema']==SCHEMA and manifest['baseline_seal']==BASE_SHA and
            manifest['qualification_seal']==QUAL_SHA and manifest['input_pins']==pins and
            manifest['authorization_source']=='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL' and
            set(manifest['output_pins'])=={str(OUT/n) for n in (*values,'combined-inputs.txt')},'Manifest identity differs')
        life.check(manifest['output_pins'])
        for name,value in values.items():require(life.read_bound(OUT/name,manifest['output_pins'][str(OUT/name)])==value,
                                               'Sealed replay differs')
        require((OUT/'combined-inputs.txt').read_text()==ledger,'Native full ledger differs')
        print('FORMAL765_VERIFY_PASS '+args.verify_seal,flush=True);return
    OUT.mkdir()
    for name,value in values.items():life.save(OUT/name,value)
    with (OUT/'combined-inputs.txt').open('x') as stream:stream.write(ledger)
    life.save(OUT/'admission-manifest.json',dict(schema=SCHEMA,baseline=str(BASE),baseline_seal=BASE_SHA,
        qualification=str(QUAL/'qualification.json'),qualification_seal=QUAL_SHA,output=str(OUT),input_pins=pins,
        output_pins={str(p):life.digest(p) for p in OUT.iterdir() if p.is_file()},
        authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL',coverage_admitted=True))
    print('FORMAL765_ADMITTED '+life.digest(OUT/'admission-manifest.json')+' '+str(values['status.json']['raw_delta']),flush=True)


if __name__=='__main__':main()
