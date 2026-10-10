#!/usr/bin/env python3
"""Prove constant-zero selectors; never assume ternary/native vector semantics."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from lzc_padding_candidates import shape_bindings, WIDTH_BY_CHECKSUM
from lzc_padding_proof import prove, SOURCE_SHA256


def selector_expression(level, index):
    return (f"(gen_lzc.sel_nodes[(((2 ** ({level} + 1)) - 1) + "
            f"({index} * 2))] == 1'b1)")


def structural_decision(point):
    if point.get('line') != '95' or point.get('vector') != '1':
        return 'RETAIN'
    match = re.fullmatch(r'level=(\d+),l=(\d+)', point.get('spec', {}).get('generate_info', ''))
    width = WIDTH_BY_CHECKSUM.get(point.get('metric_checksum'))
    if not match or width is None or point.get('source_sha256') != SOURCE_SHA256:
        raise ValueError('Selector proof source or coordinates unbound')
    level, index = map(int, match.groups())
    node = next((n for n in prove(width)['nodes'] if (n['level'], n['index']) == (level, index)), None)
    if node is None:
        raise ValueError('Selector outside internal tree')
    if node['left_real_bits']:
        return 'RETAIN_REACHABLE'
    attrs = point['attributes']
    if attrs['optype'] == '23':
        return 'HOLD_TERNARY_NATIVE_SEMANTICS'
    if (attrs['optype'] != '16' or point['expression'] != selector_expression(level, index)
            or attrs['exprstr'] != point['expression'] or attrs['width'] != '1'
            or point['truth_table'] != dict(ncols='1', nrows='2', vecs='01')):
        raise ValueError('Not an exact boolean selector condition')
    return 'STRUCTURAL_CANDIDATE_NATIVE_REQUIRED'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retained', type=Path, required=True)
    parser.add_argument('--bitmap', type=Path, required=True)
    parser.add_argument('--design-vdb', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    paths = [args.retained, args.bitmap, args.source, Path(__file__)]
    pins = {str(p.resolve()): sha(p) for p in paths}
    if sha(args.source) != SOURCE_SHA256:
        raise ValueError('Source drift')
    data = json.loads(args.retained.read_bytes())
    bitmap = json.loads(args.bitmap.read_bytes())
    points = [r['point'] for r in data['retained']]
    bindings = shape_bindings(points, bitmap, args.design_vdb / 'snps/coverage/db')
    rows, seen = [], set()
    for point in points:
        key = (point['scope'], point['raw_index'])
        if key in seen:
            raise ValueError('Duplicate point')
        seen.add(key)
        bound = bindings[key[0]][key[1]]
        for field in ('native_id', 'file_id', 'line', 'expression', 'attributes', 'spec', 'truth_table', 'row', 'vector'):
            if point.get(field) != bound.get(field):
                raise ValueError('Compiled selector identity differs: ' + field)
        record = bitmap['metrics']['cond'][key[0]]
        if record['checksum'] != point['metric_checksum']:
            raise ValueError('Metric checksum drift')
        hit = bool(int(record['bits'], 16) & (1 << (record['width'] - 1 - key[1])))
        decision = structural_decision(point) if not hit else 'RETAIN_HIT'
        rows.append(dict(point=point, hit=hit, decision=decision, native_qualified=False))
    for p in paths:
        if sha(p) != pins[str(p.resolve())]:
            raise ValueError('Evidence changed during proof')
    with args.output.open('x') as stream:
        json.dump(dict(status='STRUCTURAL_DIAGNOSTIC_ONLY_NO_EXCLUSIONS', rows=rows,
                       input_sha256=pins, design=bitmap['design'], tests=bitmap['tests']), stream, indent=2)
        stream.write('\n')
    from collections import Counter
    print(json.dumps(dict(Counter(r['decision'] for r in rows))))


if __name__ == '__main__':
    main()
