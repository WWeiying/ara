"""Read-only frozen source and exact734 missing compiled points, no EDA/tests."""
import collections
import json
from pathlib import Path

import inventory_operand_debug as compiled
from closure_point_inventory import read_xml, definition
from prove_mask_store_snapshot_zero import digest, require

ROOT = compiled.ROOT
BASE = ROOT/'verification/out/gap110-offline-admitted-734-parent-20261006-01'
DESIGN = ROOT/'verification/out/repaired-aligned-build-20260930-01/sim/simv.vdb'
BUILD = ROOT/'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json'


def evidence():
    manifest = json.loads((BASE/'admission-manifest.json').read_bytes())
    pins = {str(BASE/'admission-manifest.json'): digest(BASE/'admission-manifest.json'), str(BUILD): digest(BUILD)}
    for name in ('combined-bits.json', 'combined-inputs.txt'):
        p = BASE/name
        require(digest(p) == manifest['output_pins'][str(p)], 'Exact734 output drift')
        pins[str(p)] = digest(p)
    bits = json.loads((BASE/'combined-bits.json').read_bytes())
    require(len(bits['tests']) == len(set(bits['tests'])) == 734 and
            (BASE/'combined-inputs.txt').read_text().splitlines() == bits['tests'], 'Exact734 membership differs')
    build = json.loads(BUILD.read_bytes())
    for relative in ('hardware/src/vlsu/qbs/qbs_payload_buffer.sv',
        'hardware/src/vlsu/qbs/qbs_profile_engine_int.sv', 'hardware/src/vlsu/qbs/qbs_compute_engine.sv',
        'hardware/src/vlsu/qbs/qbs_profile_decoder.sv', 'hardware/src/vlsu/qbs/qbs_block_adapter.sv',
        'hardware/src/vlsu/qbs/qbs_read_engine.sv', 'hardware/include/qbs_pkg.sv'):
        p = ROOT/relative
        require(digest(p) == build[str(p)], 'Frozen source drift: '+relative)
        pins[str(p)] = digest(p)
    design = compiled.Design(DESIGN)
    for rel, expected in bits['design'].items():
        p = design.db/rel
        require(digest(p) == expected, 'Frozen design drift')
        pins[str(p)] = digest(p)
    scopes = [s for s in bits['metrics']['cond'] if s.endswith(('i_payload_buffer', 'i_profile_engine_int')) and 'qbs' in s]
    result = []
    for metric in ('line', 'branch', 'cond'):
        path = design.db/('shape/'+metric+'.verilog.shape.xml')
        pins[str(path)] = digest(path)
        shape = read_xml(path)
        for scope in scopes:
            rec = bits['metrics'][metric][scope]
            node = definition(shape, design.hierarchy[scope], rec['checksum'])
            pts = compiled.points(metric, node, rec['width'])
            missing = [p for p in pts if not int(rec['bits'],16) & (1 << (rec['width']-1-p['raw_index']))]
            clusters = []
            for line, count in collections.Counter(p['line'] for p in missing).most_common():
                examples = [p for p in missing if p['line'] == line]
                clusters.append(dict(line=line, count=count, examples=examples[:3]))
            result.append(dict(scope=scope, metric=metric, checksum=rec['checksum'], width=rec['width'],
                               source=design.source(scope), missing=missing, clusters=clusters))
    pins[str(Path(__file__).resolve())] = digest(Path(__file__).resolve())
    return dict(status='READ_ONLY734_ZERO_INVENTORY_NOT_REACHABILITY_NOT_WAIVER', pins=pins,
        baseline=str(BASE), records=result, simulation_started=False, RTL_changed=False)


if __name__ == '__main__':
    record = evidence()
    for r in record['records']:
        print(r['scope'].split('.')[-2:], r['metric'], len(r['missing']),
              [(c['line'], c['count']) for c in r['clusters'][:18]])
        if r['scope'].endswith('i_profile_engine_int'):
            for c in r['clusters']:
                if int(c['line']) > 240:
                    print(json.dumps(c))
