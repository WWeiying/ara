"""Strict791 + one qualified scalar misalign case; parent-only publication."""
import argparse
import hashlib
import json
from pathlib import Path

import measure_scalar_misalign791 as gain

a, c = gain.adapter, gain.c
life, require, runner = c.life, c.require, c.runner
BASE, BASE_SHA = gain.BASE, gain.BASE_SHA
QUAL, CORE_SHA, CLOSURE_SHA = gain.QUAL, gain.CORE_SHA, gain.CLOSURE_SHA
GAIN = life.OUT/'scalar-misalign-gain791-agent-20261008-01'
GAIN_SHA = 'f2de96c61684916121d6c550cd77e4d18bb92ee3e30bd09a9442517293bd8ccc'
COUNTS = dict(line=1892,cond=2023,branch=2155,fsm=92)


def joint_gate(core, closure):
    runner.exact_fields(core,dict(status='SCALAR_MISALIGN789_FULL_SCALAR_SIX_NATIVE_FAULTS_QUALIFIED_NOT_ADMITTED',
        scalar_retirements=866,scalar_memory_accesses=226,checks=56,native_faults=6,
        vector_status='UNOBSERVABLE_ZERO_DESTINATIONS',full_scalar_differential_qualified=True,
        external_AXI_directly_observed=False,coverage_admitted=False,RTL_changed=False,EDA_launched=False),
        'Complete core functional authority')
    runner.exact_fields(closure,dict(status='SCALAR_MISALIGN789_SOC_WIDTH_OFFLINE_CLOSURE_NOT_ADMITTED',
        core_qualification=str(QUAL/'qualification.json'),core_sha256=CORE_SHA,
        original_HOLD_preserved=True,VCS_rerun=False,coverage_admitted=False),'Mandatory exact SoC closure')
    require(closure['output_pins']=={str(QUAL/'qualification.json'):CORE_SHA}
        and closure['input_pins']==closure['source_proof']['pins'], 'Closure pin relationship')
    for path in (Path(a.__file__).resolve(),Path(a.__file__).with_name('test_scalar_misalign789_soc_width_adapter.py')):
        require(closure['input_pins'].get(str(path))==life.digest(path),'Finalized adapter/test identity')
    expected=a.source_proof()
    require(all(closure['source_proof'].get(k)==v for k,v in expected.items() if k!='pins')
        and all(closure['input_pins'].get(p)==h for p,h in expected['pins'].items()),'Full source-derived SoC/slot0 closure replay')


def full_union(before,single):
    require(len(before['tests'])==len(set(before['tests']))==791
        and len(single['tests'])==1 and single['tests'][0] not in before['tests'], 'Exact791 distinct append')
    require(before['design']==single['design'] and set(before['metrics'])==set(single['metrics'])==set(COUNTS), 'Frozen four-metric design')
    after=c.shared.bitmap.combine(before,single)
    for metric,count in COUNTS.items():
        require(len(before['metrics'][metric])==count,'Full metric scope count')
        wanted,_=gain.merge_rows(before['metrics'][metric],single['metrics'][metric])
        require(after['metrics'][metric]==wanted,'Full6162 exact bounded OR')
    require(after['tests']==before['tests']+single['tests'] and len(set(after['tests']))==792,'Exact792 prefix')
    return after


def historical_elf(base,ledger,authority):
    path=BASE/'elf-ledger-dedup.json';audit=life.read_bound(path,base['output_pins'][str(path)])
    require(type(audit['ledger_members']) is int and audit['ledger_members']==790
        and audit['duplicate'] is False and [r['vdb'] for r in audit['members']]==ledger[1:791], 'Closed historical790 ELF ownership')
    members=audit['members'][:]
    for row in members:
        require(row['ELF_candidates'],'Missing old ELF owner')
        for p,h in row['ELF_candidates'].items():require(authority.get(p)==h and h!=runner.ELF_SHA,'Historical duplicate ELF/identity drift')
    command_path=Path(ledger[-1]).parent/'manifest.json'
    command=life.read_bound(command_path,authority[str(command_path)])['command']
    elf=[s.split('=',1)[1] for s in command if s.startswith('+PRELOAD=')]
    require(len(elf)==1 and elf[0] in authority and authority[elf[0]]!=runner.ELF_SHA,'Exact latest791 ELF command/duplicate')
    members.append(dict(vdb=ledger[-1],ELF_candidates={elf[0]:authority[elf[0]]},command_sources=[str(command_path)]))
    return dict(ledger_members=791,members=members,duplicate=False,new_ELF_sha256=runner.ELF_SHA,
        historical_authority_only=True,pins={str(path):base['output_pins'][str(path)],str(command_path):authority[str(command_path)],elf[0]:authority[elf[0]]})


