"""Exact788 + qualified cause-storage implementation test; parent-only publication."""
import argparse
import hashlib
import json
from pathlib import Path

import collect_csr_cause_wlrl788 as case

run, life, need = case.runner, case.life, case.require
BASE, BASE_SHA = run.BASE, run.BASE_SHA
RUN = life.OUT/'csr-cause-wlrl788-parent-run-20261008-01'
RUN_SHA = '126bc695249d2c1162b80a9902d696ece50fd1c774d1932748769b60bbd77a25'
QUAL = life.OUT/'csr-cause-wlrl788-qualified-agent-20261008-01'
QUAL_SHA = 'eeee74b78cf11ffa9b65c7fab75d491896f217e142f998caf6129fe5b198d5bf'
COUNTS = dict(line=1892,cond=2023,branch=2155,fsm=92)

def full_union(before,single):
    need(len(before['tests'])==len(set(before['tests']))==788 and
         single['tests']==[str(RUN/'code.vdb')] and single['tests'][0] not in before['tests'],'Exact788 unique append')
    need(before['design']==single['design'] and set(before['metrics'])==set(single['metrics'])==set(COUNTS),'Frozen design/full metrics')
    life.merge_pins(before['input_hashes'],single['input_hashes'])
    after=case.original.bitmap.combine(before,single)
    for metric,count in COUNTS.items():
        old,add,final=(x['metrics'][metric] for x in (before,single,after))
        need(len(old)==count and set(old)==set(add)==set(final),'Full6162 scope universe')
        for scope,a in old.items():
            b,c=add[scope],final[scope]
            need(all(type(r['width']) is int and r['width']>=0 for r in (a,b,c)) and
                 (a['width'],a['checksum'])==(b['width'],b['checksum'])==(c['width'],c['checksum']),'Exact bounded metric shape')
            aa,bb,cc=(int(r['bits'],16) for r in (a,b,c))
            need(min(aa,bb,cc)>=0 and max(aa,bb,cc).bit_length()<=a['width'] and cc==aa|bb,'Exact full OR')
    need(after['tests']==before['tests']+single['tests'] and len(set(after['tests']))==789,'Exact789 prefix')
    return after

def typed_gain(target,sample):
    need(target['baseline']==788 and target['baseline_seal']==BASE_SHA and len(target['fields'])==8,'Source-bound eight cause targets')
    result=[];seen=set()
    for field in target['fields']:
        key=(field['scope'],field['attributes']['name']);need(key not in seen,'Duplicate target identity');seen.add(key)
        r=sample[field['scope']];positions=field['missing_coordinates']
        need(r['checksum']==field['checksum'] and len(positions)==len(set(positions)) and
             all(type(i) is int and 0<=i<r['width'] for i in positions),'Bounded typed target positions')
        gained=[i for i in positions if int(r['bits'],16)>>(r['width']-1-i)&1]
        result.append(dict(scope=field['scope'],name=key[1],checksum=r['checksum'],width=r['width'],before_missing=positions,gained=gained))
    need(sum(len(f['gained']) for f in result)>0,'Zero Toggle gain rejected')
    return result

def historical_elf(base,ledger,authority):
    path=BASE/'elf-ledger-dedup.json';audit=life.read_bound(path,base['output_pins'][str(path)])
    need(audit['ledger_members']==787 and audit['duplicate'] is False and
         [r['vdb'] for r in audit['members']]==ledger[1:788],'Sealed historical787 ownership')
    members=audit['members'][:]
    for row in members:
        need(row['ELF_candidates'],'Missing historical ELF')
        for p,h in row['ELF_candidates'].items():need(authority.get(p)==h and h!=run.ELF_SHA,'Historical ELF drift/duplicate')
    command_path=Path(ledger[-1]).parent/'manifest.json'
    command=life.read_bound(command_path,authority[str(command_path)])['command']
    elf=[s.split('=',1)[1] for s in command if s.startswith('+PRELOAD=')]
    need(len(elf)==1 and elf[0] in authority and authority[elf[0]]!=run.ELF_SHA,'Actual788 ELF owner/duplicate')
    members.append(dict(vdb=ledger[-1],ELF_candidates={elf[0]:authority[elf[0]]},command_sources=[str(command_path)]))
    return dict(ledger_members=788,members=members,duplicate=False,pins={str(path):base['output_pins'][str(path)],str(command_path):authority[str(command_path)],elf[0]:authority[elf[0]]},new_ELF_sha256=run.ELF_SHA,historical_authority_only=True)

