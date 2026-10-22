"""Rank raw branch gaps outside reviewed diagnostic candidates, not coverage scores."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paths = [ROOT / 'verification/out/gap83-offline-admitted-690-20261006-02/combined-bits.json',
             ROOT / 'verification/out/operand-debug-inventory-690-20261006-01.json']
    data = [p.read_bytes() for p in paths]
    bitmap, diagnostic = [json.loads(value) for value in data]
    if len(bitmap['tests']) != 690 or len(set(bitmap['tests'])) != 690:
        raise ValueError('Not exact690 unique historical members')
    skip = defaultdict(set)
    for row in diagnostic['points']:
        if row['decision'] != 'REVIEW_REQUIRED_NOT_WAIVED':
            raise ValueError('Unexpected candidate decision')
        skip[(row['metric'], row['scope'])].add(row['point']['raw_index'])
    ranks = []
    for scope, record in bitmap['metrics']['branch'].items():
        if 'i_ara.' not in scope:
            continue
        bits = format(int(record['bits'], 16), '0%db' % record['width'])
        if len(bits) != record['width']:
            raise ValueError('Bitmap width overflow')
        excluded = skip[('branch', scope)]
        if any(index < 0 or index >= len(bits) for index in excluded):
            raise ValueError('Candidate index out of range')
        ranks.append(dict(scope=scope, metric='branch', checksum=record['checksum'],
            remaining_positions=record['width'] - len(excluded),
            raw_unhit_outside_candidates=sum(bit == '0' and index not in excluded
                                            for index, bit in enumerate(bits))))
    if any(path.read_bytes() != value for path, value in zip(paths, data)):
        raise ValueError('Input changed while ranking')
    result = dict(status='DIAGNOSTIC_RANKING_NOT_WAIVED_COVERAGE', historical_passes=690,
        waivers_applied=False, official_percentages=False,
        input_sha256={str(p): hashlib.sha256(v).hexdigest() for p, v in zip(paths, data)},
        ranks=sorted(ranks, key=lambda r: (-r['raw_unhit_outside_candidates'], r['scope'])))
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result['ranks'][:3], indent=2))


if __name__ == '__main__':
    main()
