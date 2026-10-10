"""Successor candidate inventory including combinational execution leaves; no EDA."""
import argparse
import json
from pathlib import Path

import review_trusted_execution797 as previous
from inventory_operand_debug import Design


def collect():
    packet = previous.collect()
    a, native = previous.a, previous.native
    pins = packet['pins']
    path = a.ADMITTED / 'combined-toggle-bits.json'
    a.need(native.digest(path) == pins[str(path)], 'Frozen797 union')
    rows = json.loads(path.read_bytes())
    book = json.loads((a.BUILD / 'build-source-pins.json').read_bytes())
    db = a.BUILD / 'sim/simv.vdb'
    design = Design(db)
    ds = {}
    for d in native.xml(db / 'snps/coverage/db/shape/tgl.verilog.shape.xml').findall('tgldef'):
        ds.setdefault(d.get('chksum'), []).append(d)
    for scope, row in rows.items():
        definitions = ds.get(row['checksum'], [])
        if len(definitions) != 1:
            continue
        definition = definitions[0]
        family = definition.get('name', '').split(' (')[0]
        if family not in ('fpnew_classifier', 'fpnew_rounding', 'lzc'):
            continue
        if family == 'fpnew_rounding':
            a.need('EnableRSR=0' in definition.get('name', ''), 'Only deterministic rounding0')
        path = Path(design.source(scope)['resolved_path'])
        a.need(native.digest(path) == book[str(path)], 'Frozen compiled leaf source')
        pins[str(path)] = book[str(path)]
        packet['candidates'].append(dict(scope=scope, module=family, decision='RECOMMEND',
            reason='Independent combinational functional leaf; enclosing controls/interfaces remain covered.',
            source=str(path), source_sha256=book[str(path)],
            design_checksum=design.hierarchy[scope].get('chksum'), toggle_checksum=row['checksum'],
            compiled_definition=definition.attrib, native_qualified=False))
    for family in ('fpnew_classifier', 'fpnew_rounding', 'lzc'):
        packet['decisions'][family] = ['RECOMMEND', 'Independent combinational leaf; rounding restricted to EnableRSR0.']
        packet['instance_counts'][family] = sum(t['module'] == family for t in packet['candidates'])
    recommended = [t for t in packet['candidates'] if t['decision'] == 'RECOMMEND']
    roots = [t for t in recommended if not any(t['scope'].startswith(parent['scope'] + '.')
             for parent in recommended)]
    packet['minimal_recommended_roots'] = [t['scope'] for t in roots]
    packet['nested_recommended_leaves_already_owned'] = len(recommended) - len(roots)
    packet['recommended_instances'] = len(recommended)
    packet['minimal_roots_note'] = 'All-child ownership is intentional inside selected IP roots; do not duplicate nested classifier/rounding/lzc exclusions.'
    pins[str(Path(__file__).resolve())] = native.digest(Path(__file__).resolve())
    return packet


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    packet = collect()
    with args.output.open('x') as stream:
        stream.write(json.dumps(packet, indent=2) + '\n')
    print(json.dumps(dict(output=str(args.output), sha256=previous.native.digest(args.output),
        counts=packet['instance_counts'], recommended=packet['recommended_instances'],
        roots=len(packet['minimal_recommended_roots']))))
