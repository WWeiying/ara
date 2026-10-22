#!/usr/bin/env python3
"""Compose reviewed case drafts on one completed corpus; never launch tests."""
import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'verification/coverage'))
import coverage_evidence as evidence

require = evidence.require


def merge_cases(drafts, prior_rows, pin):
    names = {row['name'] for row in prior_rows}
    hashes = {row['elf_sha256'] for row in prior_rows}
    result = []
    for path, draft in drafts:
        require(isinstance(draft.get('cases'), list) and draft['cases'], 'empty draft')
        for source in draft['cases']:
            item = copy.deepcopy(source)
            name = item['name']
            parts = name.split(':')
            require(len(parts) == 2 and parts[0] in ('rvv', 'app') and parts[1],
                    'invalid case name')
            require(parts[1] not in names, 'duplicate case or existing PASS')
            names.add(parts[1])
            require(type(item['timeout_s']) is int and 0 < item['timeout_s'] <= 600,
                    'case exceeds reviewed ten-minute budget')
            require(item.get('rationale') and item.get('targets') and item.get('source_audit'),
                    'missing coverage rationale, target or source audit')
            require(item.get('sources') and item.get('evidence') and item.get('precheck'),
                    'missing independent precheck inputs')
            digest = pin(item['binary'])
            require(digest not in hashes, 'duplicate or already covered ELF')
            hashes.add(digest)
            # The case's adapter owns its exact sealed file set. Bind drafts
            # at batch level rather than altering already reviewed case data.
            result.append(item)
    require(result, 'no new cases')
    return result


def baseline_inputs(proof, directory):
    checkpoint = proof.read(directory / 'checkpoint.json')
    collection = proof.read(directory / 'collection.json')
    require(checkpoint['coverage_status'] == 'COMPLETE' and
            collection['status'] in ('PASS', 'COMPLETE_WITH_FAILURES') and
            collection['passed'] == checkpoint['aggregate_passed'], 'unfinished baseline')
    for name in ('all-passed-outcomes.json', 'combined-bits.json'):
        path = directory / name
        proof.pin(path, collection['reports'][str(path)])
    rows = proof.read(directory / 'all-passed-outcomes.json')
    bits = proof.read(directory / 'combined-bits.json')
    require(len(rows) == collection['passed'] and len({r['name'] for r in rows}) == len(rows),
            'corpus count or unique membership differs')
    require(all(r['status'] == 'PASS' and r['passed_only'] and r['vdb_valid'] for r in rows),
            'baseline contains an unverified result')
    require(bits['tests'] == [r['vdb'] for r in rows], 'bitmap membership differs')
    return rows, bits


def compose(baseline, paths, output):
    require(not output.exists(), 'new selection file required')
    proof = evidence.Evidence()
    rows, bits = baseline_inputs(proof, baseline)
    drafts = [(path, proof.read(path)) for path in paths]

    def pin(path):
        resolved = proof.pin(path)
        return proof.files[str(resolved)]

    cases = merge_cases(drafts, rows, pin)
    for item in cases:
        for target in item['targets']:
            require(target.startswith('ara_tb.dut.i_ara_soc.i_system.') and any(
                scope == target or scope.startswith(target + '.')
                for metric in bits['metrics'].values() for scope in metric),
                'target outside measured product hierarchy')
    proof.pin(Path(__file__).resolve())
    result = {
        'status': 'COMPOSED_REQUIRES_CHECKED_ADMISSION',
        'baseline': str(baseline), 'baseline_bits': str(baseline / 'combined-bits.json'),
        'cases': cases,
        'composition': {'baseline_passed': len(rows), 'drafts': [str(p) for p in paths],
                        'files': proof.files, 'maximum_concurrent_workers': 8,
                        'case_limit_seconds': 600},
        'note': 'No simulation or precheck approval here. All case adapters and full '
                'historical admission must pass before the frozen runner launches; '
                'the batch adapter must expand composition.files into plan pins.'}
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--selection', required=True, action='append', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    baseline = args.baseline.resolve(strict=True)
    paths = [path.resolve(strict=True) for path in args.selection]
    output = args.output.resolve()
    require(baseline.parent == ROOT / 'verification/out' and
            output.parent == ROOT / 'verification/out', 'use local campaign outputs')
    require(len(paths) == len(set(paths)), 'duplicate draft path')
    result = compose(baseline, paths, output)
    print(f"COMPOSED ONLY: {len(result['cases'])} new cases; "
          f"{result['composition']['baseline_passed']} baseline PASS; {output}")


if __name__ == '__main__':
    main()
