"""Expand two reviewed scope filters only; static mapping, never native approval."""
import argparse
import ast
from collections import Counter
import inspect
import json
from pathlib import Path

import prove_qbs_hit_congruence780 as p

SOURCE_SHA = 'c16eab919154b3f96bd33321bd771e8b7de0398f223241ab751b9573d079721b'
PENDING = p.OUT / 'qbs-hit128-native780-bank0-p2-slot1-row0-agent-20261008-01/config.json'
PENDING_SHA = '7864c19fd3f06b06a148ae39f5c8ed97f7b15aef3c61cfeaa51db0b41d420ed5'


def expanded_function(source):
    """Keep source/pins/EL/shape/raw-counterexample checks literally unchanged."""
    tree = ast.parse(source)
    bank = ast.parse('bank != 0', mode='eval').body
    subset = ast.parse("not (name.startswith('gen_write_merge[1].gen_bank_plane[2].gen_bank_row[0].') and name.endswith('.hit'))", mode='eval').body
    changed = Counter()

    class Filters(ast.NodeTransformer):
        def visit_If(self, node):
            if ast.dump(node.test) == ast.dump(bank):
                p.m.require(len(node.body) == 1 and isinstance(node.body[0], ast.Continue)
                            and not node.orelse, 'Bank filter shape')
                node.test = ast.Constant(value=False)
                changed['bank'] += 1
            elif ast.dump(node.test) == ast.dump(subset):
                p.m.require(len(node.body) == 1 and isinstance(node.body[0], ast.Continue)
                            and not node.orelse, 'Signal filter shape')
                node.test = ast.parse("not name.endswith('.hit')", mode='eval').body
                changed['signal'] += 1
            return self.generic_visit(node)

    tree = Filters().visit(tree)
    p.m.require(changed == {'bank': 1, 'signal': 1}, 'Exactly two reviewed filters required')
    ast.fix_missing_locations(tree)
    ns = dict(vars(p))
    exec(compile(tree, '<all-hit-filter-only-successor>', 'exec'), ns)
    return ns['report']


def summarize(records, pending):
    counts, by_group, candidates, held_examples = Counter(), Counter(), [], {}
    for item in records:
        key, slot, side = p.m.identity(item['signal'], item['bit'])
        status = item['classification']
        if status == 'SOURCE_MAPPING_ZERO_NATIVE_REQUIRED':
            identity = item['scope'], item['signal'], item['bit']
            status = ('PENDING128_NOT_YET_QUALIFIED' if identity in pending
                      else 'NEW_MAPPING_ZERO_NATIVE_REQUIRED')
            candidates.append(dict(item, classification=status))
        else:
            group = (item['scope'], key[0], key[2], slot, side)
            held_examples.setdefault(str(group), item)
        count = len(item['raw_coordinates'])
        counts[status] += count
        by_group[str((item['scope'], key[0], key[2], slot, side, status))] += count
    return dict(residual_directions_by_class=dict(counts), by_scope_kind_plane_slot_side=dict(by_group),
                zero_candidates=candidates, mapping_HOLD_examples=list(held_examples.values()))


def report():
    p.m.require(p.m.digest(Path(p.__file__)) == SOURCE_SHA, 'Reviewed predecessor source drift')
    raw = expanded_function(inspect.getsource(p.report))()
    config = json.loads(PENDING.read_bytes())
    p.m.require(p.m.digest(PENDING) == PENDING_SHA and config['baseline'] == 780
                and config['population_application'] is False, 'Pending128 provenance')
    pending = {(i['scope'], s['name'], bit) for i in config['instances']
               for s in i['signals'] for bit in s['bits']}
    p.m.require(len(pending) == 64, 'Only pending64 bits')
    summary = summarize(raw['records'], pending)
    p.m.require(summary['residual_directions_by_class'].get('PENDING128_NOT_YET_QUALIFIED') == 128,
                'Frozen128 subset must be exact projection')
    pins = dict(raw['pins'])
    for path in (PENDING, Path(__file__).resolve(),
                 Path(__file__).with_name('test_classify_qbs_all_hits780.py')):
        pins[str(path)] = p.m.digest(path)
    return dict(schema='QBS_ALL_HIT_CONGRUENCE780_STATIC_V1', population=780, pins=pins,
        source_proof=raw['source_proof'], **summary,
        reviewed_domain='Both banks; all main and side hit objects; nine weight profiles ROW/R4; activation ROW/M4/M8; direct/fill/replay and pending masks.',
        authority='Absence in complete source-derived superset is candidate proof; presence is mapping only, NOT runtime arbitration or measured coverage.',
        pending128_applied=False, initial_X_excluded=False, native_qualification=False, no_EDA=True,
        retained='All observed hits, all selected/valid/BE/control/ports/MDA; no global EL emitted.',
        official_denominator=None)


if __name__ == '__main__':
    cli = argparse.ArgumentParser()
    cli.add_argument('--output', type=Path, required=True)
    a = cli.parse_args()
    result = report()
    with a.output.open('x') as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(dict(output=str(a.output), sha256=p.m.digest(a.output),
                         counts=result['residual_directions_by_class'])))
