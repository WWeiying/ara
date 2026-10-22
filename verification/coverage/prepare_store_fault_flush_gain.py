"""Sealed fault/recovery qualification -> raw candidate. No EDA or admission."""
import argparse
import json
from pathlib import Path
import shlex

import run_store_fault_flush_simulation as runner
import coverage_bitmap_delta as bitmap
from inventory_operand_debug import Design, points
from closure_point_inventory import read_xml

p, life, require = runner.p, runner.life, runner.require
OUT = life.OUT
DESIGN = Path(str(life.IMAGE)+'.vdb')
RUN = OUT/'store-fault-flush-old-image-732-parent-20261006-01'
RUN_SEAL = '6101312ac73b8bdc3d75f7924681829f12ca9696930233564de1bb24e47a3a6c'
BASE = OUT/'gap109-offline-admitted-732-parent-20261006-01'
BASE_SEAL = 'badbcc7aad21ce6dab6c8c0eeabc7f85b2c13226bbe893a56c88995eab149794'
QUAL = OUT/'store-fault-flush-qualified-parent-20261006-01/qualification.json'
QUAL_SEAL = 'eccf64c9a7cce97c45a4e871aba6d555750a65c81b8908299d6b730598fb9201'
BITMAP_SHA = 'e251f049f619ca86e4a9578a468ddca8619ac532ead0ed0c5661a7ee3756e0e3'
STATUS = 'STORE_FAULT_FLUSH_RAW_GAIN_PLAN_NOT_COLLECTED_NOT_ADMITTED'
POSITIVE = 'STORE_FAULT_FLUSH_POSITIVE_PRIMARY_GAIN_CANDIDATE_NOT_ADMITTED'
HOLD = 'STORE_FAULT_FLUSH_NO_FRESH_PRIMARY_GAIN_HOLD_NOT_ADMITTED'


def qualification(record):
    require(record['status']=='STORE_FAULT_FLUSH_FULL_RETIREMENT_MEMORY_NATIVE_PASS_NOT_ADMITTED' and
        record['checks']==134 and record['UVM_errors']==0 and type(record['OS_returncode']) is int and
        record['OS_returncode']==0 and record['terminal_source']=='FOREGROUND_RUNNER_OS_RETURN_RECEIPT' and
        record['static_provenance_population']==731 and
        record['raw_gain_requires_latest_formal_baseline_at_least']==732, 'Strict actual DUT qualification required')
    for key in ('coverage_admitted','whole_ISA_qualified','native_B_error_plus_addr_fault_timing_measured','target_hit_verified'):
        require(record[key] is False,'Qualification scope promoted: '+key)
    require(record['raw_gain_not_collected'] is True,'Not original qualification phase')


def union(before, single):
    population=len(before['tests'])
    require(population>=732 and len(set(before['tests']))==population,'Unique formal732+ required')
    require(single['tests']==[str(RUN/'code.vdb')] and single['tests'][0] not in before['tests'],'Wrong/duplicate singleton')
    for sample in (before,single):
        require(set(sample['metrics'])==set(bitmap.METRICS) and
                sum(len(x) for x in sample['metrics'].values())==6162,'Incomplete6162 universe')
        for rows in sample['metrics'].values():
            for row in rows.values():
                require(type(row['width']) is int and row['width']>=0 and
                    0<=int(row['bits'],16)<(1<<row['width']),'Malformed/overflow bitmap')
    life.merge_pins(before['input_hashes'],single['input_hashes'])
    combined=bitmap.combine(before,single)
    require(combined['tests']==before['tests']+single['tests'] and len(set(combined['tests']))==population+1,
            'Exact formal prefix lost')
    for metric,rows in before['metrics'].items():
        for scope,row in rows.items():
            require(combined['metrics'][metric][scope]['bits']==
                hex(int(row['bits'],16)|int(single['metrics'][metric][scope]['bits'],16)),'Full OR differs')
    return combined,bitmap.delta(before,combined)


def target_hits(before,single,targets):
    require(len(targets)==2 and [t['role'] for t in targets]==['primary','conditional_witness'],'Exact target roles required')
    hits=[]
    for t in targets:
        old=before['metrics'][t['metric']][t['scope']]; new=single['metrics'][t['metric']][t['scope']]
        require((old['width'],old['checksum'])==(new['width'],new['checksum'])==(t['width'],t['checksum']),
                'Target shape/checksum drift')
        mask=1<<(t['width']-1-t['point']['raw_index'])
        a,b=bool(int(old['bits'],16)&mask),bool(int(new['bits'],16)&mask)
        hits.append(dict(t,before_hit=a,single_hit=b,after_hit=a or b,fresh_target_gain=b and not a,
                         DVE_native_exclusion_qualified=False))
    return hits


