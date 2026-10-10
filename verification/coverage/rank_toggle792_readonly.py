"""Current binary residuals; partial EL and MDA stay explicit HOLDs."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import targeted_toggle_evidence_v2 as t
import rank_cva6_scalar_data767 as typed
import report_global777_compact as native

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
BASE = OUT / 'scalar-misalign-offline-admitted792-agent-20261008-01'
SEAL = '0aadd9e4fa71a5a582830a043fedc67669b0f53cea866a1b8147a5526c8f81f4'
REPORT = OUT / 'current-population791-inherited785-parent-20261008-01'
QUAL_SHA = 'ad675368b58524794a04cc7518374eaf025382e7687f57dd60f2bb9986cba1e3'


def evidence():
    pins = {}

    def read(path, expected=None, parse=True):
        data = path.read_bytes()
        seal = hashlib.sha256(data).hexdigest()
        assert expected is None or seal == expected, str(path)
        pins[str(path)] = seal
        return json.loads(data) if parse else data.decode()

    manifest = read(BASE / 'admission-manifest.json', SEAL)
    authority = dict(manifest['input_pins'], **manifest['output_pins'])
    rows = read(BASE / 'combined-toggle-bits.json', authority[str(BASE / 'combined-toggle-bits.json')])
    ledger = read(BASE / 'combined-inputs.txt', authority[str(BASE / 'combined-inputs.txt')], False).splitlines()
    assert len(ledger) == len(set(ledger)) == 793
    q = read(REPORT / 'qualification.json', QUAL_SHA)
    assert q['population'] == 791 and q['status'] == 'CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED'
    el = read(REPORT / 'applied.el', q['output_pins'][str(REPORT / 'applied.el')], False)
    other, masks = native.semantic(el)
    whole = {s for s, checksum, machine, line in other if line == 'WHOLE_SCOPE'}
    excluded = {}
    for (scope, checksum, name, kind, decl, prefix, direction), mask in masks.items():
        checks = checksum.split()
        assert len(checks) == 2 and all(c.isdecimal() for c in checks)
        assert scope in rows and checks[1] == rows[scope]['checksum'], scope
        if not prefix:
            key = (scope, checks[1], name, direction)
            excluded[key] = excluded.get(key, 0) | mask
    shape_path = Path(ledger[0]) / 'snps/coverage/db/shape/tgl.verilog.shape.xml'
    assert t.digest(shape_path) == authority[str(shape_path)]
    pins[str(shape_path)] = authority[str(shape_path)]
    definitions = {}
    for d in t.xml(shape_path).findall('tgldef'):
        definitions.setdefault(d.get('chksum'), []).append(d)
    ranking, holds = [], []
    for scope, row in rows.items():
        if not scope.startswith('ara_tb.dut.i_ara_soc.i_system.'):
            continue
        if any(scope == s or scope.startswith(s + '.') for s in whole):
            continue
        defs = definitions.get(row['checksum'], [])
        if len(defs) != 1:
            holds.append(dict(scope=scope, reason='Nonunique checksum definition'))
            continue
        try:
            nodes, arrays = typed.typed_nodes(ET.tostring(defs[0], encoding='unicode'), row)
        except ValueError as error:
            holds.append(dict(scope=scope, reason=str(error)))
            continue
        objects, partial = [], []
        for node in nodes:
            if not node['missing_slots']:
                continue
            lo = min(int(node.get('left', 0)), int(node.get('right', 0)))
            full = ((1 << node['logical_width']) - 1) << lo
            cover = [excluded.get((scope, row['checksum'], node['name'], d), 0)
                     for d in ('0to1', '1to0')]
            if all(v & full == full for v in cover):
                continue
            obj = dict(name=node['name'], width=node['logical_width'],
                       missing_serialized_slots=node['missing_slots'],
                       coordinates=node['missing_coordinates'])
            (partial if any(v & full for v in cover) else objects).append(obj)
        ranking.append(dict(scope=scope, checksum=row['checksum'],
                            exact_unexcluded_binary_missing=sum(o['missing_serialized_slots'] for o in objects),
                            partial_EL_unclassified_raw_missing=sum(o['missing_serialized_slots'] for o in partial),
                            objects=sorted(objects, key=lambda o: -o['missing_serialized_slots']),
                            partial_EL_HOLD=partial, MDA_HOLD=arrays))
    ranking.sort(key=lambda r: -r['exact_unexcluded_binary_missing'])
    return dict(status='FORMAL792_BINARY_RESIDUAL_MINUS_QUALIFIED791_EL_READONLY',
                baseline=792, baseline_seal=SEAL, report_population=791,
                input_pins=pins, ranking=ranking, shape_HOLD=holds,
                limitations=['Not official native denominator or reachable gain',
                             'Partial EL direction mapping not guessed; separate HOLD',
                             'MDA not flattened or counted as binary directions',
                             'Unapplied constant candidates not subtracted'],
                EDA_started=False, RTL_changed=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = evidence()
    result['input_pins'][str(Path(__file__).resolve())] = t.digest(Path(__file__))
    for path, seal in result['input_pins'].items():
        assert t.digest(Path(path)) == seal, path
    with a.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(a.output, t.digest(a.output))
    for r in result['ranking'][:10]:
        print(r['exact_unexcluded_binary_missing'], r['scope'])
