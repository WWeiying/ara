"""Append one qualified Toggle-positive case to sealed740; no simulation or DVE."""
import argparse
import json
from pathlib import Path

import coverage_bitmap_delta as bitmap
import run_gap95_simulation as life
import targeted_toggle_evidence_v2 as toggle

OUT = life.OUT
BASE = OUT / 'queue-mask-offline-admitted-740-agent-20261007-01'
BASE_SHA = '752d493c5fa8179ddd414d7810da479b1a56341a1600dff56c5b5afa0a3304b5'
QUAL = OUT / 'gap113-payload-toggle-qualified-agent-20261007-01'
QUAL_SHA = '925fffaa27020ca24b697ad5f36cd5f74e813544ce3315a539df3c185cfdbd0b'
RAW = OUT / 'final-raw740-dve-prepared-agent-20261007-01/config.json'
RAW_SHA = '58d1dba6466a81fd256c5c2fa0a6f40d0bb9b22314119daa4b163909b47c29d0'
EVIDENCE = OUT / 'targeted-toggle740-gap113-20261007-01.json'
EVIDENCE_SHA = 'ed1e65f57321d38d52ae53a0d6525dbed8e45fd35416581f383ce5d4cffbadae'
VDB = OUT / 'gap113-payload-toggle-old-image-740-agent-20261007-01/code.vdb'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def exact_prefix(before, ledger):
    require(len(before) == len(set(before)) == 740, 'Not unique740')
    require(ledger[1:] == before and len(ledger) == 741, 'Raw740 ledger differs')
    require(str(VDB) not in before, 'Duplicate candidate')


def toggle_gain(evidence, sample):
    require(len(evidence['tests']) == 740, 'Not Toggle740')
    changes = toggle.gains(evidence['metrics'], toggle.union(evidence['metrics'], sample))
    return changes, sum(len(v) for v in changes.values())


def admit(out):
    require(out.parent == OUT and out.resolve() == out and not out.exists(), 'Fresh output required')
    base = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    before = life.read_bound(BASE / 'combined-bits.json', base['output_pins'][str(BASE / 'combined-bits.json')])
    state = life.read_bound(BASE / 'status.json', base['output_pins'][str(BASE / 'status.json')])
    require(state['aggregate_passed'] == 740 and state['coverage_admitted'] is True and
            state['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY', 'Not formally admitted740')
    raw = life.read_bound(RAW, RAW_SHA)
    require(raw['population'] == 740 and raw['waiver_mode'] == 'off', 'Not sealed raw740')
    exact_prefix(before['tests'], raw['input_ledger'])
    q = life.read_bound(QUAL / 'qualification.json', QUAL_SHA)
    require(q['status'] == 'GAP113_NATIVE_PASS_POSITIVE_SCOPED_TOGGLE_GAIN_NOT_ADMITTED' and
            q['full_scalar_isa_verified'] is False and q['spike_custom_isa_pass'] is False and
            q['coverage_admitted'] is False and q['rtl_changed'] is False, 'Not exact qualified custom case')
    qualified_pins = life.read_bound(QUAL / 'evidence-pins.json', q['output_pins'][str(QUAL / 'evidence-pins.json')])
    pins = life.merge_pins(raw['pins'], qualified_pins)
    pins = life.merge_pins(pins, q['output_pins'])
    anchors = {BASE / 'admission-manifest.json': BASE_SHA, RAW: RAW_SHA,
               QUAL / 'qualification.json': QUAL_SHA, EVIDENCE: EVIDENCE_SHA}
    for path in (BASE / 'combined-bits.json', BASE / 'status.json'):
        anchors[path] = base['output_pins'][str(path)]
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_admit_targeted_toggle741.py'),
                 Path(bitmap.__file__).resolve(), Path(life.__file__).resolve(),
                 Path(toggle.__file__).resolve(), Path(toggle.base.__file__).resolve()):
        anchors[path] = life.digest(path)
    pins = life.merge_pins(pins, {str(p): sha for p, sha in anchors.items()})
    life.check(pins)
    evidence = life.read_bound(EVIDENCE, EVIDENCE_SHA)
    require(evidence['tests'] == before['tests'], 'Scoped Toggle population differs')
    files = list((VDB / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(files) == 1 and files[0].parent.name == 'qbs_gap113_payload_toggle', 'Ambiguous candidate')
    sample, sha = toggle.rows(files[0], sorted(evidence['metrics']))
    require(qualified_pins[str(files[0])] == sha, 'Candidate data drift')
    changes, gain = toggle_gain(evidence, sample)
    recorded = life.read_bound(QUAL / 'toggle-gain.json', q['output_pins'][str(QUAL / 'toggle-gain.json')])
    require(gain == 2402 and changes == recorded['scopes'] and
            recorded['total_new_serialized_toggle_positions'] == gain, 'Measured gain differs')
    out.mkdir()
    try:
        single_inputs = out / 'single-inputs.txt'
        single_inputs.write_text(raw['input_ledger'][0] + '\n' + str(VDB) + '\n')
        single = bitmap.collect(single_inputs)
        combined = bitmap.combine(before, single)
        require(combined['tests'] == before['tests'] + [str(VDB)], 'Exact740 prefix not retained')
        delta = bitmap.delta(before, combined)
        # Recompute every OR independently of combine, including zero-gain metrics.
        positions = 0
        for metric, rows in before['metrics'].items():
            for scope, row in rows.items():
                observed = combined['metrics'][metric][scope]
                require(int(observed['bits'], 16) == int(row['bits'], 16) |
                        int(single['metrics'][metric][scope]['bits'], 16), 'OR differs')
                positions += 1
        require(positions == 6162, 'Frozen metric universe differs')
        inputs = raw['input_ledger'] + [str(VDB)]
        (out / 'combined-inputs.txt').write_text('\n'.join(inputs) + '\n')
        for name, value in (('single-bits.json', single), ('combined-bits.json', combined),
                            ('raw-delta.json', delta), ('scoped-toggle-gain.json', recorded)):
            life.save(out / name, value)
        pins = life.merge_pins(pins, single['input_hashes'])
        life.check(pins)
        status = dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', aggregate_passed=741,
            baseline=740, new_passed=1, exact740_prefix=True, full_OR_instances=positions,
            raw_delta=delta['metrics'], scoped_toggle_new_positions=gain, coverage_admitted=True,
            historical_fixed_image_only=True, new_RTL_signoff=False,
            whole_ISA_qualified=False, spike_custom_isa_pass=False, simulations_started=False,
            rtl_changed=False, official_denominator_verified=False)
        life.save(out / 'status.json', status)
        life.save(out / 'admission-manifest.json', dict(schema='TARGETED_TOGGLE741_ADMISSION_V1',
            output=str(out), baseline=str(BASE), baseline_seal=BASE_SHA,
            qualification=str(QUAL / 'qualification.json'), qualification_seal=QUAL_SHA,
            input_pins=pins, output_pins={str(p): life.digest(p) for p in out.iterdir() if p.is_file()},
            explicit_parent_authorized=True))
        print(json.dumps(status))
    except Exception as exc:
        life.save(out / 'failure.json', dict(status='ADMISSION_FAILED', reason=str(exc)))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--parent-authorized', action='store_true', required=True)
    args = parser.parse_args()
    admit(args.output.absolute())
