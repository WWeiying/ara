"""Compact exact-prefix admission proposal; scoped Toggle gain is separate from four-metric OR."""
import argparse
import json
from pathlib import Path
import coverage_bitmap_delta as bitmap
import qualify_gap113_payload_toggle as q

life,require=q.life,q.require
BASE=life.OUT/'queue-mask-offline-admitted-740-agent-20261007-01'
BASE_SEAL='752d493c5fa8179ddd414d7810da479b1a56341a1600dff56c5b5afa0a3304b5'
QUAL=life.OUT/'gap113-payload-toggle-qualified-agent-20261007-01/qualification.json'
QUAL_SEAL='925fffaa27020ca24b697ad5f36cd5f74e813544ce3315a539df3c185cfdbd0b'
DESIGN=Path(str(life.IMAGE)+'.vdb')


def qualification_contract(proof,audit,gain):
    require(proof['status']=='GAP113_NATIVE_PASS_POSITIVE_SCOPED_TOGGLE_GAIN_NOT_ADMITTED' and
        proof['coverage_admitted'] is False and proof['full_scalar_isa_verified'] is False and
        proof['spike_custom_isa_pass'] is False,'Exact native qualification scope')
    for key,value in dict(checks=41,full_vrf_bytes=8192,initial_vrf_bytes=8192,csr_values=24,
        source_guard_bytes=7328,custom_write_bytes=240,custom_preserved_vrf_bytes=7952).items():
        require(type(audit.get(key)) is type(value) and audit[key]==value,'Incomplete native audit: '+key)
    require(len(audit['bindings'])==2 and audit['contract']['exceptions']==0 and
        audit['contract']['protocol_errors']==0 and audit['contract']['outstanding']==0 and
        audit['contract']['requests']==audit['contract']['responses'],'Complete native lifecycle contract')
    require(gain['baseline_population']==740 and gain['metric']=='tgl' and
        gain['total_new_serialized_toggle_positions']>0 and gain['coverage_admitted'] is False and
        gain['official_percentage'] is False and gain['direction_binding_verified'] is False,'Positive scoped raw Toggle required')


def combine(before,single):
    require(set(before['metrics'])==set(single['metrics'])==set(bitmap.METRICS),'Four metrics only')
    require(before['tests'] and len(before['tests'])==len(set(before['tests'])) and
        len(single['tests'])==1 and single['tests'][0] not in before['tests'],'Unique new singleton / exact prefix')
    life.merge_pins(before['input_hashes'],single['input_hashes'])
    for data in (before,single):
        for rows in data['metrics'].values():
            for row in rows.values():
                require(type(row['width']) is int and row['width']>=0 and
                    0<=int(row['bits'],16)<1<<row['width'],'Malformed raw bitmap')
    after=bitmap.combine(before,single)
    require(after['tests']==before['tests']+single['tests'],'Lost baseline order')
    return after,bitmap.delta(before,after)


def elf_hashes(pins):
    pending=[pins];seen=set();hashes=set()
    while pending:
        for name,sha in pending.pop().items():
            path=Path(name)
            if path.suffix.lower()=='.elf':life.check({name:sha});hashes.add(sha)
            elif path.name.endswith('pins.json') and name not in seen:
                seen.add(name);value=life.read_bound(path,sha)
                require(isinstance(value,dict),'Malformed nested pin ledger');pending.append(value)
    return hashes


