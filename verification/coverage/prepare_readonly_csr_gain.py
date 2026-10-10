"""Sealed readonly CSR qualification -> raw candidate. No EDA or admission."""
import argparse
import json
from pathlib import Path
import shlex

import qualify_readonly_csr_terminal as qualifier
import coverage_bitmap_delta as bitmap
from inventory_operand_debug import Design, points
from closure_point_inventory import read_xml

p, life, require = qualifier.p, qualifier.life, qualifier.require
OUT = life.OUT
DESIGN = Path(str(life.IMAGE)+'.vdb')
RUN = qualifier.RUN
RUN_SEAL = qualifier.RUN_SEAL
BASE = OUT/'gap110-offline-admitted-734-parent-20261006-01'
BASE_SEAL = '388c041fc323289521358ee2ef08bad6367cbb3b93fe3adabf6527d0a4847261'
QUAL = OUT/'readonly-csr-terminal-qualified-parent-20261006-01/qualification.json'
QUAL_SEAL = 'dd87ac132013bd97db883a65d2ca680631bc8b57f056e05bfb97f454d5e073d4'
QUALIFIER_SHA = '25f8b70a243998c5597e103876aeb24210099bea97cd12d337b7626ca09601d8'
QUAL_PLAN_SEAL = '9630d7bc5e8763f7571c62478c6c8ca578080469f3a21625bc640bd69bc51d5e'
BITMAP_SHA = 'e251f049f619ca86e4a9578a468ddca8619ac532ead0ed0c5661a7ee3756e0e3'
STATUS = 'READONLY_CSR_RAW_GAIN_PLAN_NOT_COLLECTED_NOT_ADMITTED'
POSITIVE = 'READONLY_CSR_POSITIVE_PRIMARY_GAIN_CANDIDATE_NOT_ADMITTED'
HOLD = 'READONLY_CSR_NO_FRESH_PRIMARY_GAIN_HOLD_NOT_ADMITTED'


def qualification(record):
    require(record['status']=='READONLY_CSR_FULL_SCALAR_VECTOR_CSR_TRAP_MEMORY_NATIVE_PASS_NOT_ADMITTED' and
        type(record['checks']) is int and record['checks']==733 and record['illegal_traps']==12 and
        type(record['UVM_errors']) is int and record['UVM_errors']==0 and
        type(record['OS_returncode']) is int and record['OS_returncode']==0 and
        record['terminal_source']=='FOREGROUND_RUNNER_OS_RETURN_RECEIPT' and
        record['native_known_write_bytes']==264 and record['full_memory_bytes']==432 and
        record['software_reference_is_Spike'] is True and record['static_baseline']==733 and
        record['raw_gain_requires_latest_formal_population_at_least']==734,
        'Exact full scalar/vector/CSR/trap/memory qualification required')
    for key in ('coverage_admitted','whole_ISA_qualified','target_hits_verified','raw_gain_collected',
                'native_cycle_qualified','simulation_retried'):
        require(record[key] is False,'Qualification scope promoted: '+key)


def union(before, single):
    population=len(before['tests'])
    require(population>=734 and len(set(before['tests']))==population,'Unique formal734+ required')
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


def validate_targets(targets):
    cond=(570,572,574,582,584,586,594,596,598,606,608,610)
    line=(1374,1377,1380,1389,1392,1395,1410,1413,1416,1425,1428,1431)
    source=(4677,4682,4687,4715,4720,4725,4778,4783,4788,4819,4824,4829)
    native=(243,244,245,248,249,250,253,254,255,258,259,260)
    require(len(targets)==24,'All24 source-bound targets required')
    for metric,indices,width,checksum in (('cond',cond,1140,'1370170966'),('line',line,1718,'1316526434')):
        rows=[t for t in targets if t['metric']==metric]
        require(len(rows)==12 and [t['case'] for t in rows]==list(range(12)) and
                [t['point']['raw_index'] for t in rows]==list(indices),'Exact12 case/coordinates required')
        for t in rows:
            point=t['point']
            require(t['scope']==p.SCOPE and t['width']==width and t['checksum']==checksum and
                t['module_checksum']=='1448229316' and t['hit733'] is False and point['file_id']=='547',
                'Target scope/shape/source identity differs')
            require(point['line']==str(source[t['case']]+(metric=='line')),'Exact source coordinate required')
            if metric=='cond':
                require(point['expression']=="(instr.itype.rs1 == '0)" and point['vector']=='0' and
                        point['attributes']['optype']=='16' and point['native_id']==str(native[t['case']]),
                        'Exact false rs1-field condition required')
            else:
                require(point['expression']=="illegal_insn = 1'b1;",'Exact illegal line required')


