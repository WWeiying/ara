"""Authorized exact760 ->761 append of the native-qualified MIN_SCALE slot15 case."""
import argparse
import copy
from pathlib import Path

import admit_qbs_affine_followups760 as previous
import qualify_qbs_affine_external_reset as q
from ara_verify import vector_commit as vc

life,require = q.life,q.require
BASE = life.OUT/'qbs-affine-min-scale-offline-admitted-760-agent-20261007-01'
BASE_SHA = '0b4ae9ddf332355cdbb02ff42f237487dd0857fa5872b86916bc5ac40b3b207e'
QUAL = life.OUT/'qbs-affine-min-slot15-qualified-760-agent-20261007-01'
QUAL_SHA = '46ac9d3363d12681196f4375440442fcabea79626315a86da3be854ea61b679b'
RUN = life.OUT/'qbs-affine-min-slot15-old-image-agent-20261007-02'
OUT = life.OUT/'qbs-affine-min-slot15-offline-admitted-761-agent-20261007-01'
PROOF = life.OUT/'qbs-remaining15-fsm-native-shape-parent-20261007-01.json'
SCHEMA = 'QBS_MIN_SLOT15_HISTORICAL761_NATIVE_ADMISSION_V1'


def contract(qual):
    wanted = dict(status='QBS_AFFINE_EXACT_RESET_REUSE_TWO_EPOCH_NATIVE_PASS_NOT_ADMITTED',
        baseline=760,stage='min_scale',recovery_full_vrf_bytes=8192,initial_seed_bytes=8192,
        CSR_values=24,source_guard_bytes=7840,native_active_bytes=512,checks=41,
        reset_stage_and_slot_reuse_wave_verified=True,full_scalar_ISA_verified=False,
        spike_custom_ISA_PASS=False,uvm_check_report_pass=False,coverage_admitted=False)
    require(all(type(qual.get(k)) is type(v) and qual[k] == v for k,v in wanted.items()),'Exact native qualification scope')
    require(qual['raw_delta'] == dict(line=0,cond=0,branch=0,fsm=15) and
            qual['targets'] == [dict(stage='min_scale',index=284,before=False,single=True)],'Exact15 MIN growth')


def normalized_bindings(audit):
    lanes,vlen,activities = vc._parse_vector_trace(QUAL/'epoch1/vector_trace.csv')
    require((lanes,vlen) == (4,1024),'Frozen vector configuration')
    bindings = copy.deepcopy(audit['bindings'])
    require(len(bindings) == 2,'Exactly two native commands')
    inputs = q.native()
    custom = {seq for seq,a in activities.items() if a.instruction == q.WORD}
    require(custom == {b['arch_seq'] for b in bindings},'Exact native command owners')
    for phase,binding in enumerate(bindings):
        activity = activities[binding['arch_seq']]
        require((activity.allocations,activity.completions,activity.vd,activity.eew,activity.vl,activity.vstart) ==
                (1,1,8,2,256,0) and activity.use_vd,'Actual full8 backend shape')
        expected = q.full8.custom_expected(inputs[phase])
        observed = vc._architectural_bytes(activity.writes,lanes,vlen)
        require({key:value[0] for key,value in observed.items()} == expected and len(expected) == 256,
                'Independent full8 golden write bytes differ')
        physical = [(w.lane,w.addr) for w in activity.writes]
        require(len(physical) == len(set(physical)) == 32 and
                set(physical) == {(lane,(8+c)*4) for lane in range(4) for c in range(8)} and
                all(w.be == w.known_be == 255 and w.source == 4 for w in activity.writes),
                'Exact nonduplicate full8 native writes')
        require(binding['backend_vl'] == binding['native_active_write_bytes'] == 160 and
                binding['native_total_write_bytes'] == 160 and binding['preserved_vrf_bytes'] == 3936,
                'Unexpected predecessor descriptive labels')
        binding.update(backend_vl=256,native_active_write_bytes=256,native_total_write_bytes=256,
                       preserved_vrf_bytes=3840)
    return dict(status='ACTUAL_FULL8_BYTES_REVERIFIED_INHERITED_M5_LABELS_CORRECTED',bindings=bindings,
                native_active_bytes=512,inherited_labels_preserved_in_original_qualification=True,
                original_qualification_seal=QUAL_SHA,full_scalar_ISA_verified=False)


