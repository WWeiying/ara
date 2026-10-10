"""Fresh historical723: prepare complete actual R1 replay, then separately authorized sealed formal commit."""
import argparse
import json
from pathlib import Path
import re

import collect_narrow_reject_r1_cached_strict as c
import reconcile_r1_cached_raw722 as population
from inventory_operand_debug import Design, points
from closure_point_inventory import definition, read_xml

life, require = c.life, c.require
BASE, BASE_SEAL = population.BASE, population.BASE_SEAL
CANDIDATE, CANDIDATE_SEAL = population.CANDIDATE, population.CANDIDATE_SEAL


def baseline_contract(manifest,status,before,historical):
    require(manifest['schema']=='GAP104_HISTORICAL722_ADMISSION_V2' and manifest['output']==str(BASE) and
            status['status']=='PASS_RAW_UNION_HISTORICAL_ONLY' and status['aggregate_passed']==722 and
            status['baseline']==721 and status['new_passed']==1 and status['coverage_admitted'] is True,
            'Not formal historical722 baseline')
    require(len(historical['tests'])==len(set(historical['tests']))==721 and before['tests'][:-1]==historical['tests'] and
            len(before['tests'])==len(set(before['tests']))==722,'Not exact721 prefix retained in722')


def candidate_contract(status):
    require(status['status']=='R1_CACHED_STRICT_CANDIDATE_VERIFIED_NOT_ADMITTED' and
            status['baseline_tests']==719 and status['candidate_tests']==1 and status['new_admitted']==0 and
            status['coverage_admitted'] is False and status['targets_hit']==44 and status['targets_total']==45,
            'Not frozen complete R1 strict candidate')


def elf_unique(elfhash,basepins):
    require(len(elfhash)==64 and not any(path.endswith('.elf') and h==elfhash for path,h in basepins.items()),
            'Duplicate candidate ELF')
    return dict(sha256=elfhash,duplicate_elf=False,baseline_elf_pins=sum(p.endswith('.elf') for p in basepins))


def compiled_identity(single,targets):
    design=Design(c.DESIGN);scope=c.preflight.original.review.SCOPE
    proofs=[]
    for metric in ('line','branch','cond'):
        row=single['metrics'][metric][scope]
        node=definition(read_xml(design.db/'shape/cond.verilog.shape.xml'),design.hierarchy[scope],row['checksum']) if metric=='cond' else design.definition(scope,metric)
        actual={point['raw_index']:point for point in points(metric,node,row['width'])}
        for t in targets:
            if t['metric']!=metric:continue
            i=t['point']['raw_index']
            require((row['width'],row['checksum'])==(t['bitmap_width'],t['metric_checksum']) and actual[i]==t['point'],
                    'Exact frozen compiled target identity drift')
            proofs.append(dict(metric=metric,scope=scope,width=row['width'],checksum=row['checksum'],point=actual[i],
                               hit_single=bool(int(row['bits'],16)&(1<<(row['width']-1-i)))))
    require(len(proofs)==45,'Incomplete target identity population')
    return dict(status='EXACT_FROZEN_COMPILED_XML_IDENTITIES_VERIFIED',targets=proofs,native_DVE_qualification=False,
                raw_indices_are_DVE_selectors=False,unhit_points_remain_protected=True,exclusions_generated=False)


