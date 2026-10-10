"""Parent-review-only793 successor proposal; no publication, simulation or EDA."""
import argparse
import hashlib
import json
from pathlib import Path

import collect_scalar_fpu_fma_arbiter792 as case
from collect_c910_float_edge_initialized777 import coverage_identity

runner,life,require,bitmap,toggle=case.runner,case.life,case.require,case.bitmap,case.toggle
BASE=life.OUT/'scalar-slot-rotation-offline-admitted793-parent-20261008-01'
BASE_SHA='757513188f805841491c898584b22722df80facd8f8c9fb424564a82502f17c3'
COUNTS=dict(line=1892,cond=2023,branch=2155,fsm=92)
CORE_SHA='5ca644a710faea6f831c15fb6d39ce74fcecdf03766027f8fa885dc3b747d4f1'
RUNNER_SHA='035050f880673774c1f4561d1ece7c87ac9c64f025e4cd9c9a29258d7ebac2bf'
TEST_SHA='f75d2b122675a63cf6a61c8523a4dd771faace1360bbd9095010d93c0b31b78f'


def qualification_gate(q):
    runner.exact_fields(q,dict(status='FULL_ARCHITECTURE_FMA_HOLD_OBSERVED_NOT_ADMITTED',
        baseline=792,baseline_seal=runner.oracle.BASE_SHA,checks=56,
        vector_status='UNOBSERVABLE_ZERO_DATA_REQUESTS',coverage_admitted=False,
        automatic_retry=False,official_percentage_claimed=False),'Complete FMA qualification, not no-hold')
    a=q['FMA_audit']
    require(a['FMA_hold_observed'] is True and type(a['FMA_hold_count']) is int and
        a['FMA_hold_count']==len(a['witnesses'])>0 and a['issued']==len(a['completed'])==50,
        'Measured owned FMA hold required; never retry to manufacture it')
    require(a['exception_observed']==['cause','valid','tval'] and
        a['exception_unobserved']==dict(tval2='UNOBSERVED',tinst='UNOBSERVED',gva='UNOBSERVED'),
        'Exact driven/UNOBSERVED exception contract')


def full_union(before,single):
    require(len(before['tests'])==len(set(before['tests']))==793 and len(single['tests'])==1 and
        single['tests'][0] not in before['tests'],'793 unique prefix plus one')
    require(before['design']==single['design'] and
        set(before['metrics'])==set(single['metrics'])==set(COUNTS),'Exact compiled four metrics')
    after=bitmap.combine(before,single)
    for metric,count in COUNTS.items():
        old,new,end=[v['metrics'][metric] for v in (before,single,after)]
        require(len(old)==count and set(old)==set(new)==set(end),'All6162 scopes retained')
        for scope,row in old.items():
            added,final=new[scope],end[scope]
            require((row['checksum'],row['width'])==(added['checksum'],added['width'])==
                (final['checksum'],final['width']),'Metric shape identity')
            values=[int(v['bits'],16) for v in (row,added,final)]
            require(min(values)>=0 and max(values).bit_length()<=row['width'] and
                values[2]==values[0]|values[1],'Exact bounded OR, no lost bits')
    require(after['tests']==before['tests']+single['tests'],'Exact successor ordering')
    return after


def positive(delta,gains):
    system=sum(len(v) for k,v in gains.items() if k==case.oracle.prior.SCOPE.split('.i_fpu')[0] or
        k.startswith('ara_tb.dut.i_ara_soc.i_system.'))
    require(sum(delta['metrics'].values())+system>0,'No fresh system gain: HOLD, no admission')
    return system


def historical_elf(base,ledger,authority,newhash):
    path=BASE/'elf-ledger-dedup.json';audit=life.read_bound(path,base['output_pins'][str(path)])
    require(audit['ledger_members']==792 and audit['duplicate'] is False and
        [r['vdb'] for r in audit['members']]==ledger[1:-1],'Sealed792 ELF history exact prefix')
    for row in audit['members']:
        require(bool(row['ELF_candidates']),'Historical ELF owner missing')
        for p,h in row['ELF_candidates'].items():
            require(authority.get(p)==h and h!=newhash,'Duplicate historical ELF or provenance drift')
    p=Path(ledger[-1]).parent/'manifest.json'
    record=life.read_bound(p,authority[str(p)])
    elves=[v.split('=',1)[1] for v in record['command'] if v.startswith('+PRELOAD=')]
    require(len(elves)==1 and elves[0] in authority and authority[elves[0]]!=newhash,
        'Actual793 command ELF ownership/duplicate')
    return dict(ledger_members=793,duplicate=False,members=audit['members']+[
        dict(vdb=ledger[-1],ELF_candidates={elves[0]:authority[elves[0]]},command_sources=[str(p)])],
        pins={str(path):base['output_pins'][str(path)],str(p):authority[str(p)],elves[0]:authority[elves[0]]})


