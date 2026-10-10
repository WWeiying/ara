"""Parent-authorized795 plus one native alias case, exact OR and dual seals."""
import argparse
import hashlib
import json
from pathlib import Path

import collect_akv_canonical_alias794_sd_v2 as successor
import run_akv_canonical_alias794 as runner
import admit_itlb_ppn_aba794 as union
import admit_itlb_ppn_aba794_v2 as toggle_union

c=successor.original
life,require=c.life,c.require
BASE=life.OUT/'scalar-div-subnormal-offline-admitted795-parent-20261008-01'
BASE_SHA='4d13a15758c65791a43798467bb63c516d0747d631f6fede476eb63202001660'
QUAL=life.OUT/'akv-canonical-alias794-qualified-sd-v2-parent-20261008-01'
Q_SHA='bb545552788a04cdabc841f7b6b8550679e7084f49d89e5bfb59f426afec5d9b'
RECEIPT_SHA='8404d026f11a631e83e836a3295f28974749da41ef9f1d37dbffd0d73a064134'
RUN=life.OUT/'akv-canonical-alias794-old-image-parent-20261008-01'
RUN_SHA='f777d171de39027b9d0b7fdd4b7fd88f2c3ad5438a27e9f79eb9cbcde0c62de1'
SD_SHA='bd333f91cf896375409fb356d218dfe4d6c0f059cab54424fa96cade8d79ee5c'
SD_TEST_SHA='11383229b91c9e2c892cae7f38ca25b1eb42200997aeda91529581dc4b22f493'
DIAG_SHA='4a6ffca2c9ad192856300a797664d47ecd45075ac74cc40a12cc1fd1e4f2d418'


def qualification(q,receipt):
    require(q['status']=='AKV_CANONICAL_ALIAS_NATIVE_INDEPENDENT_QUALIFIED_NOT_ADMITTED'
        and q['baseline_tests']==794 and type(q['scalar_model_skips']) is int and q['scalar_model_skips']==0
        and q['native_custom_Spike'] is False and q['coverage_admitted'] is False
        and q['oraclekind']=='BOUNDED_NATIVE_ISA_CUSTOM_INTEGER_BYTE_MODEL_NOT_CUSTOM_SPIKE','Exact complete native core qualification')
    require(receipt['status']=='EXACT_SD_DERIVATION_SUCCESSOR_ALL_ORIGINAL_GATES_QUALIFIED'
        and receipt['core_qualification']==str(QUAL/'qualification.json') and receipt['core_sha256']==Q_SHA
        and receipt['scope']=='Derived SD after scoped CSR writes; two exact scalar S-ecall trap retirements and immediate handler'
        and receipt['fields_masked']==[] and type(receipt['skipped_retirements']) is int and receipt['skipped_retirements']==0
        and receipt['native_custom_Spike'] is False and receipt['coverage_admitted'] is False
        and receipt['original_checker_sha256']==successor.OLD_SHA,'Exact SD and ECALL successor receipt')
    required=successor.source()
    required[str(Path(successor.__file__).resolve())]=SD_SHA
    required[str(Path(successor.__file__).with_name('test_akv_canonical_alias794_sd_v2.py').resolve())]=SD_TEST_SHA
    require(all(receipt['successor_pins'].get(p)==h for p,h in required.items()),'Successor source/test proof pins')
    require(receipt['diagnosis_sha256']==DIAG_SHA and receipt['successor_pins'].get(receipt['diagnosis'])==DIAG_SHA,
        'Original failure diagnosis binding')
    wanted=life.merge_pins(life.merge_pins(q['input_pins'],q['output_pins']),receipt['successor_pins'])
    require(receipt['input_pins']==wanted,'Complete receipt/core/input/output pin closure')
    require(q['input_pins'].get(str(RUN/'manifest.json'))==RUN_SHA,'Qualified actual native run')


