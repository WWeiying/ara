"""One sealed FENCE.T scalar case only: explicit prepare/admit/verify, no EDA."""
import argparse
import hashlib
import json
from pathlib import Path

import prepare_fence_t_u_padding_gain_727 as candidate

old,require,OUT=candidate.old,candidate.require,candidate.OUT
CANDIDATE=OUT/'fence-t-u-padding-gain-candidate-agent-727-20261006-01'
CANDIDATE_SHA='0007ddb0edc692199285582601982b516161e30ba90f5d38777df51460663508'
HELPER_SHA='a2f15d7fdf75f9f74d23a81ffe45b4c7673ca42d81025d4ec5068f028ebfb574'
EXPECTED_DELTA=dict(line=7,cond=11,branch=8,fsm=0)
SCHEMA='FENCE_PADDING_HISTORICAL728_SCOPED_SCALAR_ADMISSION_V1'


def serialized(value):return (json.dumps(value,indent=2)+'\n').encode()


def identity(base_seal,post_seal,candidate_seal):
    require((base_seal,post_seal,candidate_seal)==
            (candidate.BASE_SHA,candidate.POST_SHA,CANDIDATE_SHA),'Only reviewed exact727/FENCE post/candidate allowed')


def replay_post(post,plan):
    tool=candidate.post_tool
    run=candidate.RUN;build=OUT/'fence-t-u-padding-build-parent-727-20261006-01'
    console=(run/'console.log').read_text();vcs=(run/'run.vcs.log').read_text()
    replay=tool.policy.evaluate(console,(run/'commit_trace.csv').read_text(),
            json.loads((build/'elf_metadata.json').read_bytes())[0],(build/'input.elf').read_bytes(),
            plan['proof']['sites'],vcs)
    # JSON evidence stores trap-offset dictionary keys as strings, not Python ints.
    replay=json.loads(serialized(replay))
    require(all(post.get(k)==v for k,v in replay.items()),'Complete scoped software/retirement replay differs')
    first,second=tool.terminal_log(console,True),tool.terminal_log(vcs,False)
    require(post['terminal_log_evidence']==dict(console=first,vcs_log=second),'Pinned log completion replay differs')
    witness,pins=tool.vdb_witness(run,plan)
    require(witness==post['VDB_witness'] and all(post['output_pins'].get(p)==h for p,h in pins.items()),
            'Complete native VDB witness replay differs')


def evaluate(base_seal,post_seal,candidate_seal):
    identity(base_seal,post_seal,candidate_seal)
    require(old.sha(Path(candidate.__file__).resolve())==HELPER_SHA,'Frozen candidate helper drift')
    candidate.verify(CANDIDATE,CANDIDATE_SHA)
    record=json.loads((CANDIDATE/'candidate.json').read_bytes())
    require(record['raw_delta']==EXPECTED_DELTA and record['gained_positions']==26 and
            record['exact727_prefix'] is True and record['proposed_population']==728 and
            record['full_OR_instances']==6162,'Exact reviewed gain/population differs')
    pins=json.loads((CANDIDATE/'evidence-pins.json').read_bytes())
    candidate.merge(pins,record['output_pins'])
    candidate.merge(pins,{str(CANDIDATE/'candidate.json'):CANDIDATE_SHA})
    def bound(path,digest=None):
        path=Path(path).absolute()
        if digest is None:
            require(str(path) in pins,'Unbound source: '+str(path));digest=pins[str(path)]
        require(old.sha(path)==digest,'Evidence seal differs: '+str(path))
        candidate.merge(pins,{str(path):digest});return json.loads(path.read_bytes())
    post=bound(candidate.POST,post_seal);candidate.post_contract(post)
    candidate.merge(pins,post['frozen_input_pins']);candidate.merge(pins,post['output_pins'])
    candidate.merge(pins,post['collector_pins'])
    manifest=bound(candidate.BASE/'admission-manifest.json',base_seal)
    candidate.merge(pins,manifest['output_pins'])
    before=bound(candidate.BASE/'combined-bits.json')
    single=bound(CANDIDATE/'single-bits.json')
    combined,delta,changes=candidate.validate_population(before,single)
    require(delta['metrics']==EXPECTED_DELTA and len(changes)==26 and
            combined==bound(CANDIDATE/'combined-bits.json') and delta==bound(CANDIDATE/'raw-delta.json'),
            'Full6162 OR/gain differs')
    plan=bound(old.PLAN,old.PLAN_SHA)
    require(post['frozen_input_pins']==plan['pins'],'Not exact151 pinned inputs')
    replay_post(post,plan)
    gained=bound(CANDIDATE/'gained-compiled-points.json');targets=bound(CANDIDATE/'target-hits.json')
    require(len(targets)==16 and sum(t['role']=='primary' for t in targets)==14 and
            all(t['before_hit'] is False and t['single_hit'] is True and t['after_hit'] is True for t in targets),
            'Exact14 primary +2 witness facts differ')
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_fence_t_u_padding_728.py')):
        candidate.merge(pins,{str(path):old.sha(path)})
    candidate.check(pins)
    status=dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',baseline=727,aggregate_passed=728,new_passed=1,
                coverage_admitted=True,exact727_prefix=True,full_OR_instances=6162,
                raw_delta=EXPECTED_DELTA,gained_compiled_points=26,primary_targets_hit=14,witnesses_hit=2,
                case_specific_scalar_qualifier=True,qualification_scope='699 software checks and focused ELF/RVFI retirement/trap/capture/CSR parity; this exact FENCE.T case only',
                legacy_checks=458,extra_checks=241,retired_records=18853,capture_stores=195,trap_stores=5,
                native_retired_CSR_CEIL=1011,UVM_errors=2,UVM_clean=False,
                expected_UVM_policy_errors=['CVXIF/NO_TRAFFIC','VID/NO_TRAFFIC'],
                UVM_error_records_preserved=True,generic_UVM_override=False,require_contract_promoted=False,
                terminal_source=candidate.post_tool.MODE,OS_returncode_unknown=True,OS_returncode=None,
                wall_elapsed_seconds=None,OS_terminal_receipt_verified=False,
                full_ISA_reference_verified=False,full_scalar_isa_verified=False,spike_custom_isa_pass=False,
                cyclequalified=False,exact_cycle_proof=False,native_counter_observer_verified=False,
                historical_fixed_image_only=True,official_DVE_report=False,
                official_denominator_verified=False,application_approval=False,
                rtl_changed=False,simulations_started=False,qualification_seal=post_seal,candidate_seal=candidate_seal)
    products={'combined-bits.json':combined,'single-bits.json':single,'raw-delta.json':delta,
              'gained-compiled-points.json':gained,'target-hits.json':targets,'scoped-runtime-audit.json':post,
              'evidence-pins.json':pins,'status.json':status}
    text='\n'.join([str(candidate.DESIGN),*combined['tests']])+'\n'
    return products,text


