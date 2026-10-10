"""Authorized formal746 exact-prefix native affine AUX qualification admission."""
import argparse
from pathlib import Path
import qualify_qbs_affine_external_reset as q

life, require = q.life, q.require
QUAL = life.OUT / 'qbs-affine-aux-qualified-746-agent-20261007-03'
QUAL_SHA = '22f3b7f7f359c3955f536fdd119d160c12338deab88b3fe51296f92d6989277d'
RUN = life.OUT / 'qbs-affine-aux-external-reset-old-image-745-agent-20261007-01'
OUT = life.OUT / 'qbs-affine-aux-offline-admitted-747-agent-20261007-01'


def merge(before, single):
    require(len(before['tests']) == len(set(before['tests'])) == 746 and
            single['tests'] == [str(RUN / 'code.vdb')] and single['tests'][0] not in before['tests'],
            'Exact746 plus unique singleton required')
    require(set(before['metrics']) == set(single['metrics']) == set(q.bitmap.METRICS), 'Four raw metric inventory')
    combined = q.bitmap.combine(before, single)
    count = 0
    for metric, scopes in before['metrics'].items():
        require(set(scopes) == set(single['metrics'][metric]), 'Missing/extra native shape scope')
        for scope, old in scopes.items():
            sample, after = single['metrics'][metric][scope], combined['metrics'][metric][scope]
            require((old['width'], old['checksum']) == (sample['width'], sample['checksum']) and
                    int(after['bits'], 16) == (int(old['bits'], 16) | int(sample['bits'], 16)), 'Independent exact OR differs')
            count += 1
    require(count == 6162 and combined['tests'] == before['tests'] + single['tests'] and
            len(set(combined['tests'])) == 747, 'Complete6162 OR /747 prefix differs')
    return combined


def qualification_contract(qual):
    wanted = dict(status='QBS_AFFINE_EXACT_RESET_REUSE_TWO_EPOCH_NATIVE_PASS_NOT_ADMITTED', baseline=746,
        stage='aux', recovery_full_vrf_bytes=8192, initial_seed_bytes=8192, CSR_values=24,
        source_guard_bytes=7840, native_active_bytes=512, checks=41,
        reset_stage_and_slot_reuse_wave_verified=True, full_scalar_ISA_verified=False,
        spike_custom_ISA_PASS=False, uvm_check_report_pass=False, coverage_admitted=False)
    require(all(type(qual.get(k)) is type(v) and qual[k] == v for k,v in wanted.items()), 'Native qualification scope differs')
    require(qual['raw_delta'] == dict(line=0, cond=5, branch=0, fsm=1), 'Fresh positive gain differs')


