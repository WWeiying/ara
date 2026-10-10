"""Append the sealed eleven FPU qualifications to authoritative747, without EDA."""
import argparse
from pathlib import Path
import qualify_fpu_reset_matrix as q

life, require = q.life, q.require
BASE = life.OUT / 'qbs-affine-aux-offline-admitted-747-agent-20261007-01'
BASE_SHA = '1c2de4bb109f450cb3365b7fe5b935d018af0340070c81743beb6c2dfafe3046'
FPU_SHA = '032c68ca480d8518f4357f48b367e1fc6e2377104292629944b2952985752a84'
OUT = life.OUT / 'fpu-reset-matrix-offline-admitted-758-agent-20261007-01'


def append(before, singles):
    require(len(before['tests']) == len(set(before['tests'])) == 747, 'Authoritative unique747 required')
    result = before
    for single in singles:
        require(len(single['tests']) == 1 and single['tests'][0] not in result['tests'], 'Duplicate/new VDB differs')
        require(single['design'] == before['design'] and set(single['metrics']) == set(before['metrics']) and
                all(set(single['metrics'][m]) == set(rows) for m, rows in before['metrics'].items()),
                'Compiled design/metric universe differs')
        result = q.shared.coverage.bitmap.combine(result, single)
    count = 0
    for metric, rows in before['metrics'].items():
        for scope, old in rows.items():
            bits = int(old['bits'], 16)
            for single in singles:
                row = single['metrics'][metric][scope]
                require((old['width'], old['checksum']) == (row['width'], row['checksum']), 'Native identity differs')
                bits |= int(row['bits'], 16)
            require(int(result['metrics'][metric][scope]['bits'], 16) == bits, 'Independent full OR differs')
            count += 1
    require(count == 6162 and result['tests'] == before['tests'] + [s['tests'][0] for s in singles] and
            len(result['tests']) == len(set(result['tests'])) == 747 + len(singles), 'Full OR/exact747 prefix differs')
    return result


