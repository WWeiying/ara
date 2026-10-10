#!/usr/bin/env python3
"""Report-only recovery for the gap37 JSON integer-key comparison failure.

Both worker proofs passed. Preserve them and the frozen checker. Reconstruct
each proof, normalize ONLY the two fixed capture-offset key maps, then run
the unchanged checked aggregate exporter. No simulator or failed VDB replay.
"""
import argparse
import copy
import json
from pathlib import Path

import run_fence_rvfi_checked_extension as runner

full = runner.full
require = full.require
ROOT = full.ROOT
OUTPUT = ROOT / 'verification/out/gap37-control-current-20261004-01'
REASON = 'FENCE.T runtime proof replay differs'
FENCE = runner.legacy.NAME
CSR = runner.csr.NAME
SCRIPT = Path(__file__).resolve()
WRAPPER_HASH = '6bc48f2a3ddc84edc006d23710d521e6377af6f1a4e16614e52a32402ab298b0'
AUDITOR_HASH = 'bb07e115e1e09785d624717d648146fd974af340200997f7891308df8a886b2d'


def stored_form(proof):
    """The sole normalization permitted by the frozen proof's JSON schema."""
    result = copy.deepcopy(proof)
    require(result.get('schema') == 'fence-rvfi-elf-capture-controller-v1' and
            result.get('status') == 'PASS', 'wrong FENCE proof schema')
    rounds = result['commit_evidence']['rounds']
    require(len(rounds) == 2, 'two capture rounds required')
    for index, row in enumerate(rounds):
        require(row['round'] == index, 'wrong round identity')
        stores = row['checked_stores']
        require(all(type(key) is int for key in stores) and
                set(stores) == set(range(0, 520, 8)), 'wrong capture-offset key set')
        row['checked_stores'] = {str(key): value for key, value in stores.items()}
    return result


def validate(output, plan):
    require(output == OUTPUT, 'recovery is scoped to the stopped gap37 batch')
    require(plan.get('baseline_passed') == 638 and
            {c['name'] for c in plan['cases']} == {FENCE, CSR} and len(plan['cases']) == 2,
            'wrong producer case set')
    expected = {str(runner.SCRIPT): WRAPPER_HASH, str(Path(runner.rvfi.__file__)): AUDITOR_HASH}
    require(all(plan['files'].get(p) == h for p, h in expected.items()), 'wrong original checker')
    full.check(expected)
    records, pins = {}, {}
    for case in plan['cases']:
        name = case['name']
        outcome_path = output / 'outcomes' / (name + '.json')
        row = full.read(outcome_path)
        require(row['status'] == 'PASS' and row['passed_only'] and row['vdb_valid'] and
                not row['reused'] and row['returncode'] == 0,
                'worker did not independently pass: ' + name)
        full.check(row['files'])
        full.check(row['vdb_files'])
        report = output / 'results' / name / (
            'fence_runtime_audit.json' if name == FENCE else 'csr_runtime_audit.json')
        require(str(report) in row['files'], 'unbound worker proof')
        saved = full.read(report)
        require(saved.get('status') == 'PASS' and saved.get('files'), 'incomplete worker proof')
        require(all(row['files'].get(p) == h for p, h in saved['files'].items()),
                'worker proof file set differs')
        if name == FENCE:
            actual = runner.runtime_proof(output, plan, row, replay=True)
            require(saved != actual, 'original serialization failure no longer reproduced')
            require(stored_form(actual) == saved, 'difference is not only capture-offset JSON keys')
            require(json.loads(json.dumps(actual, allow_nan=False)) == saved,
                    'standard JSON roundtrip differs')
            records[name] = {'status': 'PASS', 'original_mismatch_reproduced': True,
                             'allowed_difference': 'two 65-entry int-to-decimal-string key maps',
                             'all_values_and_other_fields_identical': True}
        else:
            require(runner.csr.runtime_proof(output, plan, row) == saved, 'CSR proof replay differs')
            records[name] = {'status': 'PASS', 'exact_proof_replay': True}
        pins.update(full.pins([outcome_path, report]))
        pins.update(row['files'])
        pins.update(row['vdb_files'])
    full.check(pins)
    return {'status': 'PASS', 'schema': 'gap37-json-offset-keys-only-v1', 'cases': records,
            'new_simulations': 0, 'worker_results_changed': False, 'files': pins}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve(strict=True)
    require(output == OUTPUT, 'unexpected output')
    state = full.read(output / 'checkpoint.json')
    require(state['status'] == 'STOPPED' and state['reason'] == REASON and
            state['counts'] == {'PASS': 2} and state['coverage_status'] == 'PENDING',
            'not the exact stopped postprocessing failure')
    require(not (output / 'combined-dve').exists() and not (output / 'collection.json').exists(),
            'do not overwrite any aggregate report')
    recovery = output / 'json-key-finalization-01'
    recovery.mkdir(exist_ok=False)
    full.save(recovery / 'original-checkpoint.json', state)
    own = full.pins([SCRIPT, ROOT / 'verification/tests/test_gap37_finalization.py'])
    full.save(recovery / 'finalizer-source-hashes.json', own)
    try:
        plan = runner.checked.frozen(output, all_cases=True)
        proof = validate(output, plan)
        full.save(recovery / 'admission.json', proof)
        print('CHECKED: two independent worker PASS; exact JSON key-only recovery; no VCS', flush=True)
        outcomes = runner.legacy.ORIGINAL_SUMMARIZE(output, plan)
        require(all(r['status'] == 'PASS' for r in outcomes), 'unexpected aggregate outcome')
        runner.checked.frozen(output, all_cases=True)
        full.check(proof['files'])
        full.check(own)
        record = output / 'collection.json'
        collection = full.read(record)
        require(collection['status'] == 'PASS' and collection['passed'] == 640, 'wrong aggregate count')
        collection['reports'].update(full.pins([
            recovery / 'admission.json', recovery / 'original-checkpoint.json',
            recovery / 'finalizer-source-hashes.json']))
        collection['postprocessing_recovery'] = str(recovery / 'admission.json')
        full.save(record, collection)
        state.pop('reason')
        state.update(status='PASS', phase='complete', coverage_status='COMPLETE',
                     aggregate_passed=640, postprocessing_recovery=str(recovery))
        full.save(output / 'checkpoint.json', state)
        print('COMPLETE: 640 independently checked PASS VDBs; original worker proofs preserved', flush=True)
    except Exception as error:
        full.save(recovery / 'failure.json', {'status': 'REJECTED',
                  'reason': f'{type(error).__name__}: {error}'})
        raise


if __name__ == '__main__':
    main()