def check():
    book = life.read_bound(q.BASE / 'admission-manifest.json', q.BASE_SHA)
    qual = life.read_bound(QUAL / 'qualification.json', QUAL_SHA)
    qualification_contract(qual)
    pins = life.merge_pins(book['input_pins'], book['output_pins'])
    pins = life.merge_pins(pins, qual['output_pins'])
    pins = life.merge_pins(pins, life.read_bound(QUAL / 'evidence-pins.json', pins[str(QUAL / 'evidence-pins.json')]))
    pins = life.merge_pins(pins, {str(q.BASE / 'admission-manifest.json'): q.BASE_SHA,
                                str(QUAL / 'qualification.json'): QUAL_SHA})
    for p in (Path(__file__).resolve(), Path(__file__).with_name('test_admit_qbs_affine_aux747.py')):
        pins = life.merge_pins(pins, {str(p): life.digest(p)})
    life.check(pins)
    def read(path):
        return life.read_bound(path, pins[str(path)])
    state = read(q.BASE / 'status.json')
    require(state['aggregate_passed'] == 746 and state['coverage_admitted'] is True and
            state['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY', 'Formal746 required')
    before, single = read(q.BASE / 'combined-bits.json'), read(QUAL / 'single-bits.json')
    require(all(pins.get(path) == sha for path,sha in single['input_hashes'].items()), 'Singleton raw input not bound')
    inputs = (q.BASE / 'combined-inputs.txt').read_text().splitlines()
    require(inputs == [str(life.IMAGE) + '.vdb', *before['tests']], 'Formal ledger mismatch')
    combined = merge(before, single)
    delta = q.bitmap.delta(before, combined)
    require(delta == read(QUAL / 'raw-delta.json') and delta['metrics'] == qual['raw_delta'], 'Measured OR/delta differs')
    window, reuse = read(QUAL / 'reset-window.json'), read(QUAL / 'slot-reuse.json')
    require(window['actual_stage'] == 1 and window['full_clocks'] == 4 and
            reuse['retained_state'] == 1 and reuse['allocated_state'] == 0 and reuse['slot'] == 0,
            'Exact AUX retained-state -> DOT waveform differs')
    audits = read(QUAL / 'epoch-audits.json')
    require(len(audits) == 2 and audits[0]['seed_bytes_checked'] == 4096 and
            audits[1]['custom_write_bytes'] == 512 and audits[1]['source_guard_bytes'] == 7840 and
            audits[1]['full_vrf_bytes'] == 8192 and len(audits[1]['bindings']) == 2, 'Incomplete native epochs')
    life.check(pins)
    status = dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', aggregate_passed=747, baseline=746,
        new_passed=1, exact746_prefix=True, unique_new_vdb=True, full_OR_instances=6162,
        raw_delta=delta['metrics'], coverage_admitted=True, independent_QBS_native_gold_and_reset_wave_PASS=True,
        full_scalar_ISA_verified=False, spike_custom_ISA_PASS=False, uvm_check_report_pass=False,
        original_uvm_checker_status_preserved=True, official_denominator_verified=False, rtl_changed=False,
        simulation_rerun=False)
    return pins, {'single-bits.json':single, 'combined-bits.json':combined, 'raw-delta.json':delta,
                  'status.json':status}, inputs + single['tests']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent-authorized', action='store_true')
    parser.add_argument('--verify-seal')
    args = parser.parse_args()
    require(bool(args.parent_authorized) != bool(args.verify_seal), 'Exactly one explicit mode')
    pins, values, inputs = check()
    texts = {'combined-inputs.txt':'\n'.join(inputs)+'\n',
             'single-inputs.txt':str(life.IMAGE)+'.vdb\n'+str(RUN/'code.vdb')+'\n'}
    if args.verify_seal:
        manifest = life.read_bound(OUT / 'admission-manifest.json', args.verify_seal)
        require(manifest['input_pins'] == pins and manifest['baseline_seal'] == q.BASE_SHA and
                manifest['qualification_seal'] == QUAL_SHA and manifest['schema'] == 'QBS_AFFINE_AUX747_NATIVE_ADMISSION_V1' and
                manifest['explicit_parent_authorized'] is True and manifest['output'] == str(OUT), 'Manifest replay mismatch')
        require(set(manifest['output_pins']) == {str(OUT/name) for name in (*values, *texts)}, 'Output inventory differs')
        life.check(manifest['output_pins'])
        for name, value in values.items():
            require(life.read_bound(OUT/name, manifest['output_pins'][str(OUT/name)]) == value, 'OR replay differs')
        for name, value in texts.items():
            require((OUT/name).read_text() == value, 'Prefix replay differs')
        print('QBS_AFFINE_AUX747_OFFLINE_REVERIFIED ' + args.verify_seal)
        return
    require(not OUT.exists(), 'Fresh formal output required')
    OUT.mkdir()
    for name, value in values.items(): life.save(OUT/name, value)
    for name, value in texts.items():
        with (OUT/name).open('x') as stream: stream.write(value)
    life.check(pins)
    life.save(OUT/'admission-manifest.json', dict(schema='QBS_AFFINE_AUX747_NATIVE_ADMISSION_V1',
        output=str(OUT), baseline=str(q.BASE), baseline_seal=q.BASE_SHA,
        qualification=str(QUAL/'qualification.json'), qualification_seal=QUAL_SHA,
        input_pins=pins, output_pins={str(p):life.digest(p) for p in OUT.iterdir()}, explicit_parent_authorized=True))
    print('QBS_AFFINE_AUX747_ADMITTED ' + life.digest(OUT/'admission-manifest.json'), flush=True)


if __name__ == '__main__': main()
