"""Offline formal784 + sealed VALU12; no proposal until real784 exists."""
import argparse
import hashlib
import json
from pathlib import Path
from types import FunctionType

import collect_valu_restart783 as case
import admit_dtlb_permissions782 as inherited

life,require=case.life,case.require
bitmap,toggle=inherited.prior.bitmap,case.toggle
RUN=case.run.OUT
QUAL=life.OUT/'valu-restart783-qualified-agent-20261008-01'
Q_SHA='97f0d2d0b5e2846d83f9e4bc7eb6d042bdc8b3b2d73f91b6f1be7a377c7770fa'
PREPARED_SHA='e12aea6614770fce27f26a27be83c9e185a79cdd765f65c16c88635dd62fa568'
COUNTS=inherited.COUNTS
native_identity=FunctionType(inherited.prior.native_identity.__code__,
    dict(inherited.prior.native_identity.__globals__,RUN=RUN))


def full_union(before,single):
    require(len(before['tests'])==len(set(before['tests']))==784 and
        single['tests']==[str(RUN/'code.vdb')] and single['tests'][0] not in before['tests'],
        'Exact784 prefix and distinct VALU candidate')
    require(set(before['metrics'])==set(single['metrics'])==set(COUNTS),'All four metrics')
    require(all(len(before['metrics'][m])==n for m,n in COUNTS.items()),'All6162 metric instances')
    life.merge_pins(before['input_hashes'],single['input_hashes'])
    after=bitmap.combine(before,single)
    inherited.publish.case.independent_or(before,single,after)
    for rows in after['metrics'].values():
        for row in rows.values():
            require(type(row['width']) is int and row['width']>=0 and
                0<=int(row['bits'],16)<(1<<row['width']),'Exact binary bounds')
    return after


def architecture(q,pre):
    require(q['status']=='VALU_RESTART783_FULL_ARCHITECTURE_QUALIFIED_NOT_ADMITTED' and
        q['coverage_admitted'] is False and q['baseline']==783 and
        q['all_scalar_RVC_memory_checked'] is True,'Sealed full VALU qualification')
    case.shared.scalar_exact(q['scalar'],pre['counts']);case.vector_gate(q['vector'])
    for key,value in dict(software_checks=13144,full_VRF_snapshot_bytes=98304,guard_bytes=3072,
        source_guard_bytes=3200,CSR_words=60,full_scalar_retirements=170167,unknown_defined_bytes_skipped=0).items():
        require(type(q[key]) is int and q[key]==value,'Exact independent obligation '+key)
    require(q['scalar']['matched_scalar_writes']==91688 and q['scalar']['matched_scalar_memory_accesses']==13728
        and q['vector']['compared_instructions']==49 and q['vector']['compared_bytes']==13344,'Full native counts')
    receipts=q['per_instruction_oracles']
    require(len(receipts)==12 and [r['vstart'] for r in receipts]==list(case.gold.STARTS) and
        [r['defined_bytes'] for r in receipts]==[4]*4+[1024]*4+[4]*4 and
        len({r['arch_seq'] for r in receipts})==12,'Twelve exact native byte oracles')
    require(q['lifecycle']==dict(requests=896,responses=896,backend_uops=817) and
        q['protocol']['status']=='EXACT_HANDSHAKE_LASTDRAIN_PASS' and
        q['protocol']['requests']==q['protocol']['responses']==896 and
        q['protocol']['last']['after']==0,'Owned execution and terminal drain')


def rebased_gain(old,added,single,targets):
    before=toggle.union(old,added);after=toggle.union(before,single);result=[]
    require(set(old)==set(added)==set(single)=={t['scope'] for t in targets},'Exact four VALU scopes')
    for scope in before:
        require(before[scope]['checksum']==after[scope]['checksum']=='994898616' and
            before[scope]['width']==after[scope]['width']==5746,'Compiled VALU shape')
    for t in targets:
        b,a=before[t['scope']],after[t['scope']]
        positions=[i for i in t['missing_coordinates'] if
            not(int(b['bits'],16)>>(b['width']-1-i)&1) and int(a['bits'],16)>>(a['width']-1-i)&1]
        result.append(dict(scope=t['scope'],name=t['name'],new_serialized_positions=positions))
    gains=toggle.gains(before,after)
    return dict(baseline=784,before=before,single=single,after=after,targets=result,
        actual_new_target_coordinates=sum(len(t['new_serialized_positions']) for t in result),
        scoped_new_coordinates=sum(map(len,gains.values())),scoped_raw_gain=gains,
        original783_target_gain_not_recounted=True,official_percentage=False)


