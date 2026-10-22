#!/usr/bin/env python3
"""Inventory diagnostic-only source regions, without creating exclusions."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE / 'reviewed_20261004'))
from audit_readonly import Design
from closure_point_inventory import points

SOURCE = ROOT / 'hardware/src/lane/operand_requester.sv'
SOURCE_SHA = '327291850e6d77797ab9e67c8d24dd7e8bca9019139d85518b0075fd80f5bca2'
REGIONS = ((620, 886), (1098, 1140))


def contained(point, metric):
    locations = [int(point['line'])]
    locations += ([int(s['line_num']) for s in point['statements']] if metric == 'line'
                  else [int(s['id']) for s in point['expressions']])
    return all(any(start <= line <= end for start, end in REGIONS) for line in locations)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cache = ROOT / 'verification/out/gap83-offline-admitted-690-20261006-02/combined-bits.json'
    build = ROOT / 'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json'
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    pins = {str(p): sha(p) for p in (SOURCE, cache, build, Path(__file__).resolve())}
    if pins[str(SOURCE)] != SOURCE_SHA or json.loads(build.read_bytes()).get(str(SOURCE)) != SOURCE_SHA:
        raise ValueError('Source does not match old image')
    bitmap = json.loads(cache.read_bytes())
    design = Design(ROOT / 'verification/out/repaired-aligned-build-20260930-01/sim/simv.vdb')
    rows, counts = [], Counter()
    for lane in range(4):
        scope = f'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[{lane}].i_lane.i_operand_requester'
        if design.source(scope)['resolved_path'] != str(SOURCE):
            raise ValueError('Wrong compiled source owner')
        for metric in ('line', 'branch'):
            record = bitmap['metrics'][metric][scope]
            definition = design.definition(scope, metric)
            if record['checksum'] != definition.get('chksum'):
                raise ValueError('Compiled metric binding differs')
            for point in points(metric, definition, record['width']):
                if not contained(point, metric):
                    continue
                hit = bool(int(record['bits'], 16) & (1 << (record['width'] - 1 - point['raw_index'])))
                rows.append(dict(scope=scope, metric=metric, point=point, hit=hit,
                                 module_checksum=design.hierarchy[scope].get('chksum'),
                                 metric_checksum=record['checksum'], decision='REVIEW_REQUIRED_NOT_WAIVED'))
                counts[metric + '_positions'] += 1
                counts[metric + '_unhit'] += int(not hit)
    for p, expected in pins.items():
        if sha(Path(p)) != expected:
            raise ValueError('Evidence changed during inventory')
    with args.output.open('x') as stream:
        json.dump(dict(status='DEBUG_REGION_INVENTORY_ONLY_NOT_EXCLUSIONS', source_regions=REGIONS,
                       input_sha256=pins, design=bitmap['design'], counts=dict(counts), points=rows,
                       native_qualified=False, functional_noninterference_review_complete=False), stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(counts)))


if __name__ == '__main__':
    main()
