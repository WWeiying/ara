"""Offline exact773 + one parent-replayed ITLB bulk PASS; no EDA."""
import argparse
import hashlib
import json
from pathlib import Path
import collect_itlb_asid_exec_bulk_axi as collector
from admit_stride_metadata768 import dedup

core, life, require = collector.core, collector.life, collector.require
BASE, BASE_SHA = core.BASE, core.BASE_SHA
RUN = life.OUT / 'itlb-asid-exec-bulk-old-image-773-agent-20261007-01'
QUAL = life.OUT / 'itlb-asid-exec-bulk-offline-qualified-773-agent-20261007-01'
QUAL_SHA = '1a3357058c6ff5d1833fed726bfd70cd9710ab0946cb72f296b60f2a8fe526ae'
REPLAY = life.OUT / 'itlb-asid-exec-bulk-axi-parent-review-20261007-01'
REPLAY_SHA = 'd69da479938dba3aa798a67d40162a41d77ef8fbf5a6ec70eefedde67c61a73f'
DOCS = ('scalar-comparison.json','reference-exception-ledger.json','csr-lifecycle.json',
        'native-oracle.json','code-write-dominance.json','itlb-axi-observations.json',
        'single-bits.json','diagnostic-combined-bits.json','raw-delta.json','toggle-gain.json')


def documents(path, seal):
    q = life.read_bound(path / 'qualification.json', seal)
    require(q['status'] == 'ITLB_TRUE_SMODE_ARCHITECTURE_OBSERVATIONS_RAW773_QUALIFIED_NOT_ADMITTED'
            and q['baseline'] == 773 and q['coverage_admitted'] is False
            and q['official_percentage'] is False and q['UVM_final_report_claimed'] is False
            and q['software_checks'] == 10966 and q['toggle_new_positions'] == 948
            and q['target_new_positions'] == 862 and q['raw_delta'] ==
            dict(line=0,cond=0,branch=0,fsm=0), 'Exact qualified identity/gain')
    require(q['input_pins'] and q['output_pins'], 'Complete qualification pins')
    life.check(q['input_pins']); life.check(q['output_pins'])
    docs = {name:life.read_bound(path / name,q['output_pins'][str(path / name)]) for name in DOCS}
    core.exact_scalar(docs['scalar-comparison.json'],
        dict(matched_instructions=103572,matched_scalar_writes=66600,
             matched_scalar_memory_accesses=26384,matched_floating_writes=0))
    n = docs['native-oracle.json']
    require(n['checks'] == 10966 and n['failed'] == n['vector_writes'] == 0
            and n['full_code_bytes'] == 65536 and n['true_S_mode_instructions'] == 144
            and n['complete_scalar_including_compressed'] is True and n['CSR_restored'] is True
            and n['scalar_memory_accesses'] == 33005 and len(n['traps']) == 48,
            'Complete native/traps/PTE/code/CSR oracle')
    require([(r['phase'],r['entry']) for r in n['traps']] ==
            [(p,e) for p in range(3) for e in range(16)], 'Exact ordered48 traps')
    d = docs['code-write-dominance.json']
    require(d['status'] == 'NATIVE_INITIALIZATION_DOMINATES_ALL_FETCHES_AND_GUARD_READS'
            and d['word_stores'] == d['word_reads'] == 8192 and d['S_mode_entries'] == 48
            and d['no_redundant_writes'] is True and d['initial_ELF_memory_readback_claimed'] is False,
            'Every code word independently initialized and checked')
    c = docs['csr-lifecycle.json']
    require(c['status'] == 'SIX_READONLY_CSR_TAGGED_RESPONSE_RETIRE_AND_REAL_CONSUMERS_EXACT'
            and c['requests'] == c['responses'] == 6 and len(c['records']) == 6
            and all(r['start'] <= r['request'] <= r['response'] <= r['retire_cycle'] <=
                    r['consumer_cycle'] for r in c['records']), 'Exact CSR lifecycle/consumer')
    w = docs['itlb-axi-observations.json']
    require(w['status'] == 'PREEDGE_ITLB16_SLOT_THREE_PHASE_AND_AXI_DRAIN_PASS'
            and w['entry_visits'] == [list(range(16))]*3 and w['pre_timebucket_sampling'] is True
            and w['no_post_startup_reset'] is True and w['AXI_channels'] ==
            dict(ar=4308,r=16664,aw=18152,w=18152,b=18152), 'Actual all-slots/AXI drain')
    return q, docs