def evaluate():
    status=life.read_bound(CANDIDATE/'status.json',CANDIDATE_SEAL);candidate_contract(status)
    require(not (CANDIDATE/'failure.json').exists(),'Rejected candidate cannot propose admission')
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SEAL);life.check(base['output_pins'])
    basepins=json.loads((BASE/'evidence-pins.json').read_text())
    pins=life.merge_pins(basepins,base['output_pins']);pins=life.merge_pins(pins,status['pins'])
    paths=[Path(__file__).resolve(),Path(__file__).with_name('test_prepare_r1_cached_admission723.py'),
           Path(population.__file__).resolve()]
    pins=life.merge_pins(pins,{str(path):life.digest(path) for path in paths})
    pins=life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SEAL,str(CANDIDATE/'status.json'):CANDIDATE_SEAL})
    life.check(pins)
    def evidence(path):
        require(str(path) in pins,'Unsealed evidence: '+str(path));return life.read_bound(path,pins[str(path)])
    def candidate(name):return evidence(CANDIDATE/name)
    before=evidence(BASE/'combined-bits.json');histpath=Path(base['baseline'])
    histmanifest=life.read_bound(histpath/'admission-manifest.json',base['baseline_seal'])
    historical=life.read_bound(histpath/'combined-bits.json',histmanifest['output_pins'][str(histpath/'combined-bits.json')])
    baseline_contract(base,evidence(BASE/'status.json'),before,historical)
    require((BASE/'combined-inputs.txt').read_text().splitlines()==[str(c.DESIGN),*before['tests']],'722 full input order differs')
    pre=life.read_bound(c.runner.PRE/'preflight-manifest.json',c.PRE_SEAL);c.runner.validate(pre)
    identity=elf_unique(pre['pins'][pre['input_elf']],basepins)
    prepared=life.read_bound(c.RUN.with_name(c.RUN.name+'.prepared.json'),c.RUN_SEAL)
    c.terminal(evidence(c.RUN/'simulation-status.json'),evidence(c.RUN/'manifest.json'),prepared)
    require(prepared['command']==c.runner.command(c.RUN) and prepared['timeout_s']==1800 and
            prepared['old_image_files_checked']==66,'R1 simv66/ELF/1800 command contract differs')
    reference=c.oracle.shared.parse_spike_commits(c.runner.PRE/'spike.trace')
    require(c.oracle.validate(reference,pre['symbols'],(c.runner.PRE/'spike.trace').read_text())==pre['validation'],
            'Independent full Spike oracle differs')
    counts=c.common.reference_counts(reference,pre['symbols'])
    require(counts==pre['reference_counts'],'Full reference counts differ')
    scalar=c.common.spike_trace.compare_commit_prefix(c.runner.PRE/'spike.trace',c.RUN/'commit_trace.csv',0x80000000,
                   terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
    c.common.scalar_exact(scalar,counts);require(scalar==candidate('scalar-comparison.json'),'Actual scalar replay differs')
    rows=c.common.read_csv((c.RUN/'commit_trace.csv').read_bytes(),c.common.COMMIT_FIELDS)
    vectors=c.common.read_csv((c.RUN/'vector_trace.csv').read_bytes(),c.common.VECTOR_FIELDS)
    control=c.lifecycle(rows,vectors,pre['symbols']);require(control==candidate('lifecycle.json'),'Actual lifecycle replay differs')
    observed=c.observed(rows,pre['symbols']);require(observed==candidate('observed-signatures.json'),'Full26/312/VRF/guard/CSR replay differs')
    trap=json.loads(json.dumps(c.tracer_exact((c.RUN/'trace_hart_0.log').read_text(),rows,pre['symbols'])))
    require(trap==candidate('trap-proof.json'),'Actual precise24 tracer replay differs')
    vector=c.common.compare_vector_commits(c.runner.PRE/'spike.trace',c.RUN/'commit_trace.csv',c.RUN/'vector_trace.csv',0x80000000)
    c.vector_exact(vector,control['rejected_arch_seqs'],reference)
    require(vector==candidate('vector-comparison.json'),'Actual full33 vector replay differs')
    contracts=re.findall(r'\[ARA_CONTRACT\] requests=(\d+) responses=(\d+) exceptions=(\d+).*?protocol_errors=(\d+) outstanding=(\d+)',(c.RUN/'console.log').read_text())
    require(len(contracts)==1 and tuple(map(int,contracts[0]))==(control['requests'],control['responses'],24,0,0) and
            not c.common.check_contract_log(c.RUN/'run.vcs.log') and
            (c.RUN/'run.vcs.log').read_text().count('Core Test *** SUCCESS ***')==1,'Full terminal contract/SUCCESS differs')
    single=candidate('single-raw-bits.json')
    require((CANDIDATE/'diagnostic-inputs.txt').read_text().splitlines()==[str(c.DESIGN),str(c.RUN/'code.vdb')], 'Single VDB binding differs')
    identity['duplicate_vdb']=False
    proposed,delta=population.combine(before,single)
    require(sum(delta['metrics'].values())>0,'No positive fresh722 gain')
    # Reuse the sealed actual single VDB bitmap; do not recollect historical raw union.
    frozen_hits=c.target_hits(json.loads((c.BASE/'combined-bits.json').read_text()),single,pre['targets'])
    require(frozen_hits==candidate('target-hits.json'),'Frozen45 target accounting differs')
    fresh=[]
    for h in frozen_hits:
        row=before['metrics'][h['metric']][h['scope']];i=h['point']['raw_index']
        was=bool(int(row['bits'],16)&(1<<(row['width']-1-i)))
        fresh.append(dict(**h,hit722=was,new_vs722=h['hit_single'] and not was))
    require(sum(h['hit_single'] for h in fresh)==44 and
            [(h['metric'],h['point']['raw_index']) for h in fresh if not h['hit_single']]==[('line',539)], 'Unhit target protection differs')
    coverage=compiled_identity(single,pre['targets'])
    pins=life.merge_pins(pins,proposed['input_hashes']);life.check(pins)
    outputs={'combined-bits.json':proposed,'raw-bitmap-delta.json':delta,'target-reconciliation722.json':fresh,
             'coverage-identity.json':coverage,'candidate-identity.json':identity,'evidence-pins.json':pins,
             'scalar-comparison.json':scalar,'vector-comparison.json':vector,'lifecycle.json':control,
             'observed-signatures.json':observed,'trap-proof.json':trap,
             'replay-summary.json':dict(status='ACTUAL_FULL_ORACLE_REPLAY_PASS_NOT_ADMISSION',counts=counts,
                 vector_instructions=33,vector_bytes=vector['compared_bytes'],snapshots=26,checks=15489,handler_store_words=312,
                 precise_exceptions=24,illegal_backend_allocations=0,targets_hit=44,targets_total=45,
                 unhit_line_raw539_remains_protected=True,native_DVE_qualification=False,coverage_admitted=False)}
    outputs['status.json']=dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',baseline=722,aggregate_passed=723,
        new_passed=1,coverage_admitted=True,raw_delta=delta['metrics'],official_DVE_report=False,
        rtl_changed=False,new_RTL_signoff=False,simulations_started=False,inherited_722_full_oracle_readmission=False,
        sealed_strict_oracle_reused=True,actual_independent_scalar_vector_replayed=True,
        actual_lifecycle_fullVRF_CSR_guards_312stores_replayed=True,frozen_compiled_coverage_identity_checked=True,
        native_DVE_qualification_not_claimed=True,original_722_order_preserved=True,
        historical_failures_not_added=True,no_duplicate_vdb_or_elf=True,scalar_exact_counts=counts,scalar_skips=0,
        vector_instructions=33,vector_bytes=vector['compared_bytes'],checks=15489,exceptions=24,
        snapshots=26,handler_store_words=312,requests=control['requests'],responses=control['responses'],
        illegal_backend_allocations=0,targets_hit=44,targets_total=45,
        unhit_targets=[dict(metric='line',raw_index=539,source_line=2224,decision='PROTECTED_NOT_WAIVED')],
        verified_input_pins=len(pins))
    return outputs,'\n'.join([str(c.DESIGN),*proposed['tests']])+'\n'


