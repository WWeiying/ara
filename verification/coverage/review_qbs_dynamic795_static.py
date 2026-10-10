"""Actual795 QBS read/accumulator binary residual; arrays/partial EL stay HOLD."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import report_population795_pmp816 as report
import rank_cva6_scalar_data767 as typed
import targeted_toggle_evidence_v2 as native


def collect():
    life = report.life
    pins = {}
    def read(path, expected):
        value = life.read_bound(path, expected)
        pins[str(path)] = expected
        return value
    manifest = read(report.BASE, report.BASE_SHA)
    bitmap = report.BASE.parent / 'combined-toggle-bits.json'
    rows = read(bitmap, manifest['output_pins'][str(bitmap)])
    handoff = read(report.HANDOFF, report.HANDOFF_SHA)
    el = report.HANDOFF.parent / 'candidate-union.el'
    expected = handoff['output_pins'][str(el)]
    report.need(life.digest(el) == expected, 'Sealed795 complete policy union')
    pins[str(el)] = expected
    other, masks = report.stable.semantic(el.read_text())
    whole = {x[0] for x in other if x[3] == 'WHOLE_SCOPE'}
    ledger = report.BASE.parent / 'combined-inputs.txt'
    report.need(life.digest(ledger) == manifest['output_pins'][str(ledger)], 'Published795 ledger')
    pins[str(ledger)] = manifest['output_pins'][str(ledger)]
    shape = Path(ledger.read_text().splitlines()[0]) / 'snps/coverage/db/shape/tgl.verilog.shape.xml'
    report.need(life.digest(shape) == manifest['input_pins'][str(shape)], 'Frozen compiled Toggle shape')
    pins[str(shape)] = manifest['input_pins'][str(shape)]
    definitions = {}
    for node in native.xml(shape).findall('tgldef'):
        definitions.setdefault(node.get('chksum'), []).append(node)
    constant = life.OUT / 'qbs-accumulator-config-constants-source-review767-agent-20261007-01.json'
    # The predecessor's source-constant receipt is also pinned by global794.
    cpath = life.OUT / 'current-population794-soc61-parent-20261008-01/config.json'
    config = read(cpath, '81526ba2020842417df95403931ca06441716ecf7b98ebf88ba0a67daca9434f')
    const_sha = config['pins'][str(constant)]
    const = read(constant, const_sha)
    constant_fields = {(r['scope'], r['attributes']['name']) for r in const['candidates']}
    objects, holds = [], []
    removed = 0
    for scope, row in rows.items():
        if not ('.i_qbs_engine.i_read_engine' in scope or '.i_fp_accumulator' in scope):
            continue
        if any(scope == s or scope.startswith(s + '.') for s in whole):
            continue
        ds = definitions.get(row['checksum'], [])
        if len(ds) != 1:
            holds.append(dict(scope=scope, reason='Compiled checksum not unique'))
            continue
        nodes, arrays = typed.typed_nodes(ET.tostring(ds[0], encoding='unicode'), row)
        if arrays:
            holds.append(dict(scope=scope, reason='MDA not ranked or flattened', objects=arrays))
        for node in nodes:
            if not node['missing_slots']:
                continue
            if node['name'] == 'hart_id_i' or node['name'].rsplit('.', 1)[-1] in {'tval2', 'tinst', 'gva'}:
                holds.append(dict(scope=scope, name=node['name'], reason='Known source/config constant, not a data-pattern target; no new waiver'))
                continue
            if any('.gen_operation_groups[%d].i_opgroup_block' % i in scope for i in (1, 2, 4)):
                holds.append(dict(scope=scope, name=node['name'], reason='Disabled operation group, not stimulus-ranked; metrics remain protected'))
                continue
            if scope.endswith('.i_fpnew.i_arbiter') and any(node['name'].startswith('data_i[%d].' % i) for i in (1, 2, 4)):
                holds.append(dict(scope=scope, name=node['name'], reason='Disabled source group alias, no data producer selected by this accumulator'))
                continue
            if (scope, node['name']) in constant_fields:
                removed += 1
                continue
            low = min(int(node.get('left', '0')), int(node.get('right', '0')))
            full = ((1 << node['logical_width']) - 1) << low
            covered = {d: 0 for d in ('0to1', '1to0')}
            any_owner = False
            for (s, cs, name, kind, decl, prefix, direction), bits in masks.items():
                if s != scope or name != node['name']:
                    continue
                report.need(cs.split()[-1] == row['checksum'], 'Native EL checksum binding')
                any_owner = True
                if not prefix:
                    covered[direction] |= bits
            if all(v & full == full for v in covered.values()):
                removed += 1
                continue
            if any_owner:
                holds.append(dict(scope=scope, name=node['name'], reason='Partial EL, direction order not assumed'))
                continue
            objects.append(dict(scope=scope, checksum=row['checksum'], definition=ds[0].get('name'),
                                name=node['name'], logical_width=node['logical_width'],
                                declaration={k:node[k] for k in ('type', 'left', 'right', 'line_num') if k in node},
                                missing_count=node['missing_slots'], coordinates=node['missing_coordinates']))
    objects.sort(key=lambda r: (-r['missing_count'], r['scope'], r['name']))
    pins[str(Path(__file__).resolve())] = life.digest(Path(__file__).resolve())
    life.check(pins)
    return dict(status='ACTUAL795_QBS_BINARY_RESIDUAL_SOURCE_REACHABILITY_PENDING',
                baseline_seal=report.BASE_SHA, EL_seal=expected, input_pins=pins,
                objects=objects, holds=holds, constants_or_full_EL_removed=removed,
                MDA_excluded_from_ranking=True, partial_EL_excluded_from_ranking=True,
                no_native_direction_guess=True, EDA_started=False, RTL_changed=False,
                official_denominator=None, measured_gain=None)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report.need(not args.output.exists(), 'Fresh evidence required')
    result = collect()
    report.life.save(args.output, result)
    print(report.life.digest(args.output))
    for item in result['objects'][:35]:
        print(item['scope'], item['name'], item['missing_count'])
