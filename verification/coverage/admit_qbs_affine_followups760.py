"""Exact758 -> SCALE759 -> MIN_SCALE760; no simulation or full-ISA claim."""
import argparse
from pathlib import Path

import qualify_qbs_affine_external_reset as q

life, require = q.life, q.require
BASE = life.OUT / 'fpu-reset-matrix-offline-admitted-758-agent-20261007-01'
BASE_SHA = '4ae911058627d23527a2b3cbe553de7e14674e95df74ca05c0c64faaf1491507'
CASES = (
    ('scale', 2, 16, '1469f00deae59d247f9d9eaa269209e3d649c2e75de82b1d1d6304cc7399a1a2',
     'qbs-affine-scale-qualified-agent-20261007-01',
     'qbs-affine-scale-external-reset-old-image-agent-20261007-01',
     'qbs-affine-scale-offline-admitted-759-agent-20261007-01'),
    ('min_scale', 3, 14, 'b8fba2fa4691f985337822f709d01accf36ef249f56c08fc314101c88af1e66e',
     'qbs-affine-min-scale-qualified-agent-20261007-01',
     'qbs-affine-min-scale-external-reset-old-image-agent-20261007-01',
     'qbs-affine-min-scale-offline-admitted-760-agent-20261007-01'),
)


def contract(qual, stage):
    wanted = dict(status='QBS_AFFINE_EXACT_RESET_REUSE_TWO_EPOCH_NATIVE_PASS_NOT_ADMITTED',
        baseline=746, stage=stage, recovery_full_vrf_bytes=8192, initial_seed_bytes=8192,
        CSR_values=24, source_guard_bytes=7840, native_active_bytes=512, checks=41,
        reset_stage_and_slot_reuse_wave_verified=True, full_scalar_ISA_verified=False,
        spike_custom_ISA_PASS=False, uvm_check_report_pass=False, coverage_admitted=False)
    require(all(type(qual.get(k)) is type(v) and qual[k] == v for k, v in wanted.items()),
            'Exact bounded native qualification required')
    require(qual['raw_delta'] == dict(line=0, cond=5, branch=0, fsm=16),
            'Historical746 diagnostic changed')


def merge(before, single, population, vdb):
    require(len(before['tests']) == len(set(before['tests'])) == population and
            single['tests'] == [str(vdb)] and str(vdb) not in before['tests'],
            'Population/duplicate singleton mismatch')
    require(set(before['metrics']) == set(single['metrics']) == set(q.bitmap.METRICS),
            'Four raw metrics required')
    after = q.bitmap.combine(before, single)
    count = 0
    for metric, rows in before['metrics'].items():
        require(set(rows) == set(single['metrics'][metric]), 'Missing/extra compiled scope')
        for scope, old in rows.items():
            sample, new = single['metrics'][metric][scope], after['metrics'][metric][scope]
            require((old['width'], old['checksum']) == (sample['width'], sample['checksum']) and
                    int(new['bits'], 16) == (int(old['bits'], 16) | int(sample['bits'], 16)),
                    'Independent shape/OR mismatch')
            count += 1
    require(count == 6162 and after['tests'] == before['tests'] + single['tests'] and
            len(set(after['tests'])) == population + 1, 'Incomplete OR/exact prefix')
    delta = q.bitmap.delta(before, after)
    require(sum(delta['metrics'].values()) > 0, 'Zero gain cannot be admitted')
    return after, delta