def evaluate():
    q=life.read_bound(QUAL/'qualification.json',QUAL_SHA)
    run.exact_fields(q,dict(status='CAUSE_WLRL788_FULL_SCALAR_NATIVE_OWNER_QUALIFIED_NOT_ADMITTED',run=str(RUN),run_seal=RUN_SHA,checks=44,observed_bytes=336,scalar_retirements=664,scalar_memory_accesses=168,native_CSR_owners=30,vector_status='UNOBSERVABLE_ZERO_DESTINATIONS',full_scalar_differential_qualified=True,coverage_admitted=False,RTL_changed=False,EDA_launched=False),'Complete cause qualification authority')
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    need(base['coverage_admitted'] is True and base['output']==str(BASE),'Formal788 authority')
    authority=life.merge_pins(base['input_pins'],base['output_pins'])
    pins=life.merge_pins(authority,life.merge_pins(q['input_pins'],q['output_pins']))
    pins=life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SHA,str(QUAL/'qualification.json'):QUAL_SHA})
    def doc(name):return life.read_bound(QUAL/name,q['output_pins'][str(QUAL/name)])
    required={'scalar-comparison.json','vector-comparison.json','vpd2vcd.log','csr-owner.vcd','single-inputs.txt','single-bits.json','combined-bits.json','raw-delta.json','architecture-audit.json','native-csr-owner-audit.json'}
    need(set(q['output_pins'])=={str(QUAL/n) for n in required},'Complete qualification outputs')
    before=life.read_bound(BASE/'combined-bits.json',authority[str(BASE/'combined-bits.json')])
    status=life.read_bound(BASE/'status.json',authority[str(BASE/'status.json')])
    ledger=(BASE/'combined-inputs.txt').read_text().splitlines()
    need(type(status['aggregate_passed']) is int and status['aggregate_passed']==788 and status['coverage_admitted'] is True and ledger==[str(life.IMAGE)+'.vdb',*before['tests']] and len(ledger)==len(set(ledger))==789,'Exact formal788 population')
    record=life.read_bound(RUN/'manifest.json',RUN_SHA);run.verify_prepared(RUN,record,terminal=True)
    ns=case.namespace();ns['terminal_gate'](*[life.read_bound(RUN/n,pins[str(RUN/n)]) for n in ('simulation-status.json','started.json','live-identity.json')],record)
    pre=life.read_bound(run.PRE/'preflight-manifest.json',run.PRE_SEAL)
    scalar=case.original.spike_trace.compare_commit_prefix(run.PRE/'spike.trace',RUN/'commit_trace.csv',0x80000000,terminal_tohost_address=pre['symbols']['tohost'],rvfi_store_data_layout='unshifted')
    ns['scalar_gate'](scalar);need(scalar==doc('scalar-comparison.json'),'Full scalar replay differs')
    arch=ns['architecture'](case.original.primitive.parse_rows(RUN/'commit_trace.csv'),run.reference(pre),pre['symbols'],run.ELF.read_bytes())
    need(arch==doc('architecture-audit.json'),'All gold/guards/scalar memory differs')
    case.CURRENT_RUN=RUN;owners=case.wave_audit(QUAL/'csr-owner.vcd',arch['expected_CSR'])
    need(owners==doc('native-csr-owner-audit.json'),'All30 packed/native/RVFI owners differ')
    case.original.primitive.zero.vector_zero(RUN/'vector_trace.csv')
    vector=case.original.vector_commit.compare_vector_commits(run.PRE/'spike.trace',RUN/'commit_trace.csv',RUN/'vector_trace.csv',0x80000000)
    case.original.primitive.vector_gate(vector);need(vector==doc('vector-comparison.json'),'Zero vector schema differs')
    for n in ('run.vcs.log','console.log'):case.original.primitive.log_gate((RUN/n).read_text())
    lines=(RUN/'console.log').read_text().splitlines()
    need(lines.count('CSR_OWNER_PROBE_READY')==1 and not any(case.original.re.match(r'^CSR_OWNER_PROBE_ERROR(?:\s|$)',l) for l in lines),'Exact probe events')
    vdb=RUN/'code.vdb';members={str(p) for p in vdb.rglob('*') if p.is_file()}
    need(members and not any(p.is_symlink() for p in vdb.rglob('*')) and members=={p for p in q['input_pins'] if p.startswith(str(vdb)+'/')},'Complete VDB membership')
    folder=vdb/'snps/coverage/db/testdata'/run.NAME
    need(list(folder.parent.iterdir())==[folder],'Exact native test')
    native=case.original.coverage.coverage_identity(folder,RUN,record,Path(ledger[0]))
    need(all(pins.get(p)==h for p,h in native.items()),'Five-metric native executed identity')
    single=doc('single-bits.json')
    need((QUAL/'single-inputs.txt').read_text().splitlines()==[ledger[0],str(vdb)] and all(pins.get(p)==h for p,h in single['input_hashes'].items()),'Singleton input provenance')
    for metric in COUNTS:
        need(single['metrics'][metric]==case.original.bitmap.read_metric(folder/(metric+'.verilog.data.xml')),'Actual metric contents')
    after=full_union(before,single);delta=case.original.bitmap.delta(before,after)
    need(after==doc('combined-bits.json') and delta==doc('raw-delta.json') and q['raw_gain']['baseline']==788 and delta['metrics']==q['raw_gain']['four_metrics'],'Qualification full OR/delta differs')
    target=life.read_bound(run.PRE/'target-before.json',pins[str(run.PRE/'target-before.json')])
    sourcepins={};need(run.oracle.target_evidence(sourcepins)==target,'Fresh typed source/raw-zero targets differ');pins=life.merge_pins(pins,sourcepins)
    toggle_path=folder/'tgl.verilog.data.xml';sample,h=run.oracle.prior.toggle.rows(toggle_path,{f['scope'] for f in target['fields']})
    need(pins.get(str(toggle_path))==h,'Native Toggle bytes');fields=typed_gain(target,sample)
    dedup=historical_elf(base,ledger,authority);pins=life.merge_pins(pins,dedup['pins'])
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_csr_cause_wlrl789.py')):pins=life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins)
    products={Path(p).name:life.read_bound(Path(p),h) for p,h in base['output_pins'].items() if Path(p).parent==BASE and p.endswith('.json') and ('toggle-gain' in Path(p).name or Path(p).name.startswith('retained-'))}
    products.update({'single-bits.json':single,'combined-bits.json':after,'raw-delta.json':delta,'cause-target-toggle-gain.json':fields,'elf-ledger-dedup.json':dedup,'evidence-pins.json':pins,'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',aggregate_passed=789,baseline=788,new_passed=1,coverage_admitted=True,exact788_prefix=True,unique_new_vdb=True,duplicate_ELF=False,full_OR_metric_instances=6162,raw_delta=delta['metrics'],measured_target_Toggle_directions=sum(len(f['gained']) for f in fields),qualification_seal=QUAL_SHA,scalar_retirements=664,scalar_memory_accesses=168,native_CSR_owners=30,software_checks=44,vector_status='UNOBSERVABLE_ZERO_DESTINATIONS',portable_exception_codes=False,official_percentage_claimed=False,RTL_changed=False,new_simulation=False)})
    return products,'\n'.join([ledger[0],*after['tests']])+'\n'

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','verify','admit'));p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--parent-authorized',action='store_true');a=p.parse_args()
    need((a.mode=='admit')==a.parent_authorized and (a.mode!='prepare')==bool(a.seal),'Explicit parent publication/seal')
    out=a.output.absolute();need(out.parent==life.OUT and out==out.resolve() and not out.exists(),'Fresh output')
    values,text=evaluate();hashes={str(out/n):hashlib.sha256((json.dumps(v,indent=2)+'\n').encode()).hexdigest() for n,v in values.items()}
    for n in ('combined-inputs.txt','generic-coverage-inputs.txt'):hashes[str(out/n)]=hashlib.sha256(text.encode()).hexdigest()
    proposal=dict(schema='CAUSE_WLRL_HISTORICAL789_ADMISSION_V1',output=str(out),baseline=str(BASE),baseline_seal=BASE_SHA,qualification=str(QUAL/'qualification.json'),qualification_seal=QUAL_SHA,input_pins=values['evidence-pins.json'],output_pins=hashes,coverage_admitted=False)
    sidecar=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':life.save(sidecar,proposal);print('PREPARED_NOT_ADMITTED',life.digest(sidecar));return
    need(life.read_bound(sidecar,a.seal)==proposal,'Prepared admission drift')
    if a.mode=='verify':print('PREPARED789_VERIFY_PASS_NO_ADMISSION');return
    out.mkdir()
    for n,v in values.items():life.save(out/n,v)
    for n in ('combined-inputs.txt','generic-coverage-inputs.txt'):
        with (out/n).open('x') as f:f.write(text)
    life.check(proposal['input_pins']);life.check(hashes)
    life.save(out/'admission-manifest.json',dict(proposal,coverage_admitted=True,prepared=str(sidecar),prepared_seal=a.seal,authorization_source='EXPLICIT_PARENT_ADMISSION_AUTHORIZATION'))
    print('ADMITTED789',life.digest(out/'admission-manifest.json'))
if __name__=='__main__':main()
