"""Parent-only formal794 append of full DIV144 flush-priority qualification."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import collect_scalar_div_subnormal794_v2 as successor
import admit_itlb_ppn_aba794 as union_tools
import admit_itlb_ppn_aba794_v2 as toggle_tools

c=successor.original
life,require,runner=c.life,c.require,c.runner
BASE,BASE_SHA=c.oracle.BASE,c.oracle.BASE_SHA
QUAL=life.OUT/'scalar-div-subnormal794-qualified-v2-parent-20261008-01'
QUAL_SHA='6dc6a89afce6346a52b52647ca43b8eb6a3a4d2d012655bcce3739e72f0bf2ef'
RUN=life.OUT/'scalar-div-subnormal794-old-image-parent-20261008-01'
RUN_SHA='dc033335b17cee63364d49f0a636de5535c496dee496d4f3b2af656d84556965'


def qualification_gate(q):
    runner.exact_fields(q,dict(status='FULL_SCALAR_DIV_SUBNORMAL144_NATIVE_QUALIFIED_NOT_ADMITTED',
        baseline=794,baseline_seal=BASE_SHA,vector_status='UNOBSERVABLE_ZERO_DATA_REQUESTS',
        coverage_admitted=False,official_percentage_claimed=False,RTL_changed=False,automatic_retry=False),
        'Complete frozen qualification authority')
    a=q['qualification_authority']
    require(a['original_collector_sha']==successor.wave.OLD_SHA and a['wave_evidence_sha']==successor.WAVE_SHA
        and a['successor']=='scheduled_flush_v2' and a['formal_admission_performed'] is False
        and a['prospective_admission_population']==795,'Mandatory reviewed flush-priority successor')
    pins=successor.authority()
    require(all(q['input_pins'].get(p)==h for p,h in pins.items()),'Complete successor/source/test authority')
    require(q['architecture']['cells']==144 and q['architecture']['checks']==436
        and q['architecture']['FCSR_restored'] is True and q['architecture']['guards_checked'] is True,
        'Full independent numeric/flags/FCSR/signatures/guards')
    require(type(q['measured_Toggle']) is int and q['measured_Toggle']>=0,'Measured count type')


def full_union(before,single,vdb):
    require(len(before['tests'])==len(set(before['tests']))==794,'Formal794 unique population')
    after=union_tools.full_union(before,single,vdb)
    require(after['tests']==before['tests']+[str(vdb)] and len(set(after['tests']))==795,'Exact795 prefix')
    return after


def dedup(base,ledger,authority,newhash):
    path=BASE/'elf-ledger-dedup.json';old=life.read_bound(path,base['output_pins'][str(path)])
    require(old['ledger_members']==793 and old['duplicate'] is False
        and [r['vdb'] for r in old['members']]==ledger[1:-1],'Closed historical793 ownership')
    members=old['members'][:]
    for r in members:
        require(r['ELF_candidates'] and all(authority.get(p)==h and h!=newhash
            for p,h in r['ELF_candidates'].items()),'Historical duplicate ELF/ownership')
    command_path=Path(ledger[-1]).parent/'manifest.json'
    record=life.read_bound(command_path,authority[str(command_path)])
    elfs=[s.split('=',1)[1] for s in record['command'] if s.startswith('+PRELOAD=')]
    require(len(elfs)==1 and elfs[0] in authority and record['pins'].get(elfs[0])==authority[elfs[0]]!=newhash,
        'Latest794 exact command and sealed ELF pin dedup')
    members.append(dict(vdb=ledger[-1],ELF_candidates={elfs[0]:authority[elfs[0]]},command_sources=[str(command_path)]))
    return dict(baseline=794,ledger_members=794,members=members,duplicate=False,
        new_ELF_sha256=newhash,pins={str(path):base['output_pins'][str(path)],
        str(command_path):authority[str(command_path)],elfs[0]:authority[elfs[0]]})


def positive(delta,gains):
    require(sum(delta['metrics'].values())+sum(map(len,gains.values()))>0,'Zero gain rejected')


def evaluate():
    q=life.read_bound(QUAL/'qualification.json',QUAL_SHA);qualification_gate(q)
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    require(base['coverage_admitted'] is True and base['output']==str(BASE),'Formal794 sealed authority')
    authority=life.merge_pins(base['input_pins'],base['output_pins'])
    pins=life.merge_pins(authority,q['input_pins']);pins=life.merge_pins(pins,q['output_pins'])
    files=(Path(__file__).resolve(),Path(__file__).with_name('test_admit_scalar_div_subnormal795.py'),
        Path(union_tools.__file__).resolve(),Path(toggle_tools.__file__).resolve())
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in files})
    pins=life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SHA,str(QUAL/'qualification.json'):QUAL_SHA})
    life.check(pins)
    def doc(folder,name,map):
        p=folder/name;return life.read_bound(p,map[str(p)])
    status=doc(BASE,'status.json',base['output_pins'])
    require(type(status['aggregate_passed']) is int and status['aggregate_passed']==794
        and status['coverage_admitted'] is True,'Formal794 terminal status')
    before=doc(BASE,'combined-bits.json',base['output_pins']);bt=doc(BASE,'combined-toggle-bits.json',base['output_pins'])
    ledger=(BASE/'combined-inputs.txt').read_text().splitlines()
    require(ledger==[str(life.IMAGE)+'.vdb',*before['tests']] and len(ledger)==len(set(ledger))==795,'Full794 ledger')
    record=life.read_bound(RUN.with_name(RUN.name+'.prepared.json'),RUN_SHA)
    require(pins.get(str(RUN.with_name(RUN.name+'.prepared.json')))==RUN_SHA,'Exact executed prepared authority')
    runner.verify(RUN,record,terminal=True);c.terminal_gate(RUN,record)
    require(json.loads((RUN/'manifest.json').read_text())==record,'Executed manifest equals sealed preparation')
    c.stdout_gate((RUN/'console.log').read_text())
    pre=life.read_bound(runner.PRE/'preflight.json',runner.PRE_SHA)
    arch=c.original.oracle.prior.old.architecture
    scalar=arch.spike_trace.compare_commit_prefix(runner.PRE/'spike.trace',RUN/'commit_trace.csv',0x80000000,
        terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
    require(scalar==doc(QUAL,'scalar-comparison.json',q['output_pins']),'Full scalar/FP/memory replay differs')
    with (RUN/'commit_trace.csv').open() as f:rows=list(csv.DictReader(f))
    native=c.architecture(rows,pre,scalar)
    require(native==q['architecture']==doc(QUAL,'architecture-audit.json',q['output_pins']),'Whole gold/CSR/guards replay')
    with (RUN/'vector_trace.csv').open() as f:
        require(all(r['event']=='config' for r in csv.DictReader(f)),'Explicit zero vector data; no vectorPASS claim')
    wave=successor.wave.wave_audit(QUAL/'probe.vcd',record['source_contract'],pre)
    require(wave==q['native_exponent_audit']==doc(QUAL,'native-exponent-audit.json',q['output_pins']),
        'All576 live/held/output owners and144 DIV stages replay')
    vdb=RUN/'code.vdb';members={str(p) for p in vdb.rglob('*') if p.is_file()}
    require(members and members=={p for p in q['input_pins'] if p.startswith(str(vdb)+'/')}
        and not any(p.is_symlink() for p in vdb.rglob('*')),'Whole immutable VDB membership')
    folder=vdb/'snps/coverage/db/testdata'/runner.NAME
    require(list(folder.parent.iterdir())==[folder],'One unique native testcase')
    c.coverage_identity(folder,RUN,record,Path(ledger[0]))
    single=doc(QUAL,'single-bits.json',q['output_pins'])
    for metric in union_tools.COUNTS:
        require(single['metrics'][metric]==c.bitmap.read_metric(folder/(metric+'.verilog.data.xml')),'Four raw bytes exact')
    after=full_union(before,single,vdb);delta=c.bitmap.delta(before,after)
    require(delta==doc(QUAL,'raw-four-metric-delta.json',q['output_pins']) and delta['metrics']==q['raw_delta'],'Raw delta exact')
    st,sha=c.toggle.rows(folder/'tgl.verilog.data.xml',list(bt))
    require(pins[str(folder/'tgl.verilog.data.xml')]==sha and st==doc(QUAL,'single-toggle-bits.json',q['output_pins']),
        'Native Toggle singleton exact')
    at=c.toggle.union(bt,st);toggle_tools.all_toggle_or(bt,st,at);gains=c.toggle.gains(bt,at)
    require(gains==doc(QUAL,'raw-toggle-gains.json',q['output_pins']) and sum(map(len,gains.values()))==q['measured_Toggle'],
        'All2989 Toggle measured increment exact')
    positive(delta,gains)
    elf=dedup(base,ledger,authority,record['elf_sha256']);pins=life.merge_pins(pins,elf['pins']);life.check(pins)
    products={Path(p).name:life.read_bound(Path(p),h) for p,h in base['output_pins'].items()
        if Path(p).parent==BASE and p.endswith('.json') and ('toggle-gain' in Path(p).name or Path(p).name.startswith('retained-'))}
    products.update({'single-bits.json':single,'combined-bits.json':after,'combined-toggle-bits.json':at,
        'raw-delta.json':delta,'div-subnormal-toggle-gain.json':gains,'elf-ledger-dedup.json':elf,'evidence-pins.json':pins,
        'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',aggregate_passed=795,baseline=794,new_passed=1,
            coverage_admitted=True,exact794_prefix=True,unique_new_vdb=True,duplicate_ELF=False,
            full_OR_metric_instances=6162,full_OR_Toggle_instances=2989,raw_delta=delta['metrics'],
            measured_Toggle_positions=q['measured_Toggle'],software_checks=436,native_FPU_owners=576,
            independent_full_scalar=True,vector_status=q['vector_status'],qualification_seal=QUAL_SHA,
            official_percentage_claimed=False,RTL_changed=False,new_simulation=False)})
    return products,'\n'.join([ledger[0],*after['tests']])+'\n'


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','verify','admit'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--parent-authorized',action='store_true')
    a=p.parse_args();require((a.mode=='admit')==a.parent_authorized and (a.mode!='prepare')==bool(a.seal),'Explicit parent authority/seal')
    out=a.output.absolute();require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh formal output')
    products,text=evaluate()
    hashes={str(out/n):hashlib.sha256((json.dumps(v,indent=2)+'\n').encode()).hexdigest() for n,v in products.items()}
    for n in ('combined-inputs.txt','generic-coverage-inputs.txt'):hashes[str(out/n)]=hashlib.sha256(text.encode()).hexdigest()
    proposal=dict(schema='SCALAR_DIV_SUBNORMAL_HISTORICAL795_FLUSH_PRIORITY_ADMISSION_V1',output=str(out),
        baseline=str(BASE),baseline_seal=BASE_SHA,qualification=str(QUAL/'qualification.json'),qualification_seal=QUAL_SHA,
        input_pins=products['evidence-pins.json'],output_pins=hashes,coverage_admitted=False)
    sidecar=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':life.save(sidecar,proposal);print('PREPARED795_NOT_ADMITTED',life.digest(sidecar));return
    require(life.read_bound(sidecar,a.seal)==proposal,'Exact prepared admission replay')
    if a.mode=='verify':print('PREPARED795_VERIFY_PASS_NOT_ADMITTED');return
    out.mkdir()
    for n,v in products.items():life.save(out/n,v)
    for n in ('combined-inputs.txt','generic-coverage-inputs.txt'):
        with (out/n).open('x') as f:f.write(text)
    life.check(products['evidence-pins.json']);life.check(hashes)
    life.save(out/'admission-manifest.json',dict(proposal,coverage_admitted=True,prepared=str(sidecar),
        prepared_seal=a.seal,authorization_source='EXPLICIT_PARENT_ADMISSION_AUTHORIZATION'))
    print('ADMITTED795',life.digest(out/'admission-manifest.json'))


if __name__=='__main__':main()