def inputs():
    book = life.read_bound(BASE/'admission-manifest.json', BASE_SHA)
    require(book['schema'] == 'FPU_MATRIX_AFTER747_FORMAL758_V1' and
            book['explicit_parent_authorized'] is True and book['output'] == str(BASE) and
            book['baseline_seal'] == '1c2de4bb109f450cb3365b7fe5b935d018af0340070c81743beb6c2dfafe3046',
            'Not sealed FPU-after-AUX758')
    pins = life.merge_pins(book['input_pins'], book['output_pins'])
    pins = life.merge_pins(pins, {str(BASE/'admission-manifest.json'): BASE_SHA})
    qualified = []
    for stage, code, index, sha, directory, run, output in CASES:
        directory = life.OUT/directory
        qual = life.read_bound(directory/'qualification.json', sha)
        contract(qual, stage)
        pins = life.merge_pins(pins, qual['output_pins'])
        evidence = life.read_bound(directory/'evidence-pins.json', qual['output_pins'][str(directory/'evidence-pins.json')])
        pins = life.merge_pins(pins, evidence)
        pins = life.merge_pins(pins, {str(directory/'qualification.json'): sha})
        qualified.append((directory, qual))
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_admit_qbs_affine_followups760.py')):
        pins = life.merge_pins(pins, {str(path): life.digest(path)})
    life.check(pins)
    def read(path):
        return life.read_bound(path, pins[str(path)])
    state = read(BASE/'status.json')
    require(state['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and
            type(state['aggregate_passed']) is int and state['aggregate_passed'] == 758 and
            state['coverage_admitted'] is True and state['exact747_prefix'] is True and
            state['new_passed'] == 11 and not state['excluded'], 'Formal758 not complete')
    before = read(BASE/'combined-bits.json')
    ledger = (BASE/'combined-inputs.txt').read_text().splitlines()
    require(ledger == [str(life.IMAGE)+'.vdb', *before['tests']], 'Exact758 input ledger')
    ancestor = Path(book['baseline'])
    prior = read(ancestor/'combined-bits.json')
    require(len(prior['tests']) == 747 and before['tests'][:747] == prior['tests'], '747 prefix changed')
    values = []
    for offset, (case, (directory, qual)) in enumerate(zip(CASES, qualified)):
        stage, code, index, sha, _, run, output = case
        single = read(directory/'single-bits.json')
        require(all(pins.get(path) == digest for path, digest in single['input_hashes'].items()),
                'Singleton raw input unpinned')
        window, reuse = read(directory/'reset-window.json'), read(directory/'slot-reuse.json')
        require(window['actual_stage'] == code and window['guard'] == 1 and window['full_clocks'] == 4 and
                reuse['retained_state'] == code and reuse['allocated_state'] == 0 and reuse['slot'] == 0,
                'Wrong reset-stage/slot reuse')
        audits = read(directory/'epoch-audits.json')
        require(len(audits) == 2 and audits[0]['seed_bytes_checked'] == 4096 and
                audits[1]['full_vrf_bytes'] == 8192 and audits[1]['custom_write_bytes'] == 512 and
                audits[1]['source_guard_bytes'] == 7840 and len(audits[1]['bindings']) == 2,
                'Native epoch coverage incomplete')
        old, sample = before['metrics']['fsm'][q.run.SCOPE], single['metrics']['fsm'][q.run.SCOPE]
        mask = 1 << (287-index)
        require((old['width'], old['checksum']) == (sample['width'], sample['checksum']) == (288, '3794445597') and
                not int(old['bits'],16) & mask and int(sample['bits'],16) & mask,
                'Exact fresh target not newly hit')
        after, delta = merge(before, single, 758+offset, life.OUT/run/'code.vdb')
        status = dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', aggregate_passed=759+offset,
            baseline=758+offset, new_passed=1, exact_prefix=True, full_OR_instances=6162,
            stage=stage, raw_delta=delta['metrics'], coverage_admitted=True,
            qualification_baseline=746, qualification_reused_without_relabeling=True,
            independent_QBS_native_gold_and_reset_wave_PASS=True, full_scalar_ISA_verified=False,
            spike_custom_ISA_PASS=False, uvm_check_report_pass=False,
            original_uvm_checker_status_preserved=True, official_denominator_verified=False,
            rtl_changed=False, simulation_rerun=False)
        values.append((life.OUT/output, directory, sha, dict(single=single, combined=after, delta=delta, status=status)))
        before = after
    life.check(pins)
    return pins, values


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent-authorized', action='store_true')
    p.add_argument('--check-only', action='store_true')
    p.add_argument('--verify', action='store_true')
    a = p.parse_args()
    require(sum((a.parent_authorized, a.check_only, a.verify)) == 1, 'Explicit mode required')
    pins, values = inputs()
    if a.check_only:
        print('QBS_FOLLOWUPS758_CHECK_PASS', [v[3]['status']['raw_delta'] for v in values], flush=True)
        return
    if a.verify:
        parent, parent_sha = BASE, BASE_SHA
        for out, qual, sha, data in values:
            manifest_path = out/'admission-manifest.json'
            manifest_sha = life.digest(manifest_path)
            manifest = life.read_bound(manifest_path, manifest_sha)
            require(manifest['schema'] == 'QBS_AFFINE_SERIAL_AFTER758_NATIVE_ADMISSION_V1' and
                    manifest['output'] == str(out) and manifest['baseline'] == str(parent) and
                    manifest['baseline_seal'] == parent_sha and manifest['qualification_seal'] == sha and
                    manifest['qualification'] == str(qual/'qualification.json') and
                    manifest['explicit_parent_authorized'] is True and manifest['input_pins'] == pins,
                    'Serial manifest binding mismatch')
            names = dict(single='single-bits.json', combined='combined-bits.json', delta='raw-delta.json', status='status.json')
            require(set(manifest['output_pins']) == {str(out/name) for name in (*names.values(), 'combined-inputs.txt')},
                    'Output inventory mismatch')
            life.check(manifest['output_pins'])
            for key, name in names.items():
                require(life.read_bound(out/name, manifest['output_pins'][str(out/name)]) == data[key],
                        'Terminal OR/status replay mismatch')
            require((out/'combined-inputs.txt').read_text().splitlines() ==
                    [str(life.IMAGE)+'.vdb', *data['combined']['tests']], 'Terminal exact prefix mismatch')
            pins = life.merge_pins(pins, dict(manifest['output_pins'], **{str(manifest_path): manifest_sha}))
            parent, parent_sha = out, manifest_sha
            print('QBS_SERIAL_REVERIFIED', out, parent_sha, flush=True)
        return
    require(all(not value[0].exists() for value in values), 'Fresh serial outputs required')
    parent, parent_sha = BASE, BASE_SHA
    for out, qual, sha, data in values:
        out.mkdir()
        names = dict(single='single-bits.json', combined='combined-bits.json', delta='raw-delta.json', status='status.json')
        for key, name in names.items(): life.save(out/name, data[key])
        with (out/'combined-inputs.txt').open('x') as stream:
            stream.write('\n'.join([str(life.IMAGE)+'.vdb', *data['combined']['tests']])+'\n')
        life.check(pins)
        life.save(out/'admission-manifest.json', dict(schema='QBS_AFFINE_SERIAL_AFTER758_NATIVE_ADMISSION_V1',
            output=str(out), baseline=str(parent), baseline_seal=parent_sha,
            qualification=str(qual/'qualification.json'), qualification_seal=sha,
            explicit_parent_authorized=True, input_pins=pins,
            output_pins={str(path):life.digest(path) for path in out.iterdir()}))
        parent, parent_sha = out, life.digest(out/'admission-manifest.json')
        pins = life.merge_pins(pins, {str(path):life.digest(path) for path in out.iterdir()})
        print('QBS_SERIAL_ADMITTED', out, parent_sha, data['status']['raw_delta'], flush=True)


if __name__ == '__main__': main()
