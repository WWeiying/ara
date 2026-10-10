"""Offline793-prefix admission of independently qualified ITLB PPN A/B/A; no EDA/model."""
import argparse
import hashlib
import json
from pathlib import Path

import collect_itlb_ppn_aba as case
import run_itlb_ppn_aba as runner
from admit_stride_metadata768 import dedup

life,require,bitmap,toggle=case.life,case.require,case.bitmap,case.pre.prior.native
BASE=life.OUT/'scalar-slot-rotation-offline-admitted793-parent-20261008-01'
BASE_SHA='757513188f805841491c898584b22722df80facd8f8c9fb424564a82502f17c3'
PREPARED=life.OUT/'itlb-ppn-aba-old-image792-parent-20261008-01.prepared.json'
PREPARED_SHA='ee90d67c0e880ee590d822e6b1131ee8154962ca5f4c926149e75b8ac199bd12'
ELF_SHA='6020c6f45bb152759dbcce58dcc83e96e6be7ff094dda662b69213c6e40da0b1'
QUALIFIED=life.OUT/'itlb-ppn-aba-qualified-v2-parent-20261008-01'
QUALIFIED_SHA='0e39eeac0b6a6335877c8232a7b54fe44f91a0e162cdc81b562d56547f7495f8'
SUCCESSOR_SHA='959809fb5b34bfd3794c16d4fc4fabc807a89335c41ef0f0802d6283a4865e47'
COUNTS={'line':1892,'cond':2023,'branch':2155,'fsm':92}
REQUIRED=('scalar-comparison.json','csr-lifecycle.json','native-oracle.json',
          'itlb-axi-observations.json','native-VDB-identity.json','single-inputs.txt',
          'single-bits.json','diagnostic-combined-bits.json','raw-delta.json',
          'toggle-gain.json','evidence-pins.json','itlb-exec.vcd','convert.log',
          'console-csr-contract.json')


def prefix(before,ledger,original):
    require(len(before['tests'])==len(set(before['tests']))==793 and
            len(ledger)==len(set(ledger))==794 and ledger[1:]==before['tests'] and
            ledger[:793]==original,'Exact formal793 ledger and full792 prefix required')


def full_union(before,single,vdb):
    require(single['tests']==[str(vdb)] and str(vdb) not in before['tests'],'One unique candidate VDB')
    after=bitmap.combine(before,single)
    require(after['tests']==before['tests']+single['tests'] and
            set(before['metrics'])==set(single['metrics'])==set(after['metrics'])==set(COUNTS),
            'Exact four metrics/prefix')
    for metric,count in COUNTS.items():
        old,added,final=[x['metrics'][metric] for x in (before,single,after)]
        require(len(old)==count and set(old)==set(added)==set(final),'Full6162 instance universe required')
        for scope,row in old.items():
            new,end=added[scope],final[scope]
            require((row['width'],row['checksum'])==(new['width'],new['checksum'])==
                    (end['width'],end['checksum']),'Compiled metric identity differs')
            values=[int(x['bits'],16) for x in (row,new,end)]
            require(min(values)>=0 and max(values).bit_length()<=row['width'] and
                    values[2]==values[0]|values[1],'Independent OR/bounds differs')
    return after


def qualification_gate(q,directory):
    require(q['status']=='ITLB_PPN_ABA792_ARCHITECTURE_ACTUAL16_SLOT_QUALIFIED_NOT_ADMITTED' and
            q['baseline']==792 and q['software_checks']==3846 and q['coverage_admitted'] is False and
            q['official_percentage'] is False,'Complete successful independent qualification required')
    require(all(str(directory/n) in q['output_pins'] for n in REQUIRED),
            'Missing required qualified output pin')
    require(all(type(q[k]) is int and q[k]>=0 for k in ('toggle_new_positions','target_new_positions')),
            'Exact measured count types required')