def bound_inputs():
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SEAL)
    proof=life.read_bound(QUAL,QUAL_SEAL)
    pins=life.merge_pins(base['input_pins'],base['output_pins'])
    pins=life.merge_pins(pins,proof['output_pins'])
    qpins=life.read_bound(QUAL.parent/'evidence-pins.json',proof['output_pins'][str(QUAL.parent/'evidence-pins.json')])
    pins=life.merge_pins(pins,qpins)
    pins=life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SEAL,str(QUAL):QUAL_SEAL})
    life.check(pins)
    before=life.read_bound(BASE/'combined-bits.json',pins[str(BASE/'combined-bits.json')])
    state=life.read_bound(BASE/'status.json',pins[str(BASE/'status.json')])
    require(base['output']==str(BASE) and state['coverage_admitted'] is True and
        state['status']=='PASS_RAW_UNION_HISTORICAL_ONLY' and
        state['aggregate_passed']==len(before['tests'])==740,'Exact formal740 required')
    require((BASE/'combined-inputs.txt').read_text().splitlines()==[str(DESIGN),*before['tests']],
            'Baseline design/input order differs')
    audit=life.read_bound(QUAL.parent/'runtime-audit.json',proof['output_pins'][str(QUAL.parent/'runtime-audit.json')])
    gain=life.read_bound(QUAL.parent/'toggle-gain.json',proof['output_pins'][str(QUAL.parent/'toggle-gain.json')])
    qualification_contract(proof,audit,gain)
    require(str(q.RUN/'code.vdb') not in before['tests'],'Duplicate candidate VDB')
    book=life.read_bound(BASE/'evidence-pins.json',pins[str(BASE/'evidence-pins.json')])
    require(q.runner.ELF_SHA not in elf_hashes(book),'Duplicate candidate ELF')
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_gap113_offline741.py'),
        Path(bitmap.__file__).resolve(),life.ROOT/'verification/coverage/run_dve_coverage.sh',
        life.ROOT/'verification/coverage/export_dve_coverage.tcl',life.ROOT/'verification/coverage/prepare_dve_waivers.py'):
        pins=life.merge_pins(pins,{str(path):life.digest(path)})
    return before,pins,gain