def prepare(out):
    stage=out.with_name(out.name+'.prepare');record=out.with_name(out.name+'.prepared.json')
    require(out.parent==life.OUT and out.resolve()==out and not out.exists() and not stage.exists() and not record.exists(),
            'Fresh formal/staging/prepared paths required')
    outputs,text=evaluate();stage.mkdir()
    for name,value in outputs.items():life.save(stage/name,value)
    with (stage/'combined-inputs.txt').open('x') as stream:stream.write(text)
    staged={str(path):life.digest(path) for path in stage.iterdir() if path.is_file()}
    formal={str(out/Path(path).name):sha for path,sha in staged.items()}
    proposal=dict(status='R1_HISTORICAL723_PREPARED_FULL_REPLAY_NOT_ADMITTED',output=str(out),stage=str(stage),
                  baseline=str(BASE),baseline_seal=BASE_SEAL,
                  baseline_tests=722,candidate=str(CANDIDATE),candidate_seal=CANDIDATE_SEAL,proposed_tests=723,
                  exact722_prefix=True,unique_new_vdb=True,duplicate_elf=False,raw_delta=outputs['raw-bitmap-delta.json']['metrics'],
                  output_pins=formal,staged_pins=staged,input_pins=outputs['evidence-pins.json'],targets_hit=44,targets_total=45,
                  unhit_targets=[dict(metric='line',raw_index=539,source_line=2224,decision='PROTECTED_NOT_WAIVED')],
                  coverage_admitted=False,new_admitted=0,rtl_changed=False,simulations_started=False,
                  authorization_source='PREPARE_ONLY_AWAIT_PARENT_AGENT_REVIEW_AND_FORMAL_AUTHORIZATION')
    life.save(record,proposal)
    print(json.dumps(dict(prepared=str(record),stage=str(stage),formal_output=str(out),seal=life.digest(record),
                         pins=len(proposal['input_pins']),raw_delta=proposal['raw_delta'],admitted=0)))


