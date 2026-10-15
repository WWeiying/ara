"""Bind reduced baseline/fixed results and check that only lane RTL changed."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(out):
    sources = json.loads((out / 'sources.json').read_text())
    for relative, expected in sources.items():
        assert sha(out / 'snapshot' / relative) == expected, relative
    records = json.loads((out / 'status.json').read_text())
    for record in records:
        log = out / record['name'] / 'run.log'
        text = log.read_text()
        assert record['passed'] and record['returncode'] == 0, record
        assert 'Fatal:' not in text and 'Error-' not in text, log
        marker = 'EXPECTED_CURRENT_FAILURE' if record['expected_failure'] else 'PASS lane_mask'
        assert marker in text, log
        assert len(record['result']) == 1, record
        record['measurements'] = {
            key: int(value) for key, value in
            (pair.split('=') for pair in record['result'][0].split()[1:])}
        record['log_sha256'] = sha(log)
    return sources, records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--fixed', type=Path, required=True)
    args = parser.parse_args()
    before, baseline = inspect(args.baseline)
    after, fixed = inspect(args.fixed)
    assert before.keys() == after.keys()
    changed = [p for p in before if before[p] != after[p]]
    assert changed == ['hardware/src/lane/lane_sequencer.sv'], changed
    assert sha(args.baseline / 'snapshot/lane_mask_tb.sv') == sha(args.fixed / 'snapshot/lane_mask_tb.sv')
    assert sha(args.baseline / 'snapshot/lane_types.svh') == sha(args.fixed / 'snapshot/lane_types.svh')
    assert len(baseline) == 10 and sum(bool(r['expected_failure']) for r in baseline) == 4
    assert len(fixed) == 41 and not any(r['expected_failure'] for r in fixed)
    for out in (args.baseline, args.fixed):
        for case in ('compare_small', 'compare_boundary', 'mfpu_boundary'):
            assert (out / case / 'focused.fsdb').stat().st_size > 0
    result = dict(status='PASS_REDUCED_LANE_CONTRACTS', baseline=str(args.baseline.resolve()),
                  fixed=str(args.fixed.resolve()), only_changed_production_sources=changed,
                  lane_baseline_sha256=before[changed[0]], lane_fixed_sha256=after[changed[0]],
                  baseline_records=baseline, fixed_records=fixed,
                  original_programs_executed=False, full_board_closure=False,
                  notes=['ALU/MFPU, memory and slide cases outside compare test mask supply only.',
                         'Mask-logical and FP-compare cases check lane requests only.',
                         'Integer compare uses real VALU and MASKU with modeled post-queue data.',
                         'Raw mask/old-vd finite streams honor actual lane request origin/count.',
                         'No operand_requester, VRF bank arbitration, alias dependency or dispatcher.'])
    (args.fixed / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('status', 'only_changed_production_sources',
                                           'lane_baseline_sha256', 'lane_fixed_sha256')}))


if __name__ == '__main__':
    main()
