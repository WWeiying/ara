#!/usr/bin/env python3
"""Group accepted independent-SoftFloat lane vectors without changing arithmetic."""
import argparse
import hashlib
import json
from pathlib import Path

BASE = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_pv_lane_20261108_03')
VECTOR_SHA = '223a8fa9cbc1ccb14a6cafc593fdc681fabb1d40188701bf1625d96d6111ff60'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def records(text, metadata):
    lines = iter(text.splitlines())
    magic, count = next(lines).split()
    if int(magic, 16) != 0x50565531 or int(count) != len(metadata):
        raise ValueError('Corpus identity/count mismatch')
    result = {}
    for meta in metadata:
        header = next(lines).split()
        if len(header) != 14:
            raise ValueError('Malformed case header')
        for index, field in enumerate(('id', 'elements', 'heads', 'tokens', 'rm', 'mode')):
            if int(header[index]) != meta[field]:
                raise ValueError('Metadata/body mismatch: '+field)
        if int(header[12], 16) != meta['fma_flags'] or int(header[13], 16) != meta['prepared_flags']:
            raise ValueError('Flags mismatch')
        counts = [int(x) for x in header[8:12]]
        if min(counts) < 0 or max(counts) > 1024 or meta['name'] in result:
            raise ValueError('Invalid counts/duplicate name')
        body = []
        for count, width in zip(counts, (2, 2, 8, 3)):
            for _ in range(count):
                line = next(lines)
                if len(line.split()) != width:
                    raise ValueError('Malformed expected record')
                body.append(line)
        result[meta['name']] = dict(header=header, body=body, metadata=meta)
    if next(lines, None) is not None:
        raise ValueError('Trailing corpus data')
    return result


def selections():
    groups = [[f'qwen3_tile{t}_lane{l}' for l in range(4)] for t in range(3)]
    # Distinct directed/random lane inputs of the same geometry stress routing.
    for n, tokens in ((16, 9), (24, 9), (32, 9), (1, 1), (3, 1), (31, 1)):
        for heads in (1, 2):
            for rm in range(5):
                groups.append([f'matrix_{l%2}_{n}_{heads}_{tokens}_{rm}' for l in range(4)])
    for rm in range(5):
        groups.append([f'special_{rm}_7c01_3c00_0']*4)
    return groups


def generate(output):
    receipt = json.loads((BASE/'report.json').read_text())
    if receipt['state'] != 'PASS' or sha(BASE/'vectors/vectors.txt') != VECTOR_SHA:
        raise ValueError('Unaccepted original corpus')
    for key, expected in receipt['artifacts'].items():
        if sha(Path(key)) != expected:
            raise ValueError('Original evidence drift: '+key)
    meta = json.loads((BASE/'vectors/vectors.json').read_text())
    rows = records((BASE/'vectors/vectors.txt').read_text(), meta['cases_by_id'])
    groups = selections()
    output.mkdir(parents=True, exist_ok=False)
    manifest = []
    lane_text = [f'50565531 {len(groups)}\n' for _ in range(4)]
    for idx, names in enumerate(groups):
        selected = [rows[name] for name in names]
        geometry = selected[0]['header'][1:5]
        if any(r['header'][1:5] != geometry or int(r['header'][5]) != 0 for r in selected):
            raise ValueError('Unequal geometry or non-numerical case')
        flags = 0
        for lane, row in enumerate(selected):
            header = row['header'][:]
            header[0] = str(idx)
            lane_text[lane] += ' '.join(header)+'\n'+'\n'.join(row['body'])+'\n'
            flags |= int(header[12], 16)
        manifest.append(dict(id=idx, source_names=names,
                             elements=int(geometry[0]), heads=int(geometry[1]),
                             tokens=int(geometry[2]), rm=int(geometry[3]), flags=flags))
    for lane, text in enumerate(lane_text):
        (output/f'lane{lane}.txt').write_text(text)
    pins = {str(p): sha(p) for p in (BASE/'report.json', BASE/'vectors/vectors.txt',
                                    BASE/'vectors/vectors.json', Path(__file__).resolve())}
    pins.update({str(output/f'lane{l}.txt'): sha(output/f'lane{l}.txt') for l in range(4)})
    summary = dict(cases=len(groups), real_groups=3, real_lane_cases=12,
                   scope='Prepared FP16 PV operands; all original expectation bodies unchanged',
                   groups=manifest, pins=pins)
    (output/'corpus.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(f'CLUSTER_CORPUS groups={len(groups)} real_groups=3')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    generate(args.output.resolve())
