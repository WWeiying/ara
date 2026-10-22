"""Source-line ranking for an admitted raw population, without exclusions."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from inventory_operand_debug import ROOT, Design
from closure_point_inventory import definition, points, read_xml


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base, out = args.base.absolute(), args.output.absolute()
    if base.parent != ROOT / 'verification/out' or out.exists() or out.parent != base.parent:
        raise ValueError('Independent admitted base and fresh output required')
    paths = [base / name for name in ('status.json', 'combined-bits.json', 'combined-inputs.txt')]
    state, bitmap = [json.loads(path.read_bytes()) for path in paths[:2]]
    count = state['aggregate_passed']
    if state['status'] != 'PASS_RAW_UNION_HISTORICAL_ONLY' or len(bitmap['tests']) != count or len(set(bitmap['tests'])) != count:
        raise ValueError('Not an admitted raw population')
    vdb = ROOT / 'verification/out/repaired-aligned-build-20260930-01/sim/simv.vdb'
    if paths[2].read_text().splitlines() != [str(vdb), *bitmap['tests']]:
        raise ValueError('Input membership mismatch')
    shape_path = vdb / 'snps/coverage/db/shape/branch.verilog.shape.xml'
    if digest(shape_path) != bitmap['design']['shape/branch.verilog.shape.xml']:
        raise ValueError('Shape drift')
    paths += [shape_path, vdb / 'snps/coverage/db/design/verilog.design.xml',
              Path(__file__).resolve()]
    pins = {str(path): digest(path) for path in paths}
    design, shape = Design(vdb), read_xml(shape_path)
    counters, unresolved = Counter(), []
    for scope, record in bitmap['metrics']['branch'].items():
        if 'i_ara.' not in scope:
            continue
        if record['checksum'] is None:
            unresolved.append(dict(scope=scope, width=record['width'],
                raw_unhit_branch_positions=record['width'] - bin(int(record['bits'], 16)).count('1'),
                reason='No checksum binding; no source-line attribution'))
            continue
        node = definition(shape, design.hierarchy[scope], record['checksum'])
        source = design.source(scope)['resolved_path']
        bits = int(record['bits'], 16)
        for point in points('branch', node, record['width']):
            index = point['raw_index']
            if not 0 <= index < record['width']:
                raise ValueError('Invalid coordinate')
            if not bits & (1 << (record['width'] - index - 1)):
                counters[source, point['line']] += 1
    if any(digest(Path(path)) != expected for path, expected in pins.items()):
        raise ValueError('Input drift')
    result = dict(status='RAW_BRANCH_LINE_RANKING_NOT_WAIVED', historical_passes=count,
        scope_filter='i_ara descendants; debug and unreachable candidates not filtered',
        waivers_applied=False, official_percentages=False, unresolved_scopes=unresolved, pins=pins,
        ranks=[dict(source=key[0], line=key[1], raw_unhit_branch_positions=value)
               for key, value in sorted(counters.items(), key=lambda row: (-row[1], row[0]))])
    with out.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result['ranks'][:15], indent=2))


if __name__ == '__main__':
    main()