def evaluate():
    base = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    require(base['schema'] == 'QBS_AFFINE_AUX747_NATIVE_ADMISSION_V1' and base['output'] == str(BASE) and
            base['baseline'] == str(q.matrix.BASE) and base['baseline_seal'] == q.matrix.BASE_SHA and
            base['explicit_parent_authorized'] is True, 'Formal747 origin differs')
    fpu = life.read_bound(q.ADMIT / 'admission-manifest.json', FPU_SHA)
    q.verify(FPU_SHA)
    pins = life.merge_pins(base['input_pins'], base['output_pins'])
    pins = life.merge_pins(pins, fpu['input_pins']); pins = life.merge_pins(pins, fpu['output_pins'])
    pins = life.merge_pins(pins, {str(BASE / 'admission-manifest.json'): BASE_SHA,
                                 str(q.ADMIT / 'admission-manifest.json'): FPU_SHA})
    for p in (Path(__file__).resolve(), Path(__file__).with_name('test_admit_fpu_matrix_after747.py')):
        pins = life.merge_pins(pins, {str(p): life.digest(p)})
    life.check(pins)
    def read(path):
        return life.read_bound(path, pins[str(path)])
    before = read(BASE / 'combined-bits.json'); prior = read(q.matrix.BASE / 'combined-bits.json')
    status = read(BASE / 'status.json')
    require(status['coverage_admitted'] is True and status['aggregate_passed'] == 747 and status['baseline'] == 746,
            'Formal747 status differs')
    # Independently preserve the already-admitted AUX test and its full native OR.
    aux = read(BASE / 'single-bits.json')
    require(q.merge(prior, [aux]) == before and before['tests'][:746] == prior['tests'] and
            q.shared.coverage.all_delta(prior, before)['metrics'] == dict(line=0, cond=5, branch=0, fsm=1),
            '747 exact746 prefix/AUX OR differs')
    require((BASE / 'combined-inputs.txt').read_text().splitlines() == [str(q.shared.coverage.DESIGN)] + before['tests'],
            'Exact747 input ledger differs')
    fpu_status = read(q.ADMIT / 'status.json')
    require(len(fpu_status['accepted']) == 11 and not fpu_status['excluded'] and fpu_status['aggregate_passed'] == 757,
            'Sealed eleven PASS qualifications required')
    plan = life.read_bound(q.matrix.PLAN, q.SEAL)
    singles = []
    for row, record in zip(fpu_status['accepted'], plan['cases']):
        require(row['case'] == record['case'], 'Qualification order/case differs')
        path = Path(row['qualification']); qual = life.read_bound(path, row['seal'])
        require(qual['baseline'] == 746 and qual['sew'] == record['sew'] and qual['stage'] == record['stage'] and
                qual['status'] == 'MATRIX_CASE_WAVE_ARCHITECTURE_PASS_NOT_ADMITTED', 'Stage/SEW qualification differs')
        single = read(path.parent / 'single-bits.json')
        require(single['tests'] == [str(Path(record['output']) / 'code.vdb')] and
                all(pins.get(p) == sha for p, sha in single['input_hashes'].items()), 'Unbound qualified singleton')
        singles.append(single)
    combined = append(before, singles); delta = q.shared.coverage.all_delta(before, combined)
    require(sum(delta['metrics'].values()) > 0, 'No fresh coverage against747')
    status = dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', aggregate_passed=758, baseline=747, new_passed=11,
        exact747_prefix=True, full_OR_instances=6162, raw_delta=delta['metrics'], coverage_admitted=True,
        qualification_baseline=746, qualification_reused_without_relabeling=True,
        accepted=fpu_status['accepted'], excluded=[], independent_external_reset_wave_and_architecture_pass=True,
        uvm_check_report_pass=False, missing_uvm_summary_preserved=True, official_denominator_verified=False,
        rtl_changed=False, simulation_rerun=False, inherited_QBS_bounded_qualification_not_full_scalar_ISA=True,
        supersedes_fpu_746_branch_for_population=True)
    life.check(pins)
    return pins, {'combined-bits.json': combined, 'raw-delta.json': delta, 'status.json': status}, \
        '\n'.join([str(q.shared.coverage.DESIGN)] + combined['tests']) + '\n'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent-authorized', action='store_true'); p.add_argument('--verify-seal')
    a = p.parse_args(); require(bool(a.parent_authorized) != bool(a.verify_seal), 'One exact offline mode required')
    pins, values, ledger = evaluate()
    if a.verify_seal:
        manifest = life.read_bound(OUT / 'admission-manifest.json', a.verify_seal)
        require(manifest['schema'] == 'FPU_MATRIX_AFTER747_FORMAL758_V1' and manifest['input_pins'] == pins and
                manifest['baseline_seal'] == BASE_SHA and manifest['FPU_qualification_population_seal'] == FPU_SHA and
                manifest['output'] == str(OUT) and manifest['explicit_parent_authorized'] is True and
                set(manifest['output_pins']) == {str(OUT / n) for n in (*values, 'combined-inputs.txt')},
                'Admission manifest replay differs')
        life.check(manifest['output_pins'])
        for name, value in values.items():
            require(life.read_bound(OUT / name, manifest['output_pins'][str(OUT / name)]) == value, 'Output replay differs')
        require((OUT / 'combined-inputs.txt').read_text() == ledger, 'Ledger replay differs')
        print('FPU_MATRIX758_OFFLINE_REVERIFIED ' + a.verify_seal, flush=True); return
    require(not OUT.exists(), 'Fresh successor output required'); OUT.mkdir()
    for name, value in values.items():
        life.save(OUT / name, value)
    with (OUT / 'combined-inputs.txt').open('x') as stream:
        stream.write(ledger)
    life.check(pins)
    life.save(OUT / 'admission-manifest.json', dict(schema='FPU_MATRIX_AFTER747_FORMAL758_V1', output=str(OUT),
        baseline=str(BASE), baseline_seal=BASE_SHA, FPU_qualification_population_seal=FPU_SHA,
        input_pins=pins, output_pins={str(p): life.digest(p) for p in OUT.iterdir()}, explicit_parent_authorized=True))
    print('FPU_MATRIX758_ADMITTED ' + life.digest(OUT / 'admission-manifest.json') + ' ' +
          str(values['raw-delta.json']['metrics']), flush=True)


if __name__ == '__main__':
    main()