def target_hits(before,single,targets):
    validate_targets(targets)
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
    require(set(delta['metrics'])==set(bitmap.METRICS) and
            all(type(v) is int and v>=0 for v in delta['metrics'].values()),'Invalid raw delta')
    return POSITIVE if sum(delta['metrics'].values())>0 and any(h['fresh_target_gain'] for h in hits) else HOLD


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
    require(life.digest(Path(qualifier.__file__))==QUALIFIER_SHA and
            record['pins'].get(str(Path(qualifier.__file__).resolve()))==QUALIFIER_SHA,
            'Frozen qualifier identity differs')
    require(QUAL_PLAN_SEAL in record['pins'].values(),'Exact reviewed qualification plan pin missing')
    pre=qualifier.verify_prepared(RUN,prepared)
    pins=life.merge_pins(pins,prepared['pins']);pins=life.merge_pins(pins,{str(sidecar):RUN_SEAL})
    for name in ('scalar-comparison.json','vector-comparison.json','observed-memory.json','lifecycle.json','trap-proof.json'):
        require(str(qualpath.parent/name) in record['pins'],'Missing full qualification proof: '+name)
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
            state['aggregate_passed']==len(before['tests'])>=734,'Not formal734+ admitted')
    anchor_manifest=life.read_bound(BASE/'admission-manifest.json',BASE_SEAL)
    anchor=life.read_bound(BASE/'combined-bits.json',anchor_manifest['output_pins'][str(BASE/'combined-bits.json')])
    require(len(anchor['tests'])==734 and before['tests'][:734]==anchor['tests'] and before['design']==anchor['design'],
            'Exact734 prefix/design differs')
    require(all(before['input_hashes'].get(x)==h for x,h in anchor['input_hashes'].items()),'734 inherited inputs lost')
    bitmap.delta(anchor,before)
    pins=life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SEAL,
        str(BASE/'combined-bits.json'):anchor_manifest['output_pins'][str(BASE/'combined-bits.json')]})
    require((baseline/'combined-inputs.txt').read_text().splitlines()==[str(DESIGN),*before['tests']],'Formal VDB ordering differs')
    pins=life.merge_pins(pins,before['input_hashes'])
    targets=pre['targets'];validate_targets(targets)
    receipt=life.read_bound(qualifier.PRE/'target-receipt.json',
                          pre['pins'][str(qualifier.PRE/'target-receipt.json')])
    require(receipt['targets']==targets,'Frozen source receipt/targets differ')
    design=Design(DESIGN)
    for t in targets:
        row=before['metrics'][t['metric']][t['scope']]
        require((row['width'],row['checksum'])==(t['width'],t['checksum']),'Formal target shape differs')
        if t['metric']=='cond':
            root=read_xml(design.db/'shape/cond.verilog.shape.xml')
            nodes=[n for n in root if n.get('id')==design.hierarchy[t['scope']].get('id') and
                   n.get('chksum')==row['checksum']]
            require(len(nodes)==1,'Unique compiled condition definition required')
            definition=nodes[0]
        else:
            definition=design.definition(t['scope'],t['metric'])
        actual=[x for x in points(t['metric'],definition,row['width'])
                if x['raw_index']==t['point']['raw_index']]
        require(actual==[t['point']],'Compiled expression/file/line/signature differs')
        require(design.hierarchy[t['scope']].get('chksum')==t['module_checksum'],'Compiled module differs')
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
    for x in (Path(__file__).resolve(),Path(__file__).with_name('test_prepare_readonly_csr_gain.py')):
        pins=life.merge_pins(pins,{str(x):life.digest(x)})
    life.check(pins)
    return before,targets,pins,rawpins


def prepare(out,qualpath,qualseal,baseline,baseseal):
    require(out.parent==OUT and out.resolve()==out and not out.exists(),'Fresh plan required')
    before,targets,pins,rawpins=inputs(qualpath,qualseal,baseline,baseseal)
    out.mkdir();life.save(out/'plan.json',dict(status=STATUS,qualification=str(qualpath),qualification_seal=qualseal,
        baseline=str(baseline),baseline_seal=baseseal,baseline_tests=len(before['tests']),exact734_prefix=True,
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
            proposed_population=len(combined['tests']),exact734_prefix=True,full_OR_instances=6162,
            raw_delta=delta['metrics'],primary_fresh_gain=any(h['fresh_target_gain'] for h in hits),output_pins=outputpins,
            coverage_admitted=False,application_approval=False,DVE_native_exclusion_qualified=False,
            native_cycle_qualified=False))
        print(json.dumps(dict(seal=life.digest(out/'candidate.json'),status=candidate_status(delta,hits))))
    except Exception as e:
        life.save(out/'failure.json',dict(status='RAW_GAIN_HOLD_NOT_ADMITTED',reason=str(e)));raise


def verify(out,seal):
    record=life.read_bound(out/'candidate.json',seal)
    require(record['output']==str(out) and record['coverage_admitted'] is False and
        record['application_approval'] is False and record['DVE_native_exclusion_qualified'] is False and
        record['native_cycle_qualified'] is False,'Candidate scope differs')
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
        record['primary_fresh_gain']==any(h['fresh_target_gain'] for h in hits) and record['baseline']==plan['baseline'] and
        record['baseline_seal']==plan['baseline_seal'] and record['qualification']==plan['qualification'] and
        record['qualification_seal']==plan['qualification_seal'] and record['baseline_tests']==len(before['tests']) and
        record['proposed_population']==len(combined['tests']) and record['full_OR_instances']==6162 and
        record['exact734_prefix'] is True,'Candidate population/gain differs')
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