def replay_equal(q, docs, parent, parent_docs):
    require({k:v for k,v in q.items() if k not in ('input_pins','output_pins')} ==
            {k:v for k,v in parent.items() if k not in ('input_pins','output_pins')} and
            docs == parent_docs, 'Complete parent semantic replay differs')


def union(before, single):
    require(single['tests'] == [str(RUN/'code.vdb')] and
            set(before['metrics']) == set(single['metrics']) == set(core.bitmap.METRICS),
            'Exact unique candidate/four metrics')
    return core.full_union(before,single)


def evaluate():
    q, docs = documents(QUAL,QUAL_SHA)
    parent, parent_docs = documents(REPLAY,REPLAY_SHA)
    replay_equal(q,docs,parent,parent_docs)
    pins = life.merge_pins(q['input_pins'],q['output_pins'])
    pins = life.merge_pins(pins,parent['input_pins']);pins = life.merge_pins(pins,parent['output_pins'])
    for path, seal in ((QUAL/'qualification.json',QUAL_SHA),(REPLAY/'qualification.json',REPLAY_SHA)):
        pins = life.merge_pins(pins,{str(path):seal})
    before, ledger, bpins = core.baseline(); pins = life.merge_pins(pins,bpins)
    base = life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    require(base['coverage_admitted'] is True and base['output'] == str(BASE), 'Authoritative formal773')
    require(ledger[1:] == before['tests'] and len(set(ledger)) == 774, 'Exact773 input ledger')
    input_path = QUAL/'single-inputs.txt'
    require(pins.get(str(input_path)) == life.digest(input_path) and
            input_path.read_text().splitlines() == [ledger[0],str(RUN/'code.vdb')], 'Exact singleton input')
    single = core.bitmap.collect(input_path)
    require(single == docs['single-bits.json'] and
            all(pins.get(p)==h for p,h in single['input_hashes'].items()) and
            all(pins.get(str(Path(ledger[0])/'snps/coverage/db'/p))==h for p,h in single['design'].items()),
            'Re-read native singleton/compiled shape pins')
    after = union(before,single); delta = core.bitmap.delta(before,after)
    require(after == docs['diagnostic-combined-bits.json'] and delta == docs['raw-delta.json'],
            'Independent all6162 OR/773prefix/774unique delta')
    previous, pins = core.pre.toggle_baseline(ledger,pins)
    files = list((RUN/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(files)==1, 'Unique native Toggle member')
    sample, sha = core.pre.native.rows(files[0],[core.pre.SCOPE])
    require(pins.get(str(files[0])) == sha, 'Sealed singleton Toggle')
    merged = core.pre.native.union(previous,sample)
    positions = core.pre.native.gains(previous,merged)[core.pre.SCOPE]
    gain = docs['toggle-gain.json']
    require(gain['baseline']==773 and gain['scope']==core.pre.SCOPE and
            gain['before']==previous[core.pre.SCOPE] and gain['single']==sample[core.pre.SCOPE] and
            gain['after']==merged[core.pre.SCOPE] and gain['new_serialized_positions']==positions
            and gain['new_positions']==len(positions)==948, 'Rebuilt exact scoped Toggle gain')
    prediction, predpins = core.pre.prediction(); pins = life.merge_pins(pins,predpins)
    oldbits = format(int(previous[core.pre.SCOPE]['bits'],16),'0%db'%previous[core.pre.SCOPE]['width'])
    targets = [dict(native=t['native'],before_zero=[i for i in t['fresh_positions'] if oldbits[i]=='0'],
        hit_positions=sorted(set(t['fresh_positions']) & set(positions))) for t in prediction['targets']]
    require(gain['targets']==targets and sum(len(t['hit_positions']) for t in targets)==862,
            'Exact independently recalculated targeted gain')
    prepared = life.read_bound(RUN.with_name(RUN.name+'.prepared.json'),
        pins[str(RUN.with_name(RUN.name+'.prepared.json'))])
    life.read_bound(Path(prepared['preflight']),prepared['preflight_seal'])
    elfpath = Path(prepared['preflight']).parent/'input.elf'
    require(pins.get(str(elfpath))==life.digest(elfpath), 'Sealed unique candidate ELF')
    elf = dedup(ledger,pins[str(elfpath)],pins)
    require(elf['ledger_members']==773 and not elf['duplicate'] and
            all(pins.get(p)==h for p,h in elf['pins'].items()), 'All773 historical ELF identity pins/no duplicate')
    elf['baseline'] = 773
    for path in (Path(__file__).absolute(),Path(__file__).with_name('test_admit_itlb_bulk774.py').absolute(),
                 Path(dedup.__code__.co_filename).absolute()):
        pins = life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    status = dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',coverage_admitted=True,aggregate_passed=774,
        baseline=773,new_passed=1,exact773_prefix=True,full_OR_instances=6162,unique_new_vdb=True,
        duplicate_ELF=False,full_scalar_ISA_verified=True,software_checks=10966,supervisor_ecalls=48,
        all16_ITLB_slots_three_phases=True,code_guard_bytes=65536,CSR_request_response_retire_verified=True,
        scoped_toggle_new_serialized_positions=948,target_new_serialized_positions=862,
        raw_delta=delta['metrics'],official_percentage_claimed=False,UVM_final_report_claimed=False,
        vector_workload_claimed=False,RTL_changed=False,new_simulation=False,
        native_hit_and_percentage_metadata_retained_not_recomputed=True,
        Toggle_gain_authority='Exact serialized bits OR and gained positions; not hit/percentage metadata')
    return {'combined-bits.json':after,'single-bits.json':single,'raw-delta.json':delta,
            'itlb-toggle-gain.json':gain,'elf-ledger-dedup.json':elf,'status.json':status,
            'evidence-pins.json':pins}, '\n'.join([ledger[0],*after['tests']])+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','verify','admit'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seal')
    parser.add_argument('--parent-authorized',action='store_true')
    args = parser.parse_args()
    require(args.parent_authorized == (args.mode=='admit'), 'Separate explicit parent authorization')
    out = args.output.absolute()
    require(out.parent==life.OUT and out.resolve()==out and (not out.exists() or args.mode=='verify'),
            'Fresh formal774 output')
    values, text = evaluate()
    outputs = {str(out/n):hashlib.sha256((json.dumps(v,indent=2)+'\n').encode()).hexdigest()
               for n,v in values.items()}
    outputs[str(out/'combined-inputs.txt')] = hashlib.sha256(text.encode()).hexdigest()
    record = out.with_name(out.name+'.prepared.json')
    proposal = dict(output=str(out),baseline=str(BASE),baseline_seal=BASE_SHA,
        qualification=str(QUAL/'qualification.json'),qualification_seal=QUAL_SHA,
        parent_replay=str(REPLAY/'qualification.json'),parent_replay_seal=REPLAY_SHA,
        input_pins=values['evidence-pins.json'],output_pins=outputs,coverage_admitted=False)
    if args.mode=='prepare':
        life.save(record,proposal);print('PREPARED774',record,life.digest(record),flush=True);return
    require(args.seal, 'Exact prepared/admitted seal required')
    if args.mode=='verify' and out.exists():
        m = life.read_bound(out/'admission-manifest.json',args.seal)
        require(m == dict(proposal,coverage_admitted=True,prepared=str(record),prepared_seal=m['prepared_seal'],
            authorization_source='EXPLICIT_PARENT_REPLAY_PASS_AND_ADMISSION_AUTHORIZATION') and
            life.read_bound(record,m['prepared_seal'])==proposal,'Exact admitted contract')
        life.check(outputs);print('FORMAL774_OFFLINE_REVERIFIED',flush=True);return
    require(life.read_bound(record,args.seal)==proposal,'Prepared contract drift')
    if args.mode=='verify':
        print('VERIFY_PASS_NO_ADMISSION',flush=True);return
    out.mkdir()
    for name,value in values.items():life.save(out/name,value)
    with (out/'combined-inputs.txt').open('x') as f:f.write(text)
    life.check(proposal['input_pins']);life.check(outputs)
    life.save(out/'admission-manifest.json',dict(proposal,coverage_admitted=True,prepared=str(record),
        prepared_seal=args.seal,authorization_source='EXPLICIT_PARENT_REPLAY_PASS_AND_ADMISSION_AUTHORIZATION'))
    print('ADMITTED774',out,life.digest(out/'admission-manifest.json'),flush=True)


if __name__=='__main__':main()