def candidate_status(delta,hits):
    return POSITIVE if sum(delta['metrics'].values())>0 and hits[0]['fresh_target_gain'] else HOLD


def single_identity(single,rawpins):
    directory=RUN/'code.vdb/snps/coverage/db/testdata'/p.NAME
    expected={str(directory/(m+'.verilog.data.xml')):rawpins[str(directory/(m+'.verilog.data.xml'))]
              for m in bitmap.METRICS}
    require(single['input_hashes']==expected,'Exact four singleton data pins required; design hashes stay in design')


def inputs(qualpath,qualseal,baseline,baseseal):
    require(qualpath==QUAL and qualseal==QUAL_SEAL,'Exact parent DUT qualification required')
    require(qualpath.resolve()==qualpath and qualpath.parent.parent==OUT,'Direct sealed qualification required')
    record=life.read_bound(qualpath,qualseal);qualification(record)
    pins=life.merge_pins(record['pins'],{str(qualpath):qualseal})
    sidecar=RUN.with_name(RUN.name+'.prepared.json')
    prepared=life.read_bound(sidecar,RUN_SEAL)
    pre=runner.verify_preflight(Path(prepared['preflight']).parent,prepared['preflight_seal'])
    require(prepared['output']==str(RUN) and prepared['command']==runner.command(RUN,runner.PRE) and
        prepared['timeout_s']==600 and prepared['software_checks']==134 and prepared['old_image_files_checked']==66 and
        prepared['elf_sha256']==pre['input_elf_sha256'] and prepared['image_sha256']==runner.preflight.guarded.IMAGE_SHA and
        prepared['coverage_admitted'] is False and prepared['admission_performed'] is False,'Sealed runner contract differs')
    pins=life.merge_pins(pins,prepared['pins']);pins=life.merge_pins(pins,{str(sidecar):RUN_SEAL})
    for name in ('simulation-status.json','manifest.json','started.json','commit_trace.csv','vector_trace.csv',
                 'console.log','run.vcs.log','trace_hart_0.log','trace_hart_0_commit.log'):
        require(str(RUN/name) in record['pins'],'Qualification dropped actual evidence: '+name)
    require(baseline.parent==OUT and baseline.resolve()==baseline,'Direct formal baseline required')
    manifest=life.read_bound(baseline/'admission-manifest.json',baseseal)
    require(manifest['output']==str(baseline) and all(Path(x).parent==baseline for x in manifest['output_pins']),
            'Formal output ownership differs')
    pins=life.merge_pins(pins,manifest['output_pins']);pins=life.merge_pins(pins,{str(baseline/'admission-manifest.json'):baseseal})
    before=life.read_bound(baseline/'combined-bits.json',pins[str(baseline/'combined-bits.json')])
    state=life.read_bound(baseline/'status.json',pins[str(baseline/'status.json')])
    require(state['status']=='PASS_RAW_UNION_HISTORICAL_ONLY' and state['coverage_admitted'] is True and
            state['aggregate_passed']==len(before['tests'])>=732,'Not formal732+ admitted')
    anchor_manifest=life.read_bound(BASE/'admission-manifest.json',BASE_SEAL)
    anchor=life.read_bound(BASE/'combined-bits.json',anchor_manifest['output_pins'][str(BASE/'combined-bits.json')])
    require(len(anchor['tests'])==732 and before['tests'][:732]==anchor['tests'] and before['design']==anchor['design'],
            'Exact732 prefix/design differs')
    require(all(before['input_hashes'].get(x)==h for x,h in anchor['input_hashes'].items()),'732 inherited inputs lost')
    bitmap.delta(anchor,before)
    pins=life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SEAL,
        str(BASE/'combined-bits.json'):anchor_manifest['output_pins'][str(BASE/'combined-bits.json')]})
    require((baseline/'combined-inputs.txt').read_text().splitlines()==[str(DESIGN),*before['tests']],'Formal VDB ordering differs')
    pins=life.merge_pins(pins,before['input_hashes'])
    receipt=json.loads((runner.PRE/'target-receipt.json').read_bytes())
    primary=receipt['primary_target'];witness=receipt['conditional_branch_witness']
    require(primary['scope']==p.SCOPE and primary['width']==91 and primary['checksum']=='3108353264' and
        primary['module_checksum']=='3820166273' and primary['point']['raw_index']==54 and
        primary['point']['line']=='583' and primary['point']['expression']=="store_b_exception_d.valid = 1'b1;" and
        primary['point']['attributes']['chksum']=='3222737' and primary['point']['file_id']=='564',
        'Exact source-bound primary differs')
    require(witness['scope']==p.SCOPE and witness['point']['raw_index']==43 and
        witness['point']['line']=='578' and witness['exact_case_vector_outcome_not_assumed'] is True,'Conditional witness differs')
    targets=[dict(primary,role='primary'),dict(witness,role='conditional_witness')]
    design=Design(DESIGN)
    for t in targets:
        row=before['metrics'][t['metric']][t['scope']]
        require((row['width'],row['checksum'])==(t['width'],t['checksum']),'Formal target shape differs')
        actual=next(x for x in points(t['metric'],design.definition(t['scope'],t['metric']),row['width'])
                    if x['raw_index']==t['point']['raw_index'])
        require(actual==t['point'],'Compiled expression/file/line/signature differs')
    require(design.hierarchy[p.SCOPE].get('chksum')==primary['module_checksum'],'Compiled module identity differs')
    directory=RUN/'code.vdb/snps/coverage/db/testdata'/p.NAME
    require(directory.parent.resolve()==directory.parent and list(directory.parent.iterdir())==[directory],
            'Wrong/extra singleton testdata')
    names={'vcmArguments.xml','siminfo.xml',*{m+'.verilog.data.xml' for m in (*bitmap.METRICS,'tgl')}}
    require({x.name for x in directory.iterdir()}==names,'Singleton membership differs')
    args=read_xml(directory/'vcmArguments.xml');info=read_xml(directory/'siminfo.xml')
    options=[x.get('vcm_opt') for x in args.iter('vcm_arg_data') if x.get('vcm_opt') is not None]
    tests=list(info.iter('srctest'))
    require(args.get('compvdbpath')==str(DESIGN) and len(options)==5 and
        set(options)=={'-cm '+m for m in ('line','cond','branch','fsm','tgl')} and len(tests)==1 and
        shlex.split(tests[0].get('cmdline',''))==prepared['command'] and tests[0].get('workdir')==str(RUN) and
        tests[0].get('seed')=='1' and tests[0].get('teststatus')=='unknown','Raw singleton metadata identity differs')
    rawpins={}
    for x in directory.iterdir():
        require(x.is_file() and not x.is_symlink(),'Aliased raw evidence');rawpins[str(x)]=life.digest(x)
    pins=life.merge_pins(pins,rawpins)
    require(life.digest(Path(bitmap.__file__))==BITMAP_SHA,'Frozen bitmap parser drift')
    for x in (Path(__file__).resolve(),Path(__file__).with_name('test_prepare_store_fault_flush_gain.py')):
        pins=life.merge_pins(pins,{str(x):life.digest(x)})
    life.check(pins)
    return before,targets,pins,rawpins


