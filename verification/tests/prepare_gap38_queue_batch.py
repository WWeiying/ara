#!/usr/bin/env python3
"""Rebase the reviewed queue candidate on a completed corpus, without simulation."""
import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'verification/coverage'))
import coverage_evidence as evidence

OUT = ROOT / 'verification/out'
DRAFT = OUT / 'gap38-i8-f16-preflight-20261004-03/selection.checked-draft.json'
AUDIT = OUT / 'gap38-queue-analysis-20261004-01/path-classification.json'
NAME = 'rvv:vgap38_i8_f16_lane3'
require = evidence.require


def missing_targets(bits, previous, candidate):
    scope = candidate['scope']
    wanted = {'branch': [candidate['branch']['raw_index']],
              'line': [int(block['index']) for block in candidate['blocks']]}
    require(wanted == {'branch': [41], 'line': [120, 121]}, 'target coordinates changed')
    result = {}
    for metric, positions in wanted.items():
        row, old = bits['metrics'][metric][scope], previous['metrics'][metric][scope]
        require((row['checksum'], row['width']) == (old['checksum'], old['width']),
                'queue shape differs from reviewed baseline')
        value = int(row['bits'], 16)
        require(0 <= value < (1 << row['width']), 'malformed raw bitmap')
        raw = format(value, f"0{row['width']}b")
        require(all(0 <= index < len(raw) and raw[index] == '0' for index in positions),
                'reviewed target already covered; select a different gap')
        result[metric] = positions
    return {'scope': scope, 'still_missing_raw_indices': result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    baseline, output = args.baseline.resolve(strict=True), args.output.resolve()
    require(baseline.parent == OUT and output.parent == OUT and not output.exists(),
            'use a completed local corpus and a new selection file')
    proof = evidence.Evidence()
    proof.hashes(proof.read(DRAFT.parent / 'draft.sha256.json'))
    draft = proof.read(DRAFT)
    precheck = proof.read(DRAFT.parent / 'checked-precheck.json')
    require(precheck['status'] == 'PASS', 'candidate precheck did not pass')
    require(len(draft['cases']) == 1 and draft['cases'][0]['name'] == NAME,
            'unexpected candidate set')
    item = copy.deepcopy(draft['cases'][0])
    require(item['timeout_s'] == 300, 'reviewed case budget changed')
    evidence.precheck(item, proof)
    checkpoint = proof.read(baseline / 'checkpoint.json')
    collection = proof.read(baseline / 'collection.json')
    require(checkpoint['coverage_status'] == 'COMPLETE' and collection['status'] == 'PASS'
            and collection['passed'] == checkpoint['aggregate_passed'] >= 640,
            'latest control corpus is not complete')
    for name in ('all-passed-outcomes.json', 'combined-bits.json'):
        path = baseline / name
        proof.pin(path, collection['reports'][str(path)])
    rows = proof.read(baseline / 'all-passed-outcomes.json')
    bits = proof.read(baseline / 'combined-bits.json')
    require(len(rows) == collection['passed'] and len({r['name'] for r in rows}) == len(rows)
            and bits['tests'] == [r['vdb'] for r in rows], 'corpus membership differs')
    require(all(r['status'] == 'PASS' and r['passed_only'] and r['vdb_valid'] for r in rows)
            and not any(r['name'] == NAME.split(':')[1] for r in rows),
            'non-PASS or duplicate candidate in corpus')
    previous = proof.read(Path(draft['baseline_bits']))
    require(bits['design'] == previous['design'], 'compiled coverage design differs')
    candidate = proof.read(AUDIT)['candidate']
    remaining = missing_targets(bits, previous, candidate)
    require(item['targets'] == [candidate['scope']], 'candidate scope changed')
    sources = [Path(__file__).resolve(), AUDIT, DRAFT,
               DRAFT.parent / 'draft.sha256.json', DRAFT.parent / 'checked-precheck.json']
    item['sources'].append(str(sources[0]))
    item['evidence'].extend(str(p) for p in sources[1:] if str(p) not in item['evidence'])
    item['rationale'] += ' The same exact target bits remain missing in the completed successor corpus.'
    result = {'status': 'REVIEWED_SELECTION_NOT_LAUNCHED', 'baseline': str(baseline),
              'baseline_bits': str(baseline / 'combined-bits.json'), 'cases': [item],
              'composition': {'draft': str(DRAFT), 'script': str(sources[0]),
                              'baseline_passed': len(rows), **remaining},
              'note': 'Selection only; unchanged checked-extension admission is required before VCS.'}
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(output, flush=True)


if __name__ == '__main__':
    main()
