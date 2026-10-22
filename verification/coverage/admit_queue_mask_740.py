"""One authorized offline queue admission; exact formal739 plus sealed qualification."""
import argparse
import json
from pathlib import Path

import qualify_queue_mask_source_lifetime_terminal as q

life, require, bitmap = q.life, q.require, q.bitmap
BASE = life.OUT / 'csr-frozen-counter-offline-admitted-739-parent-20261007-01'
BASE_SEAL = '0ad9267a071b8019f758e8fe312c7b696bf977a1136f48474f65a39c2b81ffea'
QUAL = life.OUT / 'queue-mask-terminal-qualified-parent-20261007-01/qualification.json'
QUAL_SEAL = '151ebeebf999310d07a3ee1af35f3eba2b024e5557bb9a32a92c797da3bc046a'
Q_SHA = 'f93661afc656e0c55f39a0038aa67d4a465b065d44ef31093d9a6467a0442743'
DIAG = life.OUT / 'queue-mask-source-lifetime-raw-diagnostic-738-agent-20261007-01.json'
DIAG_SEAL = 'd9c583eae9e1f7229b825b0fd54f778ed6197589cf9585168d75c096c757a0e5'
DESIGN = Path(str(life.IMAGE) + '.vdb')


def union(before, single):
    require(len(before['tests']) == len(set(before['tests'])) == 739 and
            len(single['tests']) == 1 and single['tests'][0] not in before['tests'], 'Exact739 plus unique singleton required')
    for data in (before, single):
        require(set(data['metrics']) == set(bitmap.METRICS) and
                sum(len(r) for r in data['metrics'].values()) == 6162, 'Full6162 required')
        require(bool(data['input_hashes']), 'Nonempty raw provenance required')
        for rows in data['metrics'].values():
            for row in rows.values():
                require(type(row['width']) is int and row['width'] >= 0 and
                        0 <= int(row['bits'], 16) < 1 << row['width'], 'Malformed bitmap')
    life.merge_pins(before['input_hashes'], single['input_hashes'])
    combined = bitmap.combine(before, single)
    require(combined['tests'] == before['tests'] + single['tests'] and
            len(set(combined['tests'])) == 740, 'Exact739prefix lost')
    for metric, rows in before['metrics'].items():
        for scope, row in rows.items():
            require(int(combined['metrics'][metric][scope]['bits'], 16) ==
                    int(row['bits'], 16) | int(single['metrics'][metric][scope]['bits'], 16), 'Full OR differs')
    delta = bitmap.delta(before, combined)
    require(delta['metrics'] == dict(line=0, cond=4, branch=0, fsm=0), 'Expected actual four fresh arbitration points required')
    return combined, delta