def verify_prepared(out,seal):
    record=out.with_name(out.name+'.prepared.json');proposal=life.read_bound(record,seal)
    require(proposal['status']=='R1_HISTORICAL723_PREPARED_FULL_REPLAY_NOT_ADMITTED' and
            proposal['output']==str(out) and proposal['baseline_seal']==BASE_SEAL and
            proposal['candidate_seal']==CANDIDATE_SEAL and not proposal['coverage_admitted'] and
            proposal['new_admitted']==0,'Proposal identity/admission drift')
    life.check(proposal['input_pins']);life.check(proposal['staged_pins'])
    stage=out.with_name(out.name+'.prepare')
    require(proposal['stage']==str(stage) and all(Path(path).parent==stage for path in proposal['staged_pins']) and
            proposal['output_pins']=={str(out/Path(path).name):sha for path,sha in proposal['staged_pins'].items()},
            'Foreign or altered staged/formal products')
    state=json.loads((stage/'status.json').read_text())
    require(state['status']=='PASS_RAW_UNION_HISTORICAL_ONLY' and state['coverage_admitted'] is True and
            state['aggregate_passed']==723 and state['baseline']==722 and state['new_passed']==1 and
            state['targets_hit']==44 and state['targets_total']==45 and
            state['raw_delta']==proposal['raw_delta'] and sum(state['raw_delta'].values())>0,'Staged formal status differs')
    return proposal


def admit(out,seal,authorization):
    require(authorization=='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL','Separate explicit parent authorization required')
    require(not out.exists(),'Fresh formal723 directory required')
    proposal=verify_prepared(out,seal);stage=Path(proposal['stage']);out.mkdir()
    for path,sha in proposal['output_pins'].items():
        source=stage/Path(path).name;require(life.digest(source)==sha,'Staged product drift')
        with Path(path).open('xb') as stream:stream.write(source.read_bytes())
    life.check(proposal['input_pins']);life.check(proposal['output_pins'])
    manifest=dict(schema='R1_CACHED_HISTORICAL723_ADMISSION_V1',output=str(out),baseline=str(BASE),baseline_seal=BASE_SEAL,
        candidate=str(CANDIDATE),candidate_seal=CANDIDATE_SEAL,prepared=str(out.with_name(out.name+'.prepared.json')),
        prepared_seal=seal,output_pins=proposal['output_pins'],authorization=dict(source=authorization,
        parent_verification_source='PARENT_AGENT_INDEPENDENT_EXECUTION'),raw_delta=proposal['raw_delta'])
    life.save(out/'admission-manifest.json',manifest)
    print(json.dumps(dict(output=str(out),status='PASS_RAW_UNION_HISTORICAL_ONLY',aggregate_passed=723,
                         raw_delta=proposal['raw_delta'],seal=life.digest(out/'admission-manifest.json'))))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','verify','admit'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--authorization');a=p.parse_args()
    if a.mode=='prepare':require(not a.seal,'Fresh proposal only');prepare(a.output.absolute())
    elif a.mode=='verify':
        require(a.seal and not a.authorization,'Fixed proposal seal; read-only verify');verify_prepared(a.output.absolute(),a.seal)
        print('VERIFY_PASS R1_PREPARED723 FULL_REPLAY_SEALS exact722prefix admitted0')
    else:
        require(a.seal and a.authorization,'Fixed prepared seal and explicit parent authorization required')
        admit(a.output.absolute(),a.seal,a.authorization)


if __name__=='__main__':main()