def rebase(before,single):
    require(case.SCOPE in before and case.SCOPE in single,'Exact ITLB scope required')
    after=toggle.union(before,single)
    gains=toggle.gains(before,after)
    row=before[case.SCOPE]
    require(row['checksum']=='817233724','Exact compiled ITLB checksum required')
    positions=gains[case.SCOPE]
    require(positions,'No fresh ITLB Toggle against formal793')
    return after,dict(baseline=793,scope=case.SCOPE,before=row,single=single[case.SCOPE],
        after=after[case.SCOPE],new_positions=len(positions),new_serialized_positions=positions,
        direction_order_calibrated=False,official_percentage=False,
        native_summary_hit_metadata_not_recomputed=True,historical792_gain_not_recounted=True)


def historical_dedup(ledger,newhash,authority):
    audit=dedup(ledger,newhash,authority)
    require(audit['ledger_members']==793 and audit['duplicate'] is False and
            [x['vdb'] for x in audit['members']]==ledger[1:] and
            all(authority.get(p)==h for p,h in audit['pins'].items()),
            'Historical793-only ELF ownership required, not candidate qualification')
    return audit


def evaluate(directory,qsha):
    require(directory==QUALIFIED and qsha==QUALIFIED_SHA,
            'Only the independently reviewed complete v2 qualification')
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    require(base['coverage_admitted'] is True and base['output']==str(BASE),'Formal793 authority required')
    authority=life.merge_pins(base['input_pins'],base['output_pins'])
    qpath=directory/'qualification.json';q=life.read_bound(qpath,qsha);qualification_gate(q,directory)
    successor=Path(__file__).with_name('collect_itlb_ppn_aba_v2.py').resolve()
    require(q['original_failure_preserved'] is True and
            q['original_collector_sha256']=='1fd703e7df46fc5fd8bacfa903ffd81b5ec649bedd53a4f909d9752694c2bcd9' and
            q['input_pins'].get(str(successor))==SUCCESSOR_SHA,
            'Exact CSR-aware successor and preserved original rejection')
    pins=life.merge_pins(authority,q['input_pins']);pins=life.merge_pins(pins,q['output_pins'])
    pins=life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SHA,str(qpath):qsha})
    life.check(pins)
    def bdoc(name):
        p=BASE/name;return life.read_bound(p,base['output_pins'][str(p)])
    def qdoc(name):
        p=directory/name;return life.read_bound(p,q['output_pins'][str(p)])
    before=bdoc('combined-bits.json');all_toggle=bdoc('combined-toggle-bits.json')
    status=bdoc('status.json')
    require(status['aggregate_passed']==793 and status['coverage_admitted'] is True and
            status['full_OR_metric_instances']==6162,'Exact793 status required')
    ledger=(BASE/'combined-inputs.txt').read_text().splitlines()
    _,old_toggle,original,original_pins=case.baseline()
    prefix(before,ledger,original);pins=life.merge_pins(pins,original_pins)
    record=life.read_bound(PREPARED,PREPARED_SHA);run=runner.validate(record)
    require(pins.get(str(PREPARED))==PREPARED_SHA,'Qualification must bind exact prepared configuration')
    require(life.read_bound(run/'manifest.json',q['input_pins'][str(run/'manifest.json')])==
            dict(record,pins=life.merge_pins(record['pins'],{str(PREPARED):PREPARED_SHA})),
            'Executed/prepared manifest differs')
    prepath=Path(record['preflight']);pre=life.read_bound(prepath,record['preflight_seal'])
    require(pre['input_pins'].get(str(prepath.parent/'input.elf'))==ELF_SHA and
            pins.get(str(prepath.parent/'input.elf'))==ELF_SHA,'Exact unique candidate ELF required')
    case.original.exact_scalar(qdoc('scalar-comparison.json'),pre['counts'])
    native=qdoc('native-oracle.json');csr=qdoc('csr-lifecycle.json');wave=qdoc('itlb-axi-observations.json')
    console=qdoc('console-csr-contract.json')
    require(console['status']=='SIX_READONLY_CSR_CONSOLE_CSV_MONITOR_EXACT_ZERO_VECTOR_WRITES' and
            console['summary']==dict(requests=6,responses=6,exceptions=0,mmu_request_cycles=0,
                protocol_errors=0,outstanding=0,req_stalled=0,resp_stalled=0) and
            console['lifecycle']==csr and console['zero_vector_writes'] is True and
            console['UVM_final_summary_claimed'] is False and
            len(console['boundary_cycles'])==len(console['monitor_cycles'])==6,
            'Sealed six-CSR console/monitor/retire evidence required')
    require(native['checks']==3846 and native['failed']==0 and len(native['traps'])==48 and
            all(native[k] is True for k in ('complete_scalar_PC_GPR_memory','physical_A_B_code_distinguished',
                'full_preload_and_postexecute_guards','CSR_restored')) and
            native['UVM_final_report_claimed'] is False,'Complete physical code/guards/CSR oracle required')
    require(csr['status']=='SIX_REFERENCE_BOUND_READONLY_CSR_CONSERVED' and len(csr['records'])==6 and
            csr['all_architectural_consumers_in_full_scalar_comparison'] is True,'Qualified CSR lifecycle required')
    require(wave['status']=='PREEDGE_ITLB16_SLOT_THREE_PHASE_AND_AXI_DRAIN_PASS' and
            wave['actual_all16_A_B_A'] is True and wave['pre_timebucket_sampling'] is True and
            wave['no_post_startup_reset'] is True and wave['entry_visits']==[list(range(16))]*3,
            'Actual all16 accepted updates and complete AXI required')
    case.accepted_gate(wave['accepted_full_PTEs'])
    require(all(pins.get(p)==h for p,h in wave['source_layout_pins'].items()),'Bound full PTE/AXI layout')
    inputs=directory/'single-inputs.txt'
    require(inputs.read_text().splitlines()==[ledger[0],str(run/'code.vdb')],'Qualified plaintext singleton identity')
    single=bitmap.collect(inputs)
    require(single==qdoc('single-bits.json') and all(q['input_pins'].get(p)==h for p,h in single['input_hashes'].items()),
            'Fresh sealed singleton four-metric equality required')
    require(all(pins.get(str(Path(ledger[0])/'snps/coverage/db'/rel))==h for rel,h in single['design'].items()),
            'Bound compatible compiled design required')
    after=full_union(before,single,run/'code.vdb')
    folder=run/'code.vdb/snps/coverage/db/testdata'/runner.CASE
    require(list(folder.parent.iterdir())==[folder],'One exact native testcase')
    paths=[folder/n for n in ('siminfo.xml','vcmArguments.xml')]
    require(all(pins.get(str(p))==life.digest(p) for p in paths),'Sealed native identity files required')
    identity=case.native_identity(*(toggle.xml(p) for p in paths),record,ledger[0])
    require(identity==qdoc('native-VDB-identity.json'),'Qualified native command/workdir/seed equality')
    files=list(folder.glob('tgl.verilog.data.xml'));require(len(files)==1,'One native Toggle data file')
    all_single,h=toggle.rows(files[0],list(all_toggle))
    require(q['input_pins'].get(str(files[0]))==h,'Sealed native Toggle data required')
    all_after,gain=rebase(all_toggle,all_single)
    measured=qdoc('toggle-gain.json')
    require(measured['baseline']==792 and measured['scope']==case.SCOPE and
            measured['direction_order_calibrated'] is False and measured['official_percentage'] is False,
            '792 diagnostic is not a native direction mapping or official percentage')
    old_after=toggle.union({case.SCOPE:old_toggle[case.SCOPE]},{case.SCOPE:all_single[case.SCOPE]})
    require(toggle.gains({case.SCOPE:old_toggle[case.SCOPE]},old_after)[case.SCOPE]==
            measured['new_serialized_positions'],'Qualified792 gain independently rederived')
    require(set(gain['new_serialized_positions'])<=set(measured['new_serialized_positions']),
            '793 fresh gain must deduct previously admitted suffix hits')
    elf=historical_dedup(ledger,ELF_SHA,authority);pins=life.merge_pins(pins,elf['pins'])
    for module in (case,runner,case.pre,bitmap,toggle,toggle.base,life):
        p=Path(module.__file__).resolve()
        require(pins.get(str(p))==life.digest(p),'Bound reused dependency required: '+str(p))
    dep=Path(dedup.__code__.co_filename).resolve()
    require(authority.get(str(dep))==life.digest(dep),'Historical dedup helper authority required')
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_itlb_ppn_aba794.py').resolve()):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins)
    retained={}
    for path,h in base['output_pins'].items():
        p=Path(path)
        if p.parent==BASE and p.suffix=='.json' and ('toggle-gain' in p.name or p.name.startswith('retained-')):
            retained[p.name]=life.read_bound(p,h)
    require('itlb-ppn-aba-toggle-gain.json' not in retained,'Candidate already admitted')
    delta=bitmap.delta(before,after)
    values=dict(retained,**{'combined-bits.json':after,'single-bits.json':single,
        'combined-toggle-bits.json':all_after,'itlb-ppn-aba-toggle-gain.json':gain,
        'raw-delta.json':delta,'elf-ledger-dedup.json':elf,'native-vdb-identity.json':identity,
        'evidence-pins.json':pins,'status.json':dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',
            aggregate_passed=794,baseline=793,new_passed=1,coverage_admitted=True,
            exact793_prefix=True,exact792_prefix=True,unique_new_vdb=True,duplicate_ELF=False,
            full_OR_metric_instances=6162,measured_ITLB_Toggle_positions=gain['new_positions'],
            raw_delta=delta['metrics'],actual_slots=16,actual_accepted_updates=48,
            software_checks=3846,independent_full_scalar=True,complete_AXI=True,
            prior_gains_retained_not_recounted=True,official_percentage_claimed=False,
            serialized_direction_labels_claimed=False,native_summary_metadata_recomputed=False,
            RTL_changed=False,new_simulation=False,qualification_seal=qsha)})
    return values,'\n'.join([ledger[0],*after['tests']])+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','verify','admit'))
    p.add_argument('--qualification',type=Path,required=True);p.add_argument('--qualification-seal',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--parent-authorized',action='store_true')
    a=p.parse_args();require(a.parent_authorized==(a.mode=='admit') and bool(a.seal)==(a.mode!='prepare'),
                           'Explicit parent authorization and prepared seal required')
    out=a.output.absolute();directory=a.qualification.absolute()
    require(out.parent==life.OUT and out.resolve()==out and not out.exists() and
            directory.parent==life.OUT and directory.resolve()==directory,'Exact fresh output/qualification paths')
    products,text=evaluate(directory,a.qualification_seal)
    hashes={str(out/n):hashlib.sha256((json.dumps(v,indent=2)+'\n').encode()).hexdigest() for n,v in products.items()}
    for n in ('combined-inputs.txt','generic-coverage-inputs.txt'):hashes[str(out/n)]=hashlib.sha256(text.encode()).hexdigest()
    proposal=dict(schema='ITLB_PPN_ABA_HISTORICAL794_ADMISSION_V1',output=str(out),baseline=str(BASE),baseline_seal=BASE_SHA,
        qualification=str(directory/'qualification.json'),qualification_seal=a.qualification_seal,
        input_pins=products['evidence-pins.json'],output_pins=hashes,coverage_admitted=False)
    prepared=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':
        life.save(prepared,proposal);print('PREPARED_NOT_ADMITTED',life.digest(prepared),flush=True);return
    require(life.read_bound(prepared,a.seal)==proposal,'Prepared proposal differs')
    if a.mode=='verify':print('VERIFY_PASS_NO_ADMISSION',flush=True);return
    out.mkdir()
    for n,v in products.items():life.save(out/n,v)
    for n in ('combined-inputs.txt','generic-coverage-inputs.txt'):
        with (out/n).open('x') as f:f.write(text)
    life.check(proposal['input_pins']);life.check(hashes)
    life.save(out/'admission-manifest.json',dict(proposal,coverage_admitted=True,prepared=str(prepared),prepared_seal=a.seal,
        authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL'))
    print('ADMITTED',life.digest(out/'admission-manifest.json'),flush=True)


if __name__=='__main__':main()