def fingerprints(output,products,text):
    hashes={str(output/name):hashlib.sha256(serialized(value)).hexdigest() for name,value in products.items()}
    hashes[str(output/'combined-inputs.txt')]=hashlib.sha256(text.encode()).hexdigest()
    return hashes


def approval_gate(prepared,seal,proposal):
    require(seal is not None and old.sha(prepared)==seal,'External reviewed prepared seal required')
    require(json.loads(prepared.read_bytes())==proposal,'Prepared reviewed proposal differs')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','admit','verify'))
    parser.add_argument('--base-seal',required=True);parser.add_argument('--post-seal',required=True)
    parser.add_argument('--candidate-seal',required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seal');args=parser.parse_args(argv)
    identity(args.base_seal,args.post_seal,args.candidate_seal)
    output=args.output.absolute();prepared=output.with_name(output.name+'.prepared.json')
    require(output.parent==OUT and output.resolve()==output,'Direct independent output required')
    require((args.mode!='prepare')==bool(args.seal),'Admit/verify require external seal; prepare forbids it')
    if args.mode=='verify':
        require(old.sha(output/'admission-manifest.json')==args.seal,'Formal admission seal differs')
        manifest=json.loads((output/'admission-manifest.json').read_bytes())
        require(manifest['schema']==SCHEMA and manifest['output']==str(output) and
                (manifest['baseline_seal'],manifest['qualification_seal'],manifest['candidate_seal'])==
                (args.base_seal,args.post_seal,args.candidate_seal),'Formal admission identity differs')
        candidate.check(manifest['output_pins'])
    else:
        require(not output.exists(),'Fresh formal output required')
        if args.mode=='prepare':require(not prepared.exists(),'Fresh prepared sidecar required')
    products,text=evaluate(args.base_seal,args.post_seal,args.candidate_seal)
    hashes=fingerprints(output,products,text)
    proposal=dict(schema='FENCE_PADDING_HISTORICAL728_SCOPED_PREPARED_V1',output=str(output),
                  baseline=str(candidate.BASE),baseline_seal=args.base_seal,qualification=str(candidate.POST),
                  qualification_seal=args.post_seal,candidate=str(CANDIDATE),candidate_seal=args.candidate_seal,
                  input_pins=products['evidence-pins.json'],output_pins=hashes,raw_delta=EXPECTED_DELTA,
                  case_specific_scalar_qualifier=True,UVM_clean=False,generic_UVM_override=False,
                  OS_returncode_unknown=True,full_ISA_reference_verified=False,cyclequalified=False)
    if args.mode=='verify':
        require(hashes==manifest['output_pins'],'Formal outputs differ from exact replay')
        print('FENCE_PADDING_HISTORICAL728_SCOPED_OFFLINE_REVERIFIED '+args.seal);return
    if args.mode=='prepare':
        with prepared.open('xb') as stream:stream.write(serialized(proposal))
        print(json.dumps(dict(prepared=str(prepared),seal=old.sha(prepared))));return
    approval_gate(prepared,args.seal,proposal)
    require(not output.exists(),'Output appeared during replay');output.mkdir()
    for name,value in products.items():
        with (output/name).open('xb') as stream:stream.write(serialized(value))
    with (output/'combined-inputs.txt').open('x') as stream:stream.write(text)
    candidate.check(products['evidence-pins.json']);candidate.check(hashes)
    manifest=dict(schema=SCHEMA,output=str(output),baseline=str(candidate.BASE),baseline_seal=args.base_seal,
                  qualification=str(candidate.POST),qualification_seal=args.post_seal,candidate=str(CANDIDATE),
                  candidate_seal=args.candidate_seal,prepared=str(prepared),prepared_seal=args.seal,output_pins=hashes)
    with (output/'admission-manifest.json').open('xb') as stream:stream.write(serialized(manifest))
    print(json.dumps(dict(output=str(output),seal=old.sha(output/'admission-manifest.json'))))


if __name__=='__main__':main()