def prepare(out,qualpath,qualseal,baseline,baseseal):
    require(out.parent==OUT and out.resolve()==out and not out.exists(),'Fresh plan required')
    before,targets,pins,rawpins=inputs(qualpath,qualseal,baseline,baseseal)
    out.mkdir();life.save(out/'plan.json',dict(status=STATUS,qualification=str(qualpath),qualification_seal=qualseal,
        baseline=str(baseline),baseline_seal=baseseal,baseline_tests=len(before['tests']),exact732_prefix=True,
        full_OR_instances=6162,targets=targets,pins=pins,singleton_pins=rawpins,coverage_admitted=False,
        actual_raw_collected=False,application_approval=False))
    print(json.dumps(dict(plan=str(out/'plan.json'),seal=life.digest(out/'plan.json'),actual_raw_collected=False)))


def replay(plan):
    require(plan['status']==STATUS and plan['coverage_admitted'] is False and plan['application_approval'] is False,
            'Gain plan scope differs')
    result=inputs(Path(plan['qualification']),plan['qualification_seal'],Path(plan['baseline']),plan['baseline_seal'])
    before,targets,pins,rawpins=result
    require((targets,pins,rawpins,len(before['tests']))==(plan['targets'],plan['pins'],plan['singleton_pins'],plan['baseline_tests']),
            'Gain plan evidence drift')
    return result