def prepare(out):
    stage=out.with_name(out.name+'.prepare');record=out.with_name(out.name+'.prepared.json')
    require(not out.exists() and not stage.exists() and not record.exists(),'Fresh independent proposal required')
    before,pins,sealed_gain=bound_inputs();stage.mkdir()
    inputs=stage/'singleton-inputs.txt';inputs.write_text(str(DESIGN)+'\n'+str(q.RUN/'code.vdb')+'\n')
    single=bitmap.collect(inputs)
    require(single['tests']==[str(q.RUN/'code.vdb')] and
        all(pins.get(p)==sha for p,sha in single['input_hashes'].items()),'Unpinned candidate raw metrics')
    for rel,sha in single['design'].items():
        require(pins.get(str(DESIGN/'snps/coverage/db'/rel))==sha,'Unpinned compiled design')
    after,delta=combine(before,single)
    files=list((q.RUN/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(files)==1 and files[0].parent.name==q.runner.NAME,'Exact candidate native test')
    sample,sha=q.toggle.rows(files[0],sorted(sealed_gain['scopes']))
    require(pins[str(files[0])]==sha,'Candidate Toggle pin differs')
    evidence=life.read_bound(q.recipe.EVIDENCE,q.EVIDENCE_SHA);gain=q.scoped_gain(sample,evidence)
    require(gain==sealed_gain,'Scoped gain differs from parent-qualified actual measurement')
    target=q.recipe.target(evidence);hits=set(gain['primary_target_hits'])
    points=[dict(raw_index=i,actual_hit=i in hits) for i in target['serialized_zero_coordinates']]
    products={'single-bits.json':single,'combined-bits.json':after,'raw-delta.json':delta,
        'toggle-single.json':sample,'toggle-gain.json':gain,'primary-target-hits.json':points}
    for name,value in products.items():life.save(stage/name,value)
    (stage/'combined-inputs.txt').write_text('\n'.join([str(DESIGN),*after['tests']])+'\n')
    pins=life.merge_pins(pins,{str(inputs):life.digest(inputs)});life.check(pins)
    stagepins={str(p):life.digest(p) for p in stage.iterdir() if p.is_file()}
    config=dict(schema='GAP113_SINGLETON_ADMISSION_PREPARED_NOT_ADMITTED',output=str(out),stage=str(stage),
        baseline=str(BASE),baseline_seal=BASE_SEAL,qualification=str(QUAL),qualification_seal=QUAL_SEAL,
        baseline_count=len(before['tests']),proposed_count=len(after['tests']),input_pins=pins,stage_pins=stagepins,
        raw_delta=delta['metrics'],scoped_toggle_new=gain['total_new_serialized_toggle_positions'],
        primary_targets=len(points),primary_targets_hit=len(hits),coverage_admitted=False,
        official_DVE_report=False,dve_command=['env','-u','DVE','DVE_WAIVERS=off','DVE_COVERAGE_TIMEOUT=900',
            'bash',str(life.ROOT/'verification/coverage/run_dve_coverage.sh'),
            str(out.with_name(out.name+'-raw-dve')), '--inputs-file',str(out/'combined-inputs.txt')],
        dve_environment=dict(DVE_WAIVERS='off',DVE_COVERAGE_TIMEOUT='900'),dve_unset=['DVE'])
    life.save(record,config)
    return dict(prepared=str(record),seal=life.digest(record),raw_delta=config['raw_delta'],
                scoped_toggle_new=config['scoped_toggle_new'],primary_targets_hit=len(hits))


def verify(out,seal):
    record=out.with_name(out.name+'.prepared.json');config=life.read_bound(record,seal)
    require(config['output']==str(out) and config['baseline_seal']==BASE_SEAL and
        config['qualification_seal']==QUAL_SEAL and config['coverage_admitted'] is False,'Exact proposal binding')
    require(not out.exists(),'Preserve existing formal output');stage=Path(config['stage'])
    require(stage==out.with_name(out.name+'.prepare'),'Stage owner differs')
    life.check(config['input_pins']);life.check(config['stage_pins'])
    def read(path):return life.read_bound(path,config['stage_pins'].get(str(path),config['input_pins'].get(str(path))))
    before=read(BASE/'combined-bits.json');single=read(stage/'single-bits.json');after,delta=combine(before,single)
    require(single['tests']==[str(q.RUN/'code.vdb')] and after==read(stage/'combined-bits.json') and
        delta==read(stage/'raw-delta.json') and delta['metrics']==config['raw_delta'],'Proposed complete four-metric OR differs')
    require((stage/'combined-inputs.txt').read_text().splitlines()==[str(DESIGN),*after['tests']] and
        len(after['tests'])==config['proposed_count']==config['baseline_count']+1,'Exact prefix/singleton differs')
    evidence=life.read_bound(q.recipe.EVIDENCE,q.EVIDENCE_SHA)
    gain=q.scoped_gain(read(stage/'toggle-single.json'),evidence)
    require(gain==read(stage/'toggle-gain.json') and gain['total_new_serialized_toggle_positions']==config['scoped_toggle_new']>0,
            'Positive scoped Toggle proof differs')
    return config


def admit(out,seal,authorized):
    require(authorized,'Parent authorization required');config=verify(out,seal);stage=Path(config['stage']);out.mkdir()
    for path in stage.iterdir():
        if path.name!='singleton-inputs.txt':(out/path.name).write_bytes(path.read_bytes())
    pins=life.merge_pins(config['input_pins'],config['stage_pins'])
    pins=life.merge_pins(pins,{str(out.with_name(out.name+'.prepared.json')):seal})
    life.save(out/'evidence-pins.json',pins)
    life.save(out/'status.json',dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',aggregate_passed=config['proposed_count'],
        baseline=config['baseline_count'],new_passed=1,coverage_admitted=True,exact_baseline_prefix=True,
        unique_new_vdb=True,duplicate_elf=False,qualification_seal=QUAL_SEAL,raw_delta=config['raw_delta'],
        scoped_toggle_new=config['scoped_toggle_new'],primary_targets_hit=config['primary_targets_hit'],
        primary_targets_total=config['primary_targets'],whole_ISA_qualified=False,spike_custom_isa_pass=False,
        official_DVE_report=False,official_FSM_Toggle_percentages_pending=True,rtl_changed=False,simulations_started=False))
    life.check(pins);outputpins={str(p):life.digest(p) for p in out.iterdir() if p.is_file()}
    life.save(out/'admission-manifest.json',dict(schema='GAP113_HISTORICAL_RAW_PLUS_SCOPED_TOGGLE_ADMISSION_V1',
        output=str(out),baseline=str(BASE),baseline_seal=BASE_SEAL,qualification=str(QUAL),qualification_seal=QUAL_SEAL,
        prepared_seal=seal,input_pins=pins,output_pins=outputpins,
        authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'))
    return dict(output=str(out),seal=life.digest(out/'admission-manifest.json'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','verify','admit'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--parent-authorized',action='store_true')
    a=p.parse_args();out=a.output.absolute()
    require(out.parent==life.OUT and out.resolve()==out,'Direct independent output')
    require((a.mode!='prepare')==bool(a.seal) and (a.mode=='admit')==a.parent_authorized,'Exact mode/authorization')
    if a.mode=='prepare':print(json.dumps(prepare(out)))
    elif a.mode=='verify':verify(out,a.seal);print('VERIFY_PASS EXACT_PREFIX_PLUS_ONE POSITIVE_SCOPED_TOGGLE NO_ADMISSION')
    else:print(json.dumps(admit(out,a.seal,a.parent_authorized)))
