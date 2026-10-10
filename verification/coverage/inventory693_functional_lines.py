"""Rank exact693 raw branch gaps by source line; never changes exclusions."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from inventory_operand_debug import ROOT, Design
from closure_point_inventory import definition, points, read_xml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.absolute()
    if out.exists() or out.parent != ROOT / 'verification/out':
        raise ValueError('Fresh evidence path required')
    bitmap_path = ROOT / 'verification/out/gap86-offline-admitted-693-20261006-01/combined-bits.json'
    data = bitmap_path.read_bytes()
    bitmap = json.loads(data)
    if len(bitmap['tests']) != len(set(bitmap['tests'])) or len(bitmap['tests']) != 693:
        raise ValueError('Wrong population')
    vdb = ROOT / 'verification/out/repaired-aligned-build-20260930-01/sim/simv.vdb'
    shape_path = vdb / 'snps/coverage/db/shape/branch.verilog.shape.xml'
    if hashlib.sha256(shape_path.read_bytes()).hexdigest() != bitmap['design']['shape/branch.verilog.shape.xml']:
        raise ValueError('Shape drift')
    design, shape = Design(vdb), read_xml(shape_path)
    counters = Counter()
    unresolved = []
    for scope, record in bitmap['metrics']['branch'].items():
        if 'i_ara.' not in scope:
            continue
        if record['checksum'] is None:
            unresolved.append(dict(scope=scope, width=record['width'],
                raw_unhit_branch_positions=record['width'] - bin(int(record['bits'], 16)).count('1'),
                reason='No checksum binding; source-line attribution not attempted'))
            continue
        node = definition(shape, design.hierarchy[scope], record['checksum'])
        source = design.source(scope)['resolved_path']
        bits = int(record['bits'], 16)
        for point in points('branch', node, record['width']):
            index = point['raw_index']
            if index < 0 or index >= record['width']:
                raise ValueError('Invalid coordinate')
            if not bits & (1 << (record['width'] - index - 1)):
                counters[(source, point['line'])] += 1
    if bitmap_path.read_bytes() != data:
        raise ValueError('Input changed')
    files = [bitmap_path, shape_path, vdb / 'snps/coverage/db/design/verilog.design.xml',
             Path(__file__).resolve()]
    result = dict(status='RAW_FUNCTIONAL_LINE_RANKING_NOT_WAIVED', historical_passes=693,
        waivers_applied=False, official_percentages=False,
        unresolved_scopes=unresolved,
        pins={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        ranks=[dict(source=key[0], line=key[1], raw_unhit_branch_positions=count)
               for key, count in sorted(counters.items(), key=lambda row: (-row[1], row[0]))])
    with out.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result['ranks'][:15], indent=2))


if __name__ == '__main__':
    main()