def check():
    book = life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    require(book['schema'] == 'QBS_AFFINE_SERIAL_AFTER758_NATIVE_ADMISSION_V1' and
            book['output'] == str(BASE) and book['explicit_parent_authorized'] is True,'Formal760 identity')
    qual = life.read_bound(QUAL/'qualification.json',QUAL_SHA)
    contract(qual)
    pins = life.merge_pins(book['input_pins'],book['output_pins'])
    pins = life.merge_pins(pins,qual['output_pins'])
    pins = life.merge_pins(pins,life.read_bound(QUAL/'evidence-pins.json',pins[str(QUAL/'evidence-pins.json')]))
    pins = life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SHA,str(QUAL/'qualification.json'):QUAL_SHA})
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_qbs_min_slot15_761.py'),Path(previous.__file__).resolve()):
        pins = life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins)
    def read(path): return life.read_bound(path,pins[str(path)])
    state = read(BASE/'status.json')
    require(state['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and type(state['aggregate_passed']) is int and
            state['aggregate_passed'] == 760 and state['coverage_admitted'] is True,'Formal760 PASS only')
    before,single = read(BASE/'combined-bits.json'),read(QUAL/'single-bits.json')
    require(all(pins.get(path) == sha for path,sha in single['input_hashes'].items()),'Actual raw inputs unpinned')
    require((BASE/'combined-inputs.txt').read_text().splitlines() == [str(life.IMAGE)+'.vdb',*before['tests']],
            'Formal760 ledger mismatch')
    combined,delta = previous.merge(before,single,760,RUN/'code.vdb')
    require(delta == read(QUAL/'raw-delta.json') and delta['metrics'] == qual['raw_delta'],'Exact formal760 gain differs')
    proof = read(PROOF)
    missing = [18*i+14 for i in range(1,16)]
    require(proof['status'] == 'FORMAL760_COMPILED_FSM_REMAINING15_MIN_SCALE_ONLY' and
            [p['raw_position'] for p in proof['gaps']['missing']] == missing and
            all(p['name'] == 'FP_MIN_SCALE_MULTIPLY->FP_DOT_CONVERT' for p in proof['gaps']['missing']),
            'Parent native shape evidence differs')
    old,sample,new = [b['metrics']['fsm'][q.run.SCOPE] for b in (before,single,combined)]
    require((old['width'],old['checksum']) == (sample['width'],sample['checksum']) == (288,'3794445597'),
            'Exact accumulator compiled identity')
    zeros = [index for index in range(288) if not int(old['bits'],16)&(1<<(287-index))]
    gains = [index for index in range(288) if not int(old['bits'],16)&(1<<(287-index)) and int(sample['bits'],16)&(1<<(287-index))]
    require(zeros == gains == missing and int(new['bits'],16) == (1<<288)-1,'All15 exact MIN arcs must become hit')
    wave = read(QUAL/'full-slot-reset-reuse.json')
    window = read(QUAL/'reset-window.json')
    require(wave['pre_reset']['valid'] == '1'*16 and wave['pre_reset']['states'] == [3]*16 and
            window['full_clocks'] == 4 and window['actual_stage'] == 3 and window['guard'] == 1 and
            window['assertion_timestamp'] == wave['pre_reset']['time'] and
            window['release_timestamp'] == wave['release_timestamp'],'Exact sixteen-slot MIN reset window')
    require([item['slot'] for item in wave['reused_slots']] == list(range(16)) and
            all(item['retained_state'] == 3 and item['allocated_state'] == 0 and
                item['time'] > wave['release_timestamp'] for item in wave['reused_slots']),
            'Complete retained MIN -> DOT reuse')
    binding = read(QUAL/'wave-binding.json')
    require(binding['mda_index'] == binding['selected_guard_bit'] == 15 and binding['guard_width'] == 16,
            'Exact MDA15/packed bit15 binding')
    audits = read(QUAL/'epoch-audits.json')
    require(len(audits) == 2 and audits[0]['status'] == 'CANCELLED_FIRST_COMMAND_EXACT4SEEDS_NO_CUSTOM_WRITE_OR_COMPLETION' and
            audits[0]['seed_bytes_checked'] == 4096 and audits[1]['full_vrf_bytes'] == 8192 and
            audits[1]['source_guard_bytes'] == 7840 and audits[1]['csr_values'] == 24 and audits[1]['checks'] == 41,
            'Complete native cancellation/recovery gold required')
    events = read(QUAL/'independent-event-audit.json')
    require(events['cvx_epochs'] == [dict(requests=17,responses=17,aborted=0),dict(requests=51,responses=51,aborted=0)] and
            events['original_checker_status_preserved'] == 'FAIL' and events['UVM_report_claimed'] is False,
            'Exact independent transaction evidence')
    normalized = normalized_bindings(audits[1])
    status = dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',aggregate_passed=761,baseline=760,new_passed=1,
        exact760_prefix=True,full_OR_instances=6162,coverage_admitted=True,raw_delta=delta['metrics'],
        exact_MIN_transitions=missing,all16_MIN_snapshot_and_reuse_verified=True,
        independent_QBS_native_gold_and_reset_wave_PASS=True,full_scalar_ISA_verified=False,
        spike_custom_ISA_PASS=False,uvm_check_report_pass=False,original_uvm_checker_status_preserved=True,
        official_denominator_verified=False,rtl_changed=False,simulation_rerun=False)
    life.check(pins)
    return pins,{'combined-bits.json':combined,'single-bits.json':single,'raw-delta.json':delta,
                 'native-shape-label-review.json':normalized,'status.json':status}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent-authorized',action='store_true')
    p.add_argument('--verify-seal')
    a = p.parse_args()
    require(bool(a.parent_authorized) != bool(a.verify_seal),'One explicit mode')
    pins,values = check()
    ledger = '\n'.join([str(life.IMAGE)+'.vdb',*values['combined-bits.json']['tests']])+'\n'
    if a.verify_seal:
        m = life.read_bound(OUT/'admission-manifest.json',a.verify_seal)
        require(m['schema'] == SCHEMA and m['baseline_seal'] == BASE_SHA and m['qualification_seal'] == QUAL_SHA and
                m['input_pins'] == pins and m['output'] == str(OUT) and m['explicit_parent_authorized'] is True and
                set(m['output_pins']) == {str(OUT/name) for name in (*values,'combined-inputs.txt')},'Terminal manifest mismatch')
        life.check(m['output_pins'])
        for name,value in values.items():
            require(life.read_bound(OUT/name,m['output_pins'][str(OUT/name)]) == value,'Terminal independent replay mismatch')
        require((OUT/'combined-inputs.txt').read_text() == ledger,'Terminal prefix differs')
        print('QBS_MIN_SLOT15_761_REVERIFIED',a.verify_seal,flush=True)
        return
    require(not OUT.exists(),'Fresh formal output required')
    OUT.mkdir()
    for name,value in values.items(): life.save(OUT/name,value)
    with (OUT/'combined-inputs.txt').open('x') as stream: stream.write(ledger)
    life.check(pins)
    life.save(OUT/'admission-manifest.json',dict(schema=SCHEMA,output=str(OUT),baseline=str(BASE),baseline_seal=BASE_SHA,
        qualification=str(QUAL/'qualification.json'),qualification_seal=QUAL_SHA,input_pins=pins,
        output_pins={str(path):life.digest(path) for path in OUT.iterdir()},explicit_parent_authorized=True))
    print('QBS_MIN_SLOT15_761_ADMITTED',life.digest(OUT/'admission-manifest.json'),values['status.json']['raw_delta'],flush=True)


if __name__ == '__main__': main()