def full_union(before,single):
    require(len(before['tests'])==len(set(before['tests']))==795,'Exact unique795 population')
    after=union.full_union(before,single,RUN/'code.vdb')
    require(after['tests']==before['tests']+[str(RUN/'code.vdb')] and len(set(after['tests']))==796,'Exact796 prefix and singleton')
    return after


def historical(base,ledger,authority,newhash):
    p=BASE/'elf-ledger-dedup.json';old=life.read_bound(p,base['output_pins'][str(p)])
    require(old['ledger_members']==794 and len(old['members'])==794 and old['duplicate'] is False
        and [r['vdb'] for r in old['members']]==ledger[1:-1],'Sealed794 historical ELF prefix')
    for member in old['members']:
        require(member['ELF_candidates'] and all(authority.get(p)==h and h!=newhash
            for p,h in member['ELF_candidates'].items()),'Historical ELF duplicate or authority drift')
    command_path=Path(ledger[-1]).parent/'manifest.json'
    record=life.read_bound(command_path,authority[str(command_path)])
    elves=[s.split('=',1)[1] for s in record['command'] if s.startswith('+PRELOAD=')]
    require(len(elves)==1 and elves[0] in authority and record['pins'].get(elves[0])==authority[elves[0]]!=newhash,
        'Actual795 suffix command ELF dedup')
    member=dict(vdb=ledger[-1],ELF_candidates={elves[0]:authority[elves[0]]},command_sources=[str(command_path)])
    return dict(baseline=795,ledger_members=795,members=old['members']+[member],duplicate=False,new_ELF_sha256=newhash,
        pins={str(p):base['output_pins'][str(p)],str(command_path):authority[str(command_path)],elves[0]:authority[elves[0]]})


def target_gain(before,after,targets):
    fields=[];seen=set()
    require(len(targets['fields'])==13,'Complete thirteen compiled address fields')
    for f in targets['fields']:
        key=(f['scope'],f['name']);require(key not in seen,'Duplicate target field');seen.add(key)
        b,a=before[f['scope']],after[f['scope']]
        require(b['checksum']==a['checksum']==f['checksum'] and b['width']==a['width'],'Exact typed target identity')
        coords=f['full_coordinates'];require(coords==list(range(f['offset'],f['offset']+128))
            and f['width']==64 and all(0<=p<b['width'] for p in coords),'Full128 compiled direction coordinates')
        fresh=int(a['bits'],16)&~int(b['bits'],16)
        fields.append(dict(scope=f['scope'],name=f['name'],checksum=f['checksum'],full_coordinates=coords,
            remaining_before=[p for p in coords if not int(b['bits'],16)>>(b['width']-1-p)&1],
            gained=[p for p in coords if fresh>>(b['width']-1-p)&1]))
    return fields


def positive(delta,gains):
    require(sum(delta['metrics'].values())+sum(map(len,gains.values()))>0,'Positive latest795 gain required')


