"""Parent-only792+one admission; full native/scalar replay and fresh raw OR."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import collect_scalar_slot_rotation792 as c
import admit_scalar_misalign792 as prior
import measure_scalar_misalign791 as merge
import targeted_toggle_evidence_v2 as shape
import rank_cva6_scalar_data767 as typed

r,life,require=c.runner,c.life,c.require
BASE,BASE_SHA=r.BASE,r.BASE_SHA
COUNTS=prior.COUNTS
RANK=life.OUT/'conservative-toggle785-static-agent-20261008-01.json'
RANK_SHA='035172c63269024e6e2171426fa8616dedaf6da442f766934806dcb181cdd1d5'


def full_union(before,single):
    require(len(before['tests'])==len(set(before['tests']))==792 and len(single['tests'])==1
        and single['tests'][0] not in before['tests'],'Exact792 distinct singleton')
    require(before['design']==single['design'] and set(before['metrics'])==set(single['metrics'])==set(COUNTS),'Frozen full design')
    after=c.original.shared.bitmap.combine(before,single)
    for metric,count in COUNTS.items():
        require(len(before['metrics'][metric])==count,'Full6162 shape population')
        wanted,_=merge.merge_rows(before['metrics'][metric],single['metrics'][metric])
        require(after['metrics'][metric]==wanted,'Complete exact OR, no dropped scopes')
    require(after['tests']==before['tests']+single['tests'] and len(set(after['tests']))==793,'Exact793 prefix')
    return after


def target_gain(before,sample):
    rank=life.read_bound(RANK,RANK_SHA)
    scope=c.SB; row=next(x for x in rank['ranking'] if x['scope']==scope)
    require(row['checksum']==before[scope]['checksum']==sample[scope]['checksum']=='264082867','Exact scoreboard checksum')
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    authority=life.merge_pins(base['input_pins'],base['output_pins'])
    ledger=BASE/'combined-inputs.txt'
    require(life.digest(ledger)==authority[str(ledger)],'Compiled design ledger binding')
    db=Path(ledger.read_text().splitlines()[0])/'snps/coverage/db'
    paths=[db/rel for rel in ('design/verilog.design.xml','shape/tgl.verilog.info.xml','shape/tgl.verilog.shape.xml')]
    for path in paths:
        require(life.digest(path)==authority[str(path)],'Frozen compiled target shape')
    checks,defs=shape.definitions(*(shape.xml(path) for path in paths),[scope])
    require(checks[scope]==row['checksum'],'Compiled/data scoreboard checksum')
    nodes,_=typed.typed_nodes(defs[scope]['shape'],before[scope])
    fields=[]
    for slot in (2,3,6,7):
        for stem in ('mem_q','mem_n','fwd_o.sbe'):
            name='%s[%d].%s'%(stem,slot,'sbe.ex.tval' if stem.startswith('mem_') else 'ex.tval')
            matches=[o for o in row['objects'] if o['name']==name]
            require(len(matches)==1 and matches[0]['width']==64 and not matches[0]['partial_EL_direction_binding_HOLD'],'Exact full64 target, not partial EL')
            obj=matches[0]
            native=[n for n in nodes if n['name']==name]
            require(len(native)==1 and native[0]['logical_width']==64,'Unique full64 compiled field')
            start=native[0]['serialized_offset']
            coords=list(range(start,start+128))
            require(set(obj['coordinates'])<=set(coords),'Historical missing subset belongs to compiled field')
            require(len(coords)==len(set(coords))==128 and all(type(p) is int and 0<=p<before[scope]['width'] for p in coords),'Exact128 typed direction coordinates')
            old=int(before[scope]['bits'],16); new=int(sample[scope]['bits'],16); width=before[scope]['width']
            fields.append(dict(scope=scope,name=name,checksum=row['checksum'],
                remaining_before=[p for p in coords if not old>>(width-1-p)&1],
                gained=[p for p in coords if new>>(width-1-p)&1 and not old>>(width-1-p)&1]))
    for path in paths:
        require(life.digest(path)==authority[str(path)],'Target shape read-end drift')
    return fields


def evaluate(qual,seal):
    qual=Path(qual).absolute(); q=life.read_bound(qual/'qualification.json',seal)
    r.exact_fields(q,dict(status='SLOT_ROTATION792_FULL_SCALAR_TWELVE_NATIVE_OWNERS_QUALIFIED_NOT_ADMITTED',
        scalar_retirements=1626,scalar_memory_accesses=372,checks=89,native_faults=12,
        vector_status='UNOBSERVABLE_ZERO_DESTINATIONS',full_scalar_differential_qualified=True,
        external_AXI_directly_observed=False,coverage_admitted=False,RTL_changed=False,EDA_launched=False),'Actual complete qualification')
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    require(base['coverage_admitted'] is True and base['output']==str(BASE),'Formal792 exact authority')
    authority=life.merge_pins(base['input_pins'],base['output_pins']); pins=authority
    for more in (q['input_pins'],q['output_pins'],{str(BASE/'admission-manifest.json'):BASE_SHA,str(qual/'qualification.json'):seal,str(RANK):RANK_SHA}):
        pins=life.merge_pins(pins,more)
    paths=[Path(__file__).resolve(),Path(__file__).with_name('test_prepare_scalar_slot_rotation793.py'),Path(prior.__file__),Path(merge.__file__),Path(shape.__file__),Path(typed.__file__)]
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in paths}); life.check(pins)
    def doc(folder,name,map): return life.read_bound(folder/name,map[str(folder/name)])
    status=doc(BASE,'status.json',base['output_pins'])
    require(status['aggregate_passed']==792 and status['coverage_admitted'] is True,'Admitted792 terminal')
    before=doc(BASE,'combined-bits.json',base['output_pins']); bt=doc(BASE,'combined-toggle-bits.json',base['output_pins'])
    ledger=(BASE/'combined-inputs.txt').read_text().splitlines()
    require(ledger==[str(c.original.shared.oracle.inventory.BUILD/'sim/simv.vdb'),*before['tests']]
        and len(ledger)==len(set(ledger))==793,'792 ledger retains real compile VDB first')
    run=Path(q['run']); record=life.read_bound(run/'manifest.json',q['run_seal'])
    require(record['output']==str(run),'Qualified exact run')
    r.verify_prepared(run,record,terminal=True)
    c.original.terminal_gate.__class__(c.original.terminal_gate.__code__,dict(c.original.terminal_gate.__globals__,runner=r))(
        *[doc(run,n,pins) for n in ('simulation-status.json','started.json','live-identity.json')],record)
    pre=life.read_bound(r.PRE/'preflight-manifest.json',r.PRE_SEAL)
    scalar=c.original.spike_trace.compare_commit_prefix(r.PRE/'spike.trace',run/'commit_trace.csv',0x80000000,
        terminal_tohost_address=pre['symbols']['tohost'],rvfi_store_data_layout='unshifted')
    require(scalar==doc(qual,'scalar-comparison.json',q['output_pins']),'Complete scalar differential replay')
    rows=c.original.shared.primitive.parse_rows(run/'commit_trace.csv')
    arch=c.architecture(rows,r.reference(pre),pre['symbols'],r.ELF.read_bytes(),record['expected_traps'])
    require(arch==doc(qual,'architecture-audit.json',q['output_pins']),'Full12 frames/89gold/CSR/guard/memory replay')
    owners=c.wave_audit(qual/'scalar-misalign.vcd',record['expected_traps'],arch['handlers'],rows[-1]['cycle'])
    require(owners==doc(qual,'native-fault-audit.json',q['output_pins']),'All12 allocation/flush/PC/VID/cancellation source closure replay')
    c.original.shared.primitive.zero.vector_zero(run/'vector_trace.csv')
    vector=c.original.vector_commit.compare_vector_commits(r.PRE/'spike.trace',run/'commit_trace.csv',run/'vector_trace.csv',0x80000000)
    c.original.shared.primitive.vector_gate(vector)
    require(vector==doc(qual,'vector-comparison.json',q['output_pins']),'Zero vector schema exact')
    for n in ('run.vcs.log','console.log'): c.original.shared.primitive.log_gate((run/n).read_text())
    vdb=run/'code.vdb'; members={str(p) for p in vdb.rglob('*') if p.is_file()}
    require(members and not any(p.is_symlink() for p in vdb.rglob('*')) and members=={p for p in q['input_pins'] if p.startswith(str(vdb)+'/')},'Whole VDB frozen membership')
    folder=vdb/'snps/coverage/db/testdata'/r.NAME
    require(list(folder.parent.iterdir())==[folder],'Single coverage test')
    native=c.original.shared.coverage.coverage_identity(folder,run,record,Path(ledger[0]))
    require(all(pins.get(p)==h for p,h in native.items()),'All five native metrics execution identity')
    with tempfile.TemporaryDirectory(prefix='slot793-host-') as tmp:
        inputs=Path(tmp)/'inputs.txt'; inputs.write_text(ledger[0]+'\n'+str(vdb)+'\n')
        single=c.original.shared.bitmap.collect(inputs)
    require(single['tests']==[str(vdb)] and all(pins.get(p)==h for p,h in single['input_hashes'].items()),'Actual singleton compile/data pins')
    after=full_union(before,single); delta=c.original.shared.bitmap.delta(before,after)
    st,tgl_sha=c.original.oracle.review.toggle.rows(folder/'tgl.verilog.data.xml',set(bt))
    require(pins.get(str(folder/'tgl.verilog.data.xml'))==tgl_sha,'Exact native Toggle bytes')
    at,tg=merge.merge_rows(bt,st); fields=target_gain(bt,st)
    system='ara_tb.dut.i_ara_soc.i_system'
    gained=sum(v['new_directions'] for s,v in tg.items() if s==system or s.startswith(system+'.'))
    require(sum(delta['metrics'].values())+gained>0,'Actual positive fresh gain required')
    hist=c.rewrite(prior.historical_elf,dict(prior.historical_elf.__globals__,BASE=BASE,runner=r),{791:792,790:791})(base,ledger,authority)
    pins=life.merge_pins(pins,hist['pins']); life.check(pins)
    products={Path(p).name:doc(BASE,Path(p).name,base['output_pins']) for p in base['output_pins']
        if Path(p).parent==BASE and p.endswith('.json') and ('toggle-gain' in Path(p).name or Path(p).name.startswith('retained-'))}
    products.update({'single-bits.json':single,'combined-bits.json':after,'combined-toggle-bits.json':at,'raw-delta.json':delta,
        'slot-rotation-toggle-gain792.json':dict(baseline=792,qualification_seal=seal,scope_gains=tg,target_fields=fields),
        'elf-ledger-dedup.json':hist,'evidence-pins.json':pins,'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',
            aggregate_passed=793,baseline=792,new_passed=1,coverage_admitted=True,exact792_prefix=True,
            duplicate_ELF=False,unique_new_vdb=True,full_OR_metric_instances=6162,raw_delta=delta['metrics'],
            measured_Toggle_directions=gained,measured_target_Toggle_directions=sum(len(f['gained']) for f in fields),
            scalar_retirements=1626,scalar_memory_accesses=372,native_faults=12,software_checks=89,qualification_seal=seal,
            allocation_slots_verified=True,retirement_used_to_infer_slots=False,official_percentage_claimed=False,
            external_AXI_directly_observed=False,RTL_changed=False,new_simulation=False)})
    return products,'\n'.join([ledger[0],*after['tests']])+'\n'


def main():
    p=argparse.ArgumentParser(); p.add_argument('mode',choices=('gain','prepare','verify','admit'))
    p.add_argument('--qualification',required=True,type=Path); p.add_argument('--qualification-seal',required=True)
    p.add_argument('--output',required=True,type=Path); p.add_argument('--seal'); p.add_argument('--parent-authorized',action='store_true'); a=p.parse_args()
    require((a.mode=='admit')==a.parent_authorized and (a.mode in ('verify','admit'))==bool(a.seal),'Separate explicit parent publication authority')
    out=a.output.absolute(); require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Exclusive fresh admission output')
    values,text=evaluate(a.qualification,a.qualification_seal)
    if a.mode=='gain':
        out.mkdir()
        names=('single-bits.json','combined-bits.json','combined-toggle-bits.json','raw-delta.json','slot-rotation-toggle-gain792.json')
        for n in names: life.save(out/n,values[n])
        with (out/'single-inputs.txt').open('x') as f:
            f.write(text.splitlines()[0]+'\n'+values['single-bits.json']['tests'][0]+'\n')
        status=values['status.json']; scopes=values['slot-rotation-toggle-gain792.json']['scope_gains']
        receipt=dict(status='SLOT_ROTATION792_RELATIVE_GAIN_DIAGNOSTIC_NOT_ADMITTED',baseline=792,baseline_seal=BASE_SHA,
            qualification=str(a.qualification.absolute()/'qualification.json'),qualification_seal=a.qualification_seal,
            input_pins=values['evidence-pins.json'],output_pins={str(p):life.digest(p) for p in out.iterdir()},
            full_OR_metric_instances=6162,Toggle_scope_count=len(values['combined-toggle-bits.json']),
            raw_delta=status['raw_delta'],Toggle_all_scopes=sum(v['new_directions'] for v in scopes.values()),
            Toggle_system=status['measured_Toggle_directions'],target_new_directions=status['measured_target_Toggle_directions'],
            target_fields=values['slot-rotation-toggle-gain792.json']['target_fields'],
            actual_serialized_directions_not_official_percentage=True,coverage_admitted=False,EDA_launched=False)
        life.check(receipt['input_pins']); life.save(out/'gain-receipt.json',receipt)
        print(json.dumps(dict(output=str(out),seal=life.digest(out/'gain-receipt.json'),raw_delta=receipt['raw_delta'],
            Toggle_scope_count=receipt['Toggle_scope_count'],Toggle_system=receipt['Toggle_system'],target_new_directions=receipt['target_new_directions'])))
        return
    hashes={str(out/n):hashlib.sha256((json.dumps(v,indent=2)+'\n').encode()).hexdigest() for n,v in values.items()}
    for n in ('combined-inputs.txt','generic-coverage-inputs.txt'): hashes[str(out/n)]=hashlib.sha256(text.encode()).hexdigest()
    proposal=dict(schema='SLOT_ROTATION793_ADMISSION_V1',output=str(out),baseline=str(BASE),baseline_seal=BASE_SHA,
        qualification=str(a.qualification.absolute()/'qualification.json'),qualification_seal=a.qualification_seal,
        input_pins=values['evidence-pins.json'],output_pins=hashes,coverage_admitted=False)
    sidecar=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare': life.save(sidecar,proposal); print('PREPARED_NOT_ADMITTED',life.digest(sidecar)); return
    require(life.read_bound(sidecar,a.seal)==proposal,'Full actual prepared replay equality')
    if a.mode=='verify': print('PREPARED793_VERIFY_PASS_NO_ADMISSION'); return
    out.mkdir()
    for n,v in values.items(): life.save(out/n,v)
    for n in ('combined-inputs.txt','generic-coverage-inputs.txt'):
        with (out/n).open('x') as f: f.write(text)
    life.check(proposal['input_pins']); life.check(hashes)
    life.save(out/'admission-manifest.json',dict(proposal,coverage_admitted=True,prepared=str(sidecar),prepared_seal=a.seal,
        authorization_source='EXPLICIT_PARENT_ADMISSION_AUTHORIZATION_WITHIN_USER_GOAL'))
    print('ADMITTED793',life.digest(out/'admission-manifest.json'))


if __name__=='__main__': main()