def evaluate():
    q=life.read_bound(QUAL/'qualification.json',CORE_SHA)
    closure=life.read_bound(QUAL/'soc-width-closure.json',CLOSURE_SHA);joint_gate(q,closure)
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    receipt=life.read_bound(GAIN/'gain-receipt.json',GAIN_SHA)
    runner.exact_fields(receipt,dict(status='SCALAR_MISALIGN_791_RELATIVE_GAIN_DIAGNOSTIC_NOT_ADMITTED',baseline=791,
        baseline_seal=BASE_SHA,core_sha256=CORE_SHA,closure_sha256=CLOSURE_SHA,coverage_admitted=False,EDA_launched=False),'Exact fresh791 gain authority')
    require(base['coverage_admitted'] is True and base['output']==str(BASE),'Formal791 exact directory')
    authority=life.merge_pins(base['input_pins'],base['output_pins']);pins=authority
    for more in (q['input_pins'],q['output_pins'],closure['input_pins'],closure['output_pins'],receipt['input_pins'],receipt['output_pins'],
        {str(BASE/'admission-manifest.json'):BASE_SHA,str(QUAL/'qualification.json'):CORE_SHA,
         str(QUAL/'soc-width-closure.json'):CLOSURE_SHA,str(GAIN/'gain-receipt.json'):GAIN_SHA}):pins=life.merge_pins(pins,more)
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_scalar_misalign792.py')):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins)
    def doc(folder,name,map):return life.read_bound(folder/name,map[str(folder/name)])
    status=doc(BASE,'status.json',base['output_pins'])
    require(type(status['aggregate_passed']) is int and status['aggregate_passed']==791 and status['coverage_admitted'] is True,'Formal791 terminal')
    before=doc(BASE,'combined-bits.json',base['output_pins']);bt=doc(BASE,'combined-toggle-bits.json',base['output_pins'])
    ledger=(BASE/'combined-inputs.txt').read_text().splitlines()
    require(ledger==[str(c.shared.oracle.inventory.BUILD/'sim/simv.vdb'),*before['tests']] and len(ledger)==len(set(ledger))==792,'Complete791 input ledger')
    run=Path(q['run']);record=life.read_bound(run/'manifest.json',q['run_seal'])
    require(run==Path(record['output']) and record['input_elf']==str(runner.ELF),'Exact qualified run')
    runner.verify_prepared(run,record,terminal=True)
    c.terminal_gate(*[doc(run,n,pins) for n in ('simulation-status.json','started.json','live-identity.json')],record)
    pre=life.read_bound(runner.PRE/'preflight-manifest.json',runner.PRE_SEAL)
    scalar=c.spike_trace.compare_commit_prefix(runner.PRE/'spike.trace',run/'commit_trace.csv',0x80000000,
        terminal_tohost_address=pre['symbols']['tohost'],rvfi_store_data_layout='unshifted')
    require(scalar==doc(QUAL,'scalar-comparison.json',q['output_pins']),'Complete scalar replay differs')
    rows=c.shared.primitive.parse_rows(run/'commit_trace.csv')
    arch=c.architecture(rows,runner.reference(pre),pre['symbols'],runner.ELF.read_bytes(),record['expected_traps'])
    require(arch==doc(QUAL,'architecture-audit.json',q['output_pins']),'Gold/traps/guards/all memory replay differs')
    owners=a.wave_audit(QUAL/'scalar-misalign.vcd',record['expected_traps'],arch['handlers'],rows[-1]['cycle'])
    require(owners==doc(QUAL,'native-fault-audit.json',q['output_pins']),'Six native owners/cancellation replay differs')
    c.shared.primitive.zero.vector_zero(run/'vector_trace.csv')
    vector=c.vector_commit.compare_vector_commits(runner.PRE/'spike.trace',run/'commit_trace.csv',run/'vector_trace.csv',0x80000000)
    c.shared.primitive.vector_gate(vector)
    require(vector==doc(QUAL,'vector-comparison.json',q['output_pins']),'Zero-vector schema replay differs')
    for n in ('run.vcs.log','console.log'):c.shared.primitive.log_gate((run/n).read_text())
    vdb=run/'code.vdb';members={str(p) for p in vdb.rglob('*') if p.is_file()}
    require(members and not any(p.is_symlink() for p in vdb.rglob('*'))
        and members=={p for p in q['input_pins'] if p.startswith(str(vdb)+'/')},'Whole VDB membership')
    folder=vdb/'snps/coverage/db/testdata'/runner.NAME
    require(list(folder.parent.iterdir())==[folder],'Single native coverage test')
    native=c.shared.coverage.coverage_identity(folder,run,record,Path(ledger[0]))
    require(all(pins.get(p)==h for p,h in native.items()),'Five-metric executed identity')
    single=doc(GAIN,'single-bits.json',receipt['output_pins'])
    require(single['tests']==[str(vdb)] and (GAIN/'single-inputs.txt').read_text().splitlines()==[ledger[0],str(vdb)],'Exact singleton')
    for metric in COUNTS:require(single['metrics'][metric]==c.shared.bitmap.read_metric(folder/(metric+'.verilog.data.xml')),'Raw metric byte replay')
    after=full_union(before,single);delta=c.shared.bitmap.delta(before,after)
    require(after==doc(GAIN,'combined-bits.json',receipt['output_pins']) and delta==doc(GAIN,'raw-delta.json',receipt['output_pins'])
        and receipt['four_metrics']==delta['metrics'],'Fresh complete four-metric OR differs')
    st,sha=c.oracle.review.toggle.rows(folder/'tgl.verilog.data.xml',set(bt))
    require(pins.get(str(folder/'tgl.verilog.data.xml'))==sha,'Actual Toggle bytes')
    at,tg=gain.merge_rows(bt,st)
    require(at==doc(GAIN,'combined-toggle-bits.json',receipt['output_pins']) and tg==receipt['Toggle_scope_gains']
        and sum(v['new_directions'] for v in tg.values())==receipt['Toggle_all_scopes'],'Complete Toggle OR/difference replay')
    require(sum(delta['metrics'].values())+receipt['Toggle_system']>0,'Zero gain rejected')
    dedup=historical_elf(base,ledger,authority);pins=life.merge_pins(pins,dedup['pins']);life.check(pins)
    products={Path(p).name:life.read_bound(Path(p),h) for p,h in base['output_pins'].items()
        if Path(p).parent==BASE and p.endswith('.json') and ('toggle-gain' in Path(p).name or Path(p).name.startswith('retained-'))}
    products.update({'single-bits.json':single,'combined-bits.json':after,'combined-toggle-bits.json':at,'raw-delta.json':delta,
        'scalar-misalign-toggle-gain791.json':dict(baseline=791,scope_gains=tg,target_fields=doc(GAIN,'typed-target-gain791.json',receipt['output_pins'])),
        'elf-ledger-dedup.json':dedup,'evidence-pins.json':pins,'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',
            aggregate_passed=792,baseline=791,new_passed=1,coverage_admitted=True,exact791_prefix=True,
            duplicate_ELF=False,unique_new_vdb=True,full_OR_metric_instances=6162,raw_delta=delta['metrics'],
            measured_Toggle_directions=receipt['Toggle_system'],measured_target_Toggle_directions=receipt['target_new_directions'],
            scalar_retirements=866,scalar_memory_accesses=226,native_faults=6,software_checks=56,
            vector_status='UNOBSERVABLE_ZERO_DESTINATIONS',qualification_seal=CORE_SHA,soc_closure_seal=CLOSURE_SHA,
            external_AXI_directly_observed=False,official_percentage_claimed=False,RTL_changed=False,new_simulation=False)})
    return products,'\n'.join([ledger[0],*after['tests']])+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','verify','admit'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--parent-authorized',action='store_true');args=p.parse_args()
    require((args.mode=='admit')==args.parent_authorized and (args.mode!='prepare')==bool(args.seal),'Explicit parent publication and seal')
    out=args.output.absolute();require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh admission output')
    values,text=evaluate()
    hashes={str(out/n):hashlib.sha256((json.dumps(v,indent=2)+'\n').encode()).hexdigest() for n,v in values.items()}
    for n in ('combined-inputs.txt','generic-coverage-inputs.txt'):hashes[str(out/n)]=hashlib.sha256(text.encode()).hexdigest()
    proposal=dict(schema='SCALAR_MISALIGN_HISTORICAL792_JOINT_SOC_ADMISSION_V1',output=str(out),baseline=str(BASE),baseline_seal=BASE_SHA,
        qualification=str(QUAL/'qualification.json'),qualification_seal=CORE_SHA,soc_closure=str(QUAL/'soc-width-closure.json'),soc_closure_seal=CLOSURE_SHA,
        input_pins=values['evidence-pins.json'],output_pins=hashes,coverage_admitted=False)
    sidecar=out.with_name(out.name+'.prepared.json')
    if args.mode=='prepare':life.save(sidecar,proposal);print('PREPARED_NOT_ADMITTED',life.digest(sidecar));return
    require(life.read_bound(sidecar,args.seal)==proposal,'Prepared admission drift')
    if args.mode=='verify':print('PREPARED792_VERIFY_PASS_NO_ADMISSION');return
    out.mkdir()
    for n,v in values.items():life.save(out/n,v)
    for n in ('combined-inputs.txt','generic-coverage-inputs.txt'):
        with (out/n).open('x') as f:f.write(text)
    life.check(proposal['input_pins']);life.check(hashes)
    life.save(out/'admission-manifest.json',dict(proposal,coverage_admitted=True,prepared=str(sidecar),prepared_seal=args.seal,
        authorization_source='EXPLICIT_PARENT_ADMISSION_AUTHORIZATION'))
    print('ADMITTED792',life.digest(out/'admission-manifest.json'))


if __name__=='__main__':main()