def evaluate():
    q=life.read_bound(QUAL/'qualification.json',Q_SHA)
    receipt=life.read_bound(QUAL/'sd-successor-receipt.json',RECEIPT_SHA);qualification(q,receipt)
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    require(base['coverage_admitted'] is True and base['output']==str(BASE),'Exact admitted795 authority')
    authority=life.merge_pins(base['input_pins'],base['output_pins'])
    pins=life.merge_pins(authority,receipt['input_pins'])
    pins=life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SHA,str(QUAL/'qualification.json'):Q_SHA,
        str(QUAL/'sd-successor-receipt.json'):RECEIPT_SHA})
    files=(Path(__file__).resolve(),Path(__file__).with_name('test_admit_akv_canonical_alias796.py'),
        Path(union.__file__).resolve(),Path(toggle_union.__file__).resolve())
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in files});life.check(pins)
    def doc(folder,name,map):return life.read_bound(folder/name,map[str(folder/name)])
    status=doc(BASE,'status.json',base['output_pins'])
    require(type(status['aggregate_passed']) is int and status['aggregate_passed']==795 and status['coverage_admitted'] is True,'Formal795 terminal PASS')
    before=doc(BASE,'combined-bits.json',base['output_pins']);bt=doc(BASE,'combined-toggle-bits.json',base['output_pins'])
    ledger=(BASE/'combined-inputs.txt').read_text().splitlines()
    require(ledger==[str(life.IMAGE)+'.vdb',*before['tests']] and len(ledger)==len(set(ledger))==796,'Actual795 complete compile-first ledger')
    m=runner.verify(RUN,RUN_SHA)
    c.terminal(doc(RUN,'simulation-status.json',pins),doc(RUN,'started.json',pins),m,RUN,runner.ELF)
    rows=c.old.isa.base.native.commit_rows(RUN/'commit_trace.csv')
    model,scalar=successor.replay(runner.ELF.read_bytes(),m['preflight']['symbols'],rows)
    require(scalar==doc(QUAL,'scalar.json',q['output_pins']),'Full116614 native scalar/CSR/memory zero-skip replay')
    arch=c.lifecycle(rows,model);require(arch==doc(QUAL,'lifecycle.json',q['output_pins']),'All ten native PC/type/backend owners')
    vector=c.vectors(c.old.isa.base.native.common.read_csv(RUN/'vector_trace.csv',c.old.isa.base.native.common.VECTOR_FIELDS),model,arch)
    require(vector==doc(QUAL,'vector.json',q['output_pins']),'Full4096 seed/768 custom/16384 snapshots oracle')
    require(c.native_wave(QUAL/'akv-alias.vcd',model.symbols,arch)==doc(QUAL,'native-capture.json',q['output_pins']), 'Accepted VA/PA/AR and command owners')
    log=(RUN/'run.vcs.log').read_text()
    require(c.perf(log,arch)==doc(QUAL,'perf.json',q['output_pins']) and c.contract(log,arch['requests'])==
        doc(QUAL,'contract.json',q['output_pins']),'Exact native PERF/strict conservation replay')
    vdb=RUN/'code.vdb';members={str(p) for p in vdb.rglob('*') if p.is_file()}
    require(members and members=={p for p in q['input_pins'] if p.startswith(str(vdb)+'/')}
        and not any(p.is_symlink() for p in vdb.rglob('*')),'Complete frozen VDB membership')
    folder=vdb/'snps/coverage/db/testdata'/runner.NAME
    require(list(folder.parent.iterdir())==[folder],'Exactly one candidate native test')
    identity=c.native_identity(c.case.static.shape.xml(folder/'siminfo.xml'),c.case.static.shape.xml(folder/'vcmArguments.xml'),RUN,m['command'],ledger[0])
    require(identity==doc(QUAL,'native-vdb-identity.json',q['output_pins']),'Native five-metric compile/command/cwd/completion binding')
    single=doc(QUAL,'single-bits.json',q['output_pins'])
    for rel,h in single['design'].items():
        p=Path(ledger[0])/'snps/coverage/db'/rel
        require(authority.get(str(p))==h==life.digest(p),'Real compile VDB design/shape authority')
    for metric in union.COUNTS:
        p=folder/(metric+'.verilog.data.xml')
        require(single['metrics'][metric]==c.old.bitmap.read_metric(p) and single['input_hashes'].get(str(p))==pins[str(p)], 'Actual singleton metric bytes')
    after=full_union(before,single);delta=c.old.bitmap.delta(before,after)
    st,h=c.case.old.toggle.rows(folder/'tgl.verilog.data.xml',list(bt))
    require(h==pins[str(folder/'tgl.verilog.data.xml')] and st==doc(QUAL,'single-toggle-bits.json',q['output_pins']),'Native2989 Toggle singleton')
    at=c.case.old.toggle.union(bt,st);toggle_union.all_toggle_or(bt,st,at);gains=c.case.old.toggle.gains(bt,at)
    fields=target_gain(bt,at,m['targets']);positive(delta,gains)
    hist=historical(base,ledger,authority,pins[str(runner.ELF)]);pins=life.merge_pins(pins,hist['pins']);life.check(pins)
    products={Path(p).name:life.read_bound(Path(p),h) for p,h in base['output_pins'].items()
        if Path(p).parent==BASE and p.endswith('.json') and ('toggle-gain' in Path(p).name or Path(p).name.startswith('retained-'))}
    products.update({'single-bits.json':single,'combined-bits.json':after,'combined-toggle-bits.json':at,'raw-delta.json':delta,
        'alias-toggle-gain795.json':dict(baseline=795,baseline_seal=BASE_SHA,scope_gains=gains,target_fields=fields,
            system_new_directions=sum(map(len,gains.values())),target_new_directions=sum(len(f['gained']) for f in fields),
            qualification_seal=Q_SHA,successor_receipt_seal=RECEIPT_SHA,official_percentage_claimed=False),
        'elf-ledger-dedup.json':hist,'evidence-pins.json':pins,'native-vdb-identity.json':identity,
        'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',aggregate_passed=796,baseline=795,new_passed=1,
            coverage_admitted=True,exact795_prefix=True,unique_new_vdb=True,duplicate_ELF=False,
            full_OR_metric_instances=6162,full_OR_Toggle_instances=2989,raw_delta=delta['metrics'],
            measured_Toggle_positions=sum(map(len,gains.values())),target_Toggle_positions=sum(len(f['gained']) for f in fields),
            checks=4247,scalar_retirements=116614,scalar_model_skips=0,custom_commands=10,precise_S_ecalls=2,
            full_VRF_frames=4,actual_MMU_accepted_translations=8,native_custom_Spike=False,
            oraclekind=scalar['oraclekind'],qualification_seal=Q_SHA,successor_receipt_seal=RECEIPT_SHA,
            official_percentage_claimed=False,RTL_changed=False,new_simulation=False)})
    return products,'\n'.join([ledger[0],*after['tests']])+'\n'


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','verify','admit'));p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seal');p.add_argument('--parent-authorized',action='store_true');a=p.parse_args()
    require((a.mode=='admit')==a.parent_authorized and (a.mode!='prepare')==bool(a.seal),'Separate explicit parent publication authority')
    out=a.output.absolute();require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh formal output')
    products,text=evaluate()
    hashes={str(out/n):hashlib.sha256((json.dumps(v,indent=2)+'\n').encode()).hexdigest() for n,v in products.items()}
    for n in ('combined-inputs.txt','generic-coverage-inputs.txt'):hashes[str(out/n)]=hashlib.sha256(text.encode()).hexdigest()
    proposal=dict(schema='AKV_CANONICAL_ALIAS_NATIVE796_ADMISSION_V1',output=str(out),baseline=str(BASE),baseline_seal=BASE_SHA,
        qualification=str(QUAL/'qualification.json'),qualification_seal=Q_SHA,
        successor_receipt=str(QUAL/'sd-successor-receipt.json'),successor_receipt_seal=RECEIPT_SHA,
        input_pins=products['evidence-pins.json'],output_pins=hashes,coverage_admitted=False)
    sidecar=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':life.save(sidecar,proposal);print('PREPARED796_NOT_ADMITTED',life.digest(sidecar));return
    require(life.read_bound(sidecar,a.seal)==proposal,'Exact full prepared replay')
    if a.mode=='verify':print('PREPARED796_VERIFY_PASS_NOT_ADMITTED');return
    out.mkdir()
    for n,v in products.items():life.save(out/n,v)
    for n in ('combined-inputs.txt','generic-coverage-inputs.txt'):
        with (out/n).open('x') as f:f.write(text)
    life.check(products['evidence-pins.json']);life.check(hashes)
    life.save(out/'admission-manifest.json',dict(proposal,coverage_admitted=True,prepared=str(sidecar),prepared_seal=a.seal,
        authorization_source='EXPLICIT_PARENT_ADMISSION_AUTHORIZATION_WITHIN_USER_GOAL'))
    print('ADMITTED796',life.digest(out/'admission-manifest.json'))


if __name__=='__main__':main()
