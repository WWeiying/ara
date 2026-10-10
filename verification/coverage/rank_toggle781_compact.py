"""Reuse raw OR/typed inventory readers. Static capacity, never an official ratio."""
import argparse
from collections import defaultdict
import json
from pathlib import Path

import audit_remaining_toggle776 as old

t, OUT = old.t, old.OUT
BASE = OUT / 'akv-tile-range-admitted781-parent-20261008-01'
SHA = '720511a144576a95fee244a675635c96104b249c0f99ab3d6b8e0249de77f900'
POLICY = OUT / 'current-population781-plus9700-prepared-agent-20261008-01'


def collect():
    pins = {}
    def read(path, sha):
        t.require(t.digest(path) == sha, 'Bound input drift: ' + str(path))
        pins[str(path)] = sha
        return path.read_bytes()
    admission = json.loads(read(BASE/'admission-manifest.json', SHA))
    t.require(admission['coverage_admitted'] is True, 'Formal781 required')
    lp = BASE/'combined-inputs.txt'
    ledger = read(lp, admission['output_pins'][str(lp)]).decode().splitlines()
    t.require(len(ledger) == len(set(ledger)) == 782, 'Exact781 ledger')
    cache = json.loads(read(old.CACHE, old.CACHE_SHA))
    prefix = next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    t.require(ledger[:742] == read(prefix, cache['input_pins'][str(prefix)]).decode().splitlines(),
              'Exact sealed741 prefix')
    union = {s: {k: r[k] for k in ('width', 'checksum', 'bits')} for s, r in cache['instances'].items()}
    for vdb in ledger[742:]:
        paths = list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        t.require(len(paths) == 1, 'Exact single native suffix')
        read(paths[0], admission['input_pins'][str(paths[0])])
        rows, _ = t.rows(paths[0], set(union))
        union = t.union(union, rows)
    cp = POLICY/'config.json'
    config = json.loads(read(cp, t.digest(cp)))
    t.require(config['population'] == 781 and config['input_ledger'] == ledger, 'Exact prepared781 policy')
    ep = POLICY/'combined.el'
    el, whole = old.el_fields(read(ep, config['pins'][str(ep)]).decode())
    struct_owners = defaultdict(set)
    for scope, field in el:
        struct_owners[scope].add(field)
    db = Path(ledger[0])/'snps/coverage/db'
    files = [db/'design/verilog.design.xml', db/'shape/tgl.verilog.info.xml', db/'shape/tgl.verilog.shape.xml']
    for path in files: read(path, admission['input_pins'][str(path)])
    design, info, shape = (t.xml(path) for path in files)
    nodes = {n.get('id'): (n, m) for m in design.findall('srcdef') for n in m.findall('srcinst')}
    def scope_path(key):
        n, _ = nodes[key]
        return (scope_path(n.get('pid'))+'.' if n.get('pid') in nodes else '')+n.get('name')
    modules = {scope_path(key): m for key, (n, m) in nodes.items()}
    checks = {n.get('name'): n.get('chksum') for n in info.iter('instance_data')}
    definitions = defaultdict(list)
    for d in shape.findall('tgldef'):
        definitions[d.get('name').split(' (')[0], d.get('chksum')].append(d)
    groups, scopes, hold = {}, [], []
    for scope, row in union.items():
        if not (scope == 'ara_tb.dut.i_ara_soc.i_system' or scope.startswith('ara_tb.dut.i_ara_soc.i_system.')):
            continue
        if any(scope == s or scope.startswith(s+'.') for s in whole):
            continue
        module = modules[scope]
        t.require(row['checksum'] == checks[scope], 'Native/info checksum')
        family = module.get('name').split(' (')[0]
        matches = definitions[family, row['checksum']]
        exact = [d for d in matches if d.get('name') == module.get('name')]
        matches = exact or matches
        if len(matches) != 1:
            hold.append(dict(scope=scope, reason='AMBIGUOUS_TYPED_SHAPE', raw_width=row['width']))
            continue
        offset = 0; total = 0; partial = 0; fields = []
        binary = format(int(row['bits'], 16), '0%db' % row['width'])
        for node in matches[0].find('tglshape'):
            if node.tag == 'arrays':
                hold.append(dict(scope=scope, field=node.get('name'), reason='SRAM_OR_MDA_CAPACITY_UNBOUND',
                                 attributes=dict(node.attrib)))
                continue
            t.require(node.tag in ('node', 'vectornode'), 'Known serialized typed node')
            left, right = int(node.get('left', '0')), int(node.get('right', '0'))
            width = 1 if node.tag == 'node' else abs(left-right)+1
            missing = [offset+i for i, bit in enumerate(binary[offset:offset+2*width]) if bit == '0']
            offset += 2*width
            if not missing: continue
            name = node.get('name'); entries = el.get((scope, name), [])
            legal = set(range(min(left, right), max(left, right)+1))
            if any(bits == 'MDA_HOLD' for _, bits, _ in entries):
                hold.append(dict(scope=scope, field=name, reason='MDA_EL_OWNERSHIP_HOLD'))
                continue
            removed, ambiguous = old.excluded_bits(entries, legal)
            if removed == legal: continue
            if removed or ambiguous or any(name.startswith(n+'.') for n in struct_owners[scope]):
                partial += len(missing)
                hold.append(dict(scope=scope, field=name, reason='PARTIAL_OR_STRUCT_EL_NATIVE_BIT_MAP_REQUIRED',
                                 raw_missing_upper_bound=len(missing)))
                continue
            key = family, name
            group = groups.setdefault(key, dict(module_family=family, field=name, missing=0, members=[]))
            group['missing'] += len(missing)
            group['members'].append(dict(scope=scope, checksum=row['checksum'],
                module_checksum=module.get('chksum'), bounds=[left,right], kind=node.tag,
                compiled_attributes=dict(node.attrib), raw_missing=len(missing), coordinates=missing))
            total += len(missing)
            fields.append((name, len(missing)))
        t.require(offset == row['width'], 'Complete non-MDA serialized width')
        scopes.append(dict(scope=scope, module=family, unwaived_exact_field_missing=total,
            partial_EL_hold_upper_bound=partial, top_fields=sorted(fields,key=lambda x:-x[1])[:5]))
    ranked = sorted(groups.values(), key=lambda g:(-g['missing'],g['module_family'],g['field']))
    for path, sha in pins.items(): t.require(t.digest(path) == sha, 'Read-end drift')
    pins[str(Path(__file__).resolve())] = t.digest(__file__)
    return dict(schema='FORMAL781_COMPACT_NATIVE_RAW_OR_TYPED_CAPACITY_V1', population=781,
        policy='Prepared781+9700 exact EL subtraction; NOT final qualification or a percentage claim',
        top10=ranked[:10], scope_top10=sorted(scopes,key=lambda x:-x['unwaived_exact_field_missing'])[:10],
        bound_group_count=len(ranked), hold=hold, pins=pins,
        raw_native_scope_count=len(union), suffix_count=40, known741_cache_prefix=742,
        arrays_capacity=None, official_denominator=None, predicted_percentage_gain=None,
        serialization_pair_direction_order_not_inferred=True, EDA_started=False, waivers_applied=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    path = parser.parse_args().output.resolve()
    t.require(path.parent == OUT and not path.exists(), 'Fresh independent evidence')
    result = collect()
    with path.open('x') as stream: json.dump(result, stream, separators=(',', ':')); stream.write('\n')
    print(json.dumps(dict(output=str(path), sha256=t.digest(path),
        top10=[(g['module_family'],g['field'],g['missing']) for g in result['top10']],
        scope_top10=result['scope_top10'])), flush=True)