def evaluate():
    require(life.digest(Path(q.__file__)) == Q_SHA, 'Frozen collector changed')
    proof = life.read_bound(QUAL, QUAL_SEAL)
    for key, value in dict(status='QUEUE_MASK_FULL_TERMINAL_PASS_NOT_ADMITTED', checks=6936,
            strict_memory_bytes=6912, csr_values=24, primary_native_writers=32, mask_active_bits=720,
            mask_tail_set_bits=7472, UVM_errors=0, OS_returncode=0, all_primary_hit=False,
            coverage_admitted=False, raw_gain_collected=False, whole_ISA_qualified=False).items():
        require(proof.get(key) == value, 'Exact qualification differs: ' + key)
    base = life.read_bound(BASE / 'admission-manifest.json', BASE_SEAL)
    diag = life.read_bound(DIAG, DIAG_SEAL)
    pins = life.merge_pins(proof['pins'], life.merge_pins(base['input_pins'], base['output_pins']))
    pins = life.merge_pins(pins, diag['pins'])
    pins = life.merge_pins(pins, {str(QUAL): QUAL_SEAL, str(BASE / 'admission-manifest.json'): BASE_SEAL,
        str(DIAG): DIAG_SEAL, str(Path(__file__).resolve()): life.digest(Path(__file__)),
        str(Path(__file__).with_name('test_admit_queue_mask_740.py')):
            life.digest(Path(__file__).with_name('test_admit_queue_mask_740.py'))})
    life.check(pins)
    require(base['output'] == str(BASE), 'Baseline owner differs')
    before = life.read_bound(BASE / 'combined-bits.json', pins[str(BASE / 'combined-bits.json')])
    state = life.read_bound(BASE / 'status.json', pins[str(BASE / 'status.json')])
    require(state['aggregate_passed'] == 739 and state['coverage_admitted'] is True and
            state['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY', 'Formal739 required')
    require((BASE / 'combined-inputs.txt').read_text().splitlines() == [str(DESIGN), *before['tests']], 'Baseline input order differs')
    inputs = QUAL.parent / 'singleton-inputs.txt'
    lines = inputs.read_text().splitlines()
    require(len(lines) == 2 and lines[0] == str(DESIGN), 'Exact singleton input list required')
    run = Path(lines[1]).parent
    require(run.name == 'queue-mask-source-lifetime-old-image-738-agent-20261006-01', 'Exact run owner required')
    record = life.read_bound(run.with_name(run.name + '.prepared.json'),
        'b45a190d4441fe9c4573aadad51dcd3a670679ff1281fd2bea76a930e4b31d7c')
    require(record == q.runner.manifest(run), 'Frozen run contract differs')
    q.terminal(life.read_bound(run / 'simulation-status.json', pins[str(run / 'simulation-status.json')]),
        life.read_bound(run / 'manifest.json', pins[str(run / 'manifest.json')]),
        life.read_bound(run / 'started.json', pins[str(run / 'started.json')]), record)
    single = bitmap.collect(inputs)
    for relative, sha in single['design'].items():
        require(life.digest(DESIGN / 'snps/coverage/db' / relative) == sha and
                pins.get(str(DESIGN / 'snps/coverage/db' / relative)) == sha, 'Unpinned design shape')
    require(single['tests'] == [str(run / 'code.vdb')] and
            all(pins.get(k) == v for k, v in single['input_hashes'].items()), 'Unpinned singleton metric')
    combined, delta = union(before, single)
    points = []
    for t in diag['new_points']:
        scope = t['scope']; row = before['metrics']['cond'][scope]; add = single['metrics']['cond'][scope]
        require((row['width'], row['checksum']) == (166, '845025520') and
                t['point']['raw_index'] == 135 and t['point']['vector'] == '110', 'Exact compiled point differs')
        mask = 1 << (166 - 1 - 135)
        require(not int(row['bits'], 16) & mask and int(add['bits'], 16) & mask, 'Arbitration point no longer fresh')
        points.append(dict(t, before739=False, single_hit=True, union_hit=True))
    require(len(points) == len({t['scope'] for t in points}) == 4, 'Four distinct lanes required')
    primary = life.read_bound(QUAL.parent / 'actual-target-hits.json', pins[str(QUAL.parent / 'actual-target-hits.json')])
    require(len(primary) == 4 and all(t['raw_index'] == 665 and t['actual_hit'] is False for t in primary), 'Preserve primary miss')
    products = {'single-bits.json': single, 'combined-bits.json': combined, 'raw-delta.json': delta,
        'target-hits.json': points, 'primary-target-misses.json': primary, 'evidence-pins.json': pins,
        'status.json': dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', baseline=739, aggregate_passed=740,
            new_passed=1, case=q.runner.NAME, coverage_admitted=True, exact739_prefix=True,
            full_OR_instances=6162, raw_delta=delta['metrics'], original_primary_targets_hit=0,
            alternative_arbitration_points_hit=4, qualification=str(QUAL), qualification_seal=QUAL_SEAL,
            checks=6936, strict_memory_bytes=6912, csr_values=24, primary_native_writers=32,
            historical_fixed_image_only=True, official_denominator_verified=False, new_RTL_signoff=False,
            native_cycle_qualified=False, whole_ISA_qualified=False, simulations_started=False, rtl_changed=False)}
    return products, '\n'.join([str(DESIGN), *combined['tests']]) + '\n'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=('admit', 'verify'))
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--seal'); ap.add_argument('--parent-authorized', action='store_true')
    a = ap.parse_args(); out = a.output.absolute()
    require(out.parent == life.OUT and out.resolve() == out, 'Direct output required')
    require((a.mode == 'admit') == a.parent_authorized and (a.mode == 'verify') == bool(a.seal), 'Explicit one-shot authorization required')
    require(not out.exists() if a.mode == 'admit' else out.is_dir(), 'Fresh admission / existing verification required')
    products, text = evaluate()
    if a.mode == 'admit':
        out.mkdir()
        for name, value in products.items(): life.save(out / name, value)
        (out / 'combined-inputs.txt').write_text(text)
        outputs = {str(f): life.digest(f) for f in out.iterdir() if f.is_file()}
        life.save(out / 'admission-manifest.json', dict(schema='QUEUE_MASK_HISTORICAL740_ADMISSION_V1',
            output=str(out), baseline=str(BASE), baseline_seal=BASE_SEAL, qualification=str(QUAL),
            qualification_seal=QUAL_SEAL, input_pins=products['evidence-pins.json'], output_pins=outputs,
            explicit_parent_authorized=True))
        print(json.dumps(dict(output=str(out), seal=life.digest(out / 'admission-manifest.json'), aggregate_passed=740)))
    else:
        m = life.read_bound(out / 'admission-manifest.json', a.seal)
        require(m['output'] == str(out) and m['baseline_seal'] == BASE_SEAL and m['qualification_seal'] == QUAL_SEAL
                and m['input_pins'] == products['evidence-pins.json'], 'Admission identity differs')
        life.check(m['output_pins'])
        for name, value in products.items(): require(json.loads((out / name).read_text()) == value, 'Actual product differs: ' + name)
        require((out / 'combined-inputs.txt').read_text() == text, 'Actual prefix differs')
        print('QUEUE_MASK_HISTORICAL740_FULL6162_VERIFY_PASS')


if __name__ == '__main__': main()
