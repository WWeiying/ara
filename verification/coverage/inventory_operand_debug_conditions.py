#!/usr/bin/env python3
"""Condition-coordinate supplement; diagnostic inventory, not native waivers."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from inventory_operand_debug import ROOT, SOURCE, SOURCE_SHA, REGIONS, Design
from closure_point_inventory import points, read_xml, definition


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cache = ROOT / 'verification/out/gap83-offline-admitted-690-20261006-02/combined-bits.json'
    oldbuild = ROOT / 'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json'
    vdb = ROOT / 'verification/out/repaired-aligned-build-20260930-01/sim/simv.vdb'
    shape_path = vdb / 'snps/coverage/db/shape/cond.verilog.shape.xml'
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    paths = [SOURCE, cache, oldbuild, shape_path, Path(__file__).resolve(),
             Path(__file__).with_name('inventory_operand_debug.py')]
    pins = {str(p): sha(p) for p in paths}
    if sha(SOURCE) != SOURCE_SHA or json.loads(oldbuild.read_bytes()).get(str(SOURCE)) != SOURCE_SHA:
        raise ValueError('Not frozen image source')
    bitmap = json.loads(cache.read_bytes())
    if bitmap['design']['shape/cond.verilog.shape.xml'] != sha(shape_path):
        raise ValueError('Condition shape drift')
    design, shape = Design(vdb), read_xml(shape_path)
    rows, counts = [], Counter()
    for lane in range(4):
        scope = f'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[{lane}].i_lane.i_operand_requester'
        if design.source(scope)['resolved_path'] != str(SOURCE):
            raise ValueError('Wrong source owner')
        record = bitmap['metrics']['cond'][scope]
        node = definition(shape, design.hierarchy[scope], record['checksum'])
        for point in points('cond', node, record['width']):
            # Unknown/multi-line locations are retained, not guessed into a region.
            if not point['line'].isdigit() or not any(a <= int(point['line']) <= z for a, z in REGIONS):
                continue
            hit = bool(int(record['bits'], 16) & (1 << (record['width'] - 1 - point['raw_index'])))
            rows.append(dict(scope=scope, metric='cond', point=point, hit=hit,
                             module_checksum=design.hierarchy[scope].get('chksum'),
                             metric_checksum=record['checksum'], decision='REVIEW_REQUIRED_NOT_WAIVED'))
            counts['condition_positions'] += 1
            counts['condition_unhit'] += int(not hit)
    for path in paths:
        if sha(path) != pins[str(path)]:
            raise ValueError('Evidence changed')
    with args.output.open('x') as stream:
        json.dump(dict(status='DEBUG_CONDITION_INVENTORY_ONLY_NO_EXCLUSIONS', counts=dict(counts),
                       source_regions=REGIONS, input_sha256=pins, points=rows,
                       native_qualified=False), stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(counts)))


if __name__ == '__main__':
    main()