def evaluate(directory,qsha,run,prepared_sha):
    qpath=directory/'qualification.json';q=life.read_bound(qpath,qsha);qualification_gate(q)
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    require(base['coverage_admitted'] is True and base['output']==str(BASE),'Formal793 exact authority')
    authority=life.merge_pins(base['input_pins'],base['output_pins'])
    pins=life.merge_pins(authority,q['input_pins']);pins=life.merge_pins(pins,q['output_pins'])
    pins=life.merge_pins(pins,{str(qpath):qsha,str(BASE/'admission-manifest.json'):BASE_SHA})
    for p,h in ((Path(case.__file__).resolve(),CORE_SHA),(Path(runner.__file__).resolve(),RUNNER_SHA),
        Path(runner.__file__).with_name('test_scalar_fpu_fma_arbiter792_runtime.py').resolve().__class__ and
        (Path(runner.__file__).with_name('test_scalar_fpu_fma_arbiter792_runtime.py').resolve(),TEST_SHA)):
        require(q['input_pins'].get(str(p))==h and life.digest(p)==h,'Frozen functional consumer authority')
    life.check(pins)
    def doc(folder,name,mapping):return life.read_bound(folder/name,mapping[str(folder/name)])
    before=doc(BASE,'combined-bits.json',base['output_pins'])
    bt=doc(BASE,'combined-toggle-bits.json',base['output_pins'])
    status=doc(BASE,'status.json',base['output_pins'])
    require(type(status['aggregate_passed']) is int and status['aggregate_passed']==793,'Formal793 status')
    ledger=(BASE/'combined-inputs.txt').read_text().splitlines()
    require(len(ledger)==len(set(ledger))==794 and ledger[1:]==before['tests'] and
        ledger[0]==str(life.IMAGE)+'.vdb','Complete exact793 input ledger')
    sidecar=run.with_name(run.name+'.prepared.json');record=life.read_bound(sidecar,prepared_sha)
    require(q['input_pins'].get(str(sidecar))==prepared_sha,'Qualified prepared binding')
    runner.verify(run,record,terminal=True);case.terminal_gate(run,record)
    case.stdout_gate((run/'console.log').read_text())
    pre=life.read_bound(runner.PRE/'preflight.json',runner.PRE_SHA)
    arch=case.oracle.prior.old.architecture
    scalar=arch.spike_trace.compare_commit_prefix(runner.PRE/'spike.trace',run/'commit_trace.csv',
        0x80000000,terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
    arch.scalar_exact(scalar,pre['counts'])
    require(scalar==doc(directory,'scalar-comparison.json',q['output_pins']) and
        q['scalar_counts']==pre['counts'],'Complete scalar/value/fflags reference unchanged')
    wave=case.wave_audit(directory/'probe.vcd',pre,record['source_contract'])
    require(wave==q['FMA_audit']==doc(directory,'FMA-owner-audit.json',q['output_pins']),
        'All50 native owners/ABC/tag/stall/output replay')
    vdb=run/'code.vdb';files={str(p) for p in vdb.rglob('*') if p.is_file()}
    require(files and not any(p.is_symlink() for p in vdb.rglob('*')) and
        files=={p for p in q['input_pins'] if p.startswith(str(vdb)+'/')},'Full VDB membership pins')
    folder=vdb/'snps/coverage/db/testdata'/runner.NAME
    require(list(folder.parent.iterdir())==[folder],'Exactly one native testcase')
    native=coverage_identity(folder,run,record,Path(ledger[0]))
    require(all(pins.get(p)==h for p,h in native.items()),'Native five-metric identity')
    require((directory/'single-inputs.txt').read_text().splitlines()==[ledger[0],str(vdb)],'Exact singleton ledger')
    single=bitmap.collect(directory/'single-inputs.txt')
    require(single==doc(directory,'single-bits.json',q['output_pins']),'Raw singleton replay')
    after=full_union(before,single);delta=bitmap.delta(before,after)
    st,h=toggle.rows(folder/'tgl.verilog.data.xml',list(bt))
    require(pins[str(folder/'tgl.verilog.data.xml')]==h and
        st==doc(directory,'single-toggle-bits.json',q['output_pins']),'Actual complete Toggle singleton')
    at=toggle.union(bt,st);gains=toggle.gains(bt,at);system=positive(delta,gains)
    elf=historical_elf(base,ledger,authority,record['elf_sha256'])
    pins=life.merge_pins(pins,elf['pins'])
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_prepare_scalar_fpu_fma_arbiter793_successor.py'),
              Path(coverage_identity.__code__.co_filename).resolve()):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins)
    return dict(status='FMA793_SUCCESSOR_PREPARED_NOT_ADMITTED',baseline=793,baseline_seal=BASE_SHA,
        proposed_population=794,publication_enabled=False,qualification_seal=qsha,prepared_run_seal=prepared_sha,
        pins=pins,full_OR_instances=6162,raw_delta=delta['metrics'],measured_system_Toggle=system,
        single_bits=single,combined_bits=after,combined_toggle_bits=at,Toggle_gains=gains,elf_dedup=elf,
        input_ledger=ledger+[str(vdb)],official_percentage_claimed=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','verify'))
    p.add_argument('--qualification',type=Path,required=True);p.add_argument('--qualification-seal',required=True)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--prepared-run-seal',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');a=p.parse_args()
    require(bool(a.seal)==(a.mode=='verify'),'Proposal verify requires seal')
    require(a.output.parent.resolve()==life.OUT and not a.output.is_symlink(),'Independent agent-owned proposal')
    value=evaluate(a.qualification.resolve(),a.qualification_seal,a.run.resolve(),a.prepared_run_seal)
    if a.mode=='prepare':life.save(a.output,value);print('PREPARED_NO_PUBLICATION',life.digest(a.output))
    else:
        require(life.read_bound(a.output,a.seal)==value,'Prepared successor drift')
        print('VERIFY_PASS_NO_ADMISSION')


if __name__=='__main__':main()