def ledger_gate(ledger,before,status,parent_ledger):
    require(len(ledger)==len(set(ledger))==785 and ledger==[str(life.IMAGE)+'.vdb',*before['tests']]
        and ledger[:-1]==parent_ledger and status['aggregate_passed']==784 and
        status['coverage_admitted'] is True,'Real784 exact783 prefix and sealed status')


def evaluate(base,base_sha):
    manifest=life.read_bound(base/'admission-manifest.json',base_sha)
    require(manifest['coverage_admitted'] is True and manifest['output']==str(base) and
        manifest['baseline']==str(case.gold.BASE) and manifest['baseline_seal']==case.gold.BASE_SHA,
        'Formal784 must inherit actual783, not a duplicate783 branch')
    authority=life.merge_pins(manifest['input_pins'],manifest['output_pins'])
    q=life.read_bound(QUAL/'qualification.json',Q_SHA);life.check(q['pins'])
    pins=life.merge_pins(authority,q['pins'])
    def previous(name):return life.read_bound(base/name,manifest['output_pins'][str(base/name)])
    before=previous('combined-bits.json');status=previous('status.json')
    ledger=(base/'combined-inputs.txt').read_text().splitlines()
    parent=life.read_bound(case.gold.BASE/'admission-manifest.json',case.gold.BASE_SHA)
    parent_ledger=case.gold.BASE/'combined-inputs.txt'
    require(life.digest(parent_ledger)==parent['output_pins'][str(parent_ledger)],'Original783 ledger pin')
    ledger_gate(ledger,before,status,parent_ledger.read_text().splitlines())
    prepared=RUN.with_name(RUN.name+'.prepared.json');record=case.run.check(prepared,PREPARED_SHA)
    require(life.read_bound(RUN/'manifest.json',pins[str(RUN/'manifest.json')])==
        dict(record,pins=life.merge_pins(record['pins'],{str(prepared):PREPARED_SHA})),'Actual prepared run identity')
    case.terminal(life.read_bound(RUN/'simulation-status.json',pins[str(RUN/'simulation-status.json')]))
    architecture(q,record['preflight'])
    db=RUN/'code.vdb';members=sorted(p for p in db.rglob('*') if p.is_file())
    require(not any(p.is_symlink() for p in db.rglob('*')) and {str(p) for p in members}==
        {p for p in q['pins'] if p.startswith(str(db)+'/')},'Exact immutable native VDB membership')
    native=db/'snps/coverage/db/testdata'/case.run.CASE
    require(list(native.parent.iterdir())==[native],'One native test owner')
    identity=native_identity(toggle.xml(native/'siminfo.xml'),toggle.xml(native/'vcmArguments.xml'),record,ledger[0])
    design=Path(ledger[0])/'snps/coverage/db'
    require(all(life.digest(design/rel)==h==pins[str(design/rel)] for rel,h in before['design'].items()),
        'Frozen compatible full design fingerprints')
    single=dict(design=before['design'],tests=[str(db)],input_hashes={},metrics={})
    for metric in bitmap.METRICS:
        p=native/(metric+'.verilog.data.xml');require(pins[str(p)]==life.digest(p),'Native metric pin')
        single['metrics'][metric]=bitmap.read_metric(p);single['input_hashes'][str(p)]=pins[str(p)]
    after=full_union(before,single);delta=bitmap.delta(before,after)
    binding,binding_pins=case.gold.binding783();require(binding==record['preflight']['baseline'],'Bound45 targets')
    review=life.read_bound(case.gold.REVIEW,case.gold.REVIEW_SHA)
    inventory=life.read_bound(Path(review['inventory']),review['inventory_sha256'])
    scopes=sorted({t['scope'] for t in binding['targets']})
    old={s['scope']:s['row'] for s in inventory['scopes'] if s['scope'] in scopes}
    def sample(vdb,evidence):
        files=list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files)==1,'One actual Toggle sample')
        rows,h=toggle.rows(files[0],scopes);require(evidence.get(str(files[0]))==h,'Bound native Toggle sample')
        return rows
    old=toggle.union(old,sample(binding['appended_vdb'],binding_pins))
    gain=rebased_gain(old,sample(ledger[-1],authority),sample(str(db),q['pins']),binding['targets'])
    require(gain['scoped_new_coordinates']>0,'No positive rebased VALU gain: HOLD, never recount422')
    elf=inherited.prior.dedup(ledger,record['ELF_sha256'],authority)
    require(elf['ledger_members']==784 and elf['duplicate'] is False and
        [r['vdb'] for r in elf['members']]==ledger[1:] and
        all(authority.get(p)==h for p,h in elf['pins'].items()),'Historical-only784 ELF dedup authority')
    pins=life.merge_pins(pins,binding_pins);pins=life.merge_pins(pins,elf['pins'])
    fixed={str(base/'admission-manifest.json'):base_sha,str(QUAL/'qualification.json'):Q_SHA,
        str(parent_ledger):parent['output_pins'][str(parent_ledger)]}
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_valu_restart785.py'),
        Path(inherited.__file__),Path(inherited.prior.__file__),Path(inherited.publish.__file__),
        Path(inherited.publish.case.__file__),Path(inherited.prior.dedup.__code__.co_filename)):
        fixed[str(p.resolve())]=life.digest(p)
    pins=life.merge_pins(pins,fixed);life.check(pins)
    products={Path(p).name:previous(Path(p).name) for p in manifest['output_pins']
        if Path(p).parent==base and Path(p).suffix=='.json' and
        ('toggle-gain' in Path(p).name or Path(p).name.startswith('retained-'))}
    products.update({'single-bits.json':single,'combined-bits.json':after,'raw-delta.json':delta,
        'valu-restart-toggle-gain784.json':gain,'native-vdb-identity.json':identity,
        'elf-ledger-dedup.json':dict(elf,baseline=784),'evidence-pins.json':pins,
        'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',baseline=784,aggregate_passed=785,
            new_passed=1,coverage_admitted=True,exact784_prefix=True,full_OR_metric_instances=6162,
            unique_new_vdb=True,duplicate_ELF=False,full_scalar_ISA=True,full_vector_verified=True,
            scalar_retired=170167,checks=13144,full_VRF_snapshot_bytes=98304,
            actual_target_gain=gain['actual_new_target_coordinates'],raw_delta=delta['metrics'],
            qualification_seal=Q_SHA,new_simulation=False,RTL_changed=False,official_percentage_claimed=False)})
    return products,'\n'.join([ledger[0],*after['tests']])+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','verify','admit'))
    p.add_argument('--baseline',type=Path,required=True);p.add_argument('--baseline-seal',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--parent-authorized',action='store_true')
    a=p.parse_args();base=a.baseline.resolve();out=a.output.resolve()
    require(a.parent_authorized==(a.mode=='admit') and bool(a.seal)==(a.mode!='prepare'),'Explicit reviewed admission only')
    require(out.parent==life.OUT and not out.exists(),'Fresh785 output')
    products,text=evaluate(base,a.baseline_seal)
    hashes={str(out/n):hashlib.sha256((json.dumps(v,indent=2)+'\n').encode()).hexdigest() for n,v in products.items()}
    for name in ('combined-inputs.txt','generic-coverage-inputs.txt'):hashes[str(out/name)]=hashlib.sha256(text.encode()).hexdigest()
    proposal=dict(output=str(out),baseline=str(base),baseline_seal=a.baseline_seal,
        qualification=str(QUAL/'qualification.json'),qualification_seal=Q_SHA,
        input_pins=products['evidence-pins.json'],output_pins=hashes,coverage_admitted=False)
    prepared=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':
        require(not prepared.exists(),'Preserve any prior proposal');life.save(prepared,proposal)
        print('PREPARED785_NOT_ADMITTED',life.digest(prepared));return
    require(life.read_bound(prepared,a.seal)==proposal,'Exact prepared785 equality')
    if a.mode=='verify':print('VERIFY_PASS_NO_ADMISSION');return
    out.mkdir()
    for name,value in products.items():life.save(out/name,value)
    for name in ('combined-inputs.txt','generic-coverage-inputs.txt'):
        with (out/name).open('x') as stream:stream.write(text)
    life.check(proposal['input_pins']);life.check(hashes)
    life.save(out/'admission-manifest.json',dict(proposal,coverage_admitted=True,
        prepared=str(prepared),prepared_seal=a.seal,authorization_source='PARENT_EXPLICIT_AUTHORIZATION'))
    print('ADMITTED785',life.digest(out/'admission-manifest.json'))


if __name__=='__main__':main()