def collect(planpath,seal,out):
    plan=life.read_bound(planpath,seal);before,targets,pins,rawpins=replay(plan)
    require(out.parent==OUT and out.resolve()==out and not out.exists(),'Fresh candidate required')
    pins=life.merge_pins(pins,{str(planpath):seal});life.check(pins);out.mkdir()
    try:
        (out/'single-inputs.txt').write_text(str(DESIGN)+'\n'+str(RUN/'code.vdb')+'\n')
        single=bitmap.collect(out/'single-inputs.txt')
        single_identity(single,rawpins)
        combined,delta=union(before,single);hits=target_hits(before,single,targets)
        for n,value in [('single-bits.json',single),('combined-bits.json',combined),('raw-delta.json',delta),
                        ('target-hits.json',hits),('evidence-pins.json',pins)]:life.save(out/n,value)
        (out/'combined-inputs.txt').write_text('\n'.join([str(DESIGN),*combined['tests']])+'\n')
        life.check(pins)
        outputpins={str(x):life.digest(x) for x in out.iterdir() if x.is_file()}
        life.save(out/'candidate.json',dict(status=candidate_status(delta,hits),output=str(out),plan=str(planpath),plan_seal=seal,
            qualification=plan['qualification'],qualification_seal=plan['qualification_seal'],
            baseline=plan['baseline'],baseline_seal=plan['baseline_seal'],baseline_tests=len(before['tests']),
            proposed_population=len(combined['tests']),exact732_prefix=True,full_OR_instances=6162,
            raw_delta=delta['metrics'],primary_fresh_gain=hits[0]['fresh_target_gain'],output_pins=outputpins,
            coverage_admitted=False,application_approval=False,DVE_native_exclusion_qualified=False,
            native_B_error_plus_addr_fault_timing_measured=False))
        print(json.dumps(dict(seal=life.digest(out/'candidate.json'),status=candidate_status(delta,hits))))
    except Exception as e:
        life.save(out/'failure.json',dict(status='RAW_GAIN_HOLD_NOT_ADMITTED',reason=str(e)));raise


def verify(out,seal):
    record=life.read_bound(out/'candidate.json',seal)
    require(record['output']==str(out) and record['coverage_admitted'] is False and
        record['application_approval'] is False and record['DVE_native_exclusion_qualified'] is False and
        record['native_B_error_plus_addr_fault_timing_measured'] is False,'Candidate scope differs')
    names=('single-inputs.txt','single-bits.json','combined-bits.json','raw-delta.json','target-hits.json','evidence-pins.json','combined-inputs.txt')
    require(set(record['output_pins'])=={str(out/n) for n in names},'Dropped/foreign output pins');life.check(record['output_pins'])
    plan=life.read_bound(Path(record['plan']),record['plan_seal']);before,targets,pins,rawpins=replay(plan)
    require(json.loads((out/'evidence-pins.json').read_bytes())==life.merge_pins(pins,{record['plan']:record['plan_seal']}),'Evidence pins lost')
    require((out/'single-inputs.txt').read_text().splitlines()==[str(DESIGN),str(RUN/'code.vdb')],'Singleton order differs')
    single=bitmap.collect(out/'single-inputs.txt');single_identity(single,rawpins)
    combined,delta=union(before,single);hits=target_hits(before,single,targets)
    for n,value in [('single-bits.json',single),('combined-bits.json',combined),('raw-delta.json',delta),('target-hits.json',hits)]:
        require(json.loads((out/n).read_bytes())==value,'Candidate replay differs: '+n)
    require(record['status']==candidate_status(delta,hits) and record['raw_delta']==delta['metrics'] and
        record['primary_fresh_gain']==hits[0]['fresh_target_gain'] and record['baseline']==plan['baseline'] and
        record['baseline_seal']==plan['baseline_seal'] and record['qualification']==plan['qualification'] and
        record['qualification_seal']==plan['qualification_seal'] and record['baseline_tests']==len(before['tests']) and
        record['proposed_population']==len(combined['tests']) and record['full_OR_instances']==6162 and
        record['exact732_prefix'] is True,'Candidate population/gain differs')
    require((out/'combined-inputs.txt').read_text().splitlines()==[str(DESIGN),*combined['tests']],'Exact prefix differs')
    life.check(pins);life.check(record['output_pins']);return record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','verify-plan','collect','verify-candidate'))
    parser.add_argument('--qualification',type=Path);parser.add_argument('--qualification-seal')
    parser.add_argument('--baseline',type=Path);parser.add_argument('--baseline-seal')
    parser.add_argument('--output',type=Path);parser.add_argument('--plan',type=Path);parser.add_argument('--seal')
    a=parser.parse_args()
    if a.mode=='prepare':
        require(all((a.qualification,a.qualification_seal,a.baseline,a.baseline_seal,a.output)),'Explicit sealed inputs required')
        prepare(a.output.absolute(),a.qualification.absolute(),a.qualification_seal,a.baseline.absolute(),a.baseline_seal)
    elif a.mode=='verify-plan':
        require(a.plan and a.seal,'Plan/seal required');replay(life.read_bound(a.plan,a.seal));print('VERIFY_PLAN_PASS NO_COLLECTION')
    elif a.mode=='collect':
        require(a.plan and a.seal and a.output,'Plan/seal/output required');collect(a.plan.absolute(),a.seal,a.output.absolute())
    else:
        require(a.output and a.seal,'Candidate/seal required');verify(a.output.absolute(),a.seal);print('VERIFY_CANDIDATE_PASS NOT_ADMITTED')


if __name__=='__main__':main()
