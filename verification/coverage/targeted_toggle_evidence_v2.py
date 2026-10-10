"""Exact design/info/shape Toggle binding when tgldef omits tglinst."""
import argparse
import gzip
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import targeted_toggle_evidence as base

digest, require, rows, union, gains = base.digest, base.require, base.rows, base.union, base.gains


def xml(path):
    data = path.read_bytes()
    return ET.fromstring(gzip.decompress(data) if data[:2] == b'\x1f\x8b' else data)


def definitions(design, info, shape, scopes):
    nodes = {}
    for module in design.findall('srcdef'):
        for node in module.findall('srcinst'):
            require(node.get('id') not in nodes, 'Duplicate compiled instance id')
            nodes[node.get('id')] = (node, module)

    def path(key, seen=()):
        require(key not in seen, 'Compiled hierarchy cycle')
        node, _ = nodes[key]
        parent = node.get('pid')
        return (path(parent, seen + (key,)) + '.' if parent in nodes else '') + node.get('name')

    hierarchy = {}
    for key, (_, module) in nodes.items():
        name = path(key)
        require(name not in hierarchy, 'Duplicate compiled path')
        hierarchy[name] = module
    checks = {}
    for node in info.iter('instance_data'):
        if node.get('name') in scopes:
            require(node.get('name') not in checks and node.get('chksum') is not None,
                    'Ambiguous/missing Toggle info checksum')
            checks[node.get('name')] = node.get('chksum')
    require(set(checks) == set(scopes), 'Missing compiled Toggle scope')
    result = {}
    for scope in scopes:
        require(scope in hierarchy, 'Unknown compiled instance')
        matches = [d for d in shape.findall('tgldef') if
                   d.get('chksum') == checks[scope] and d.get('name') == hierarchy[scope].get('name')]
        require(len(matches) == 1, 'Ambiguous/missing module+checksum Toggle definition')
        instances = list(matches[0].iter('tglinst'))
        require(not instances or any(i.get('name') == scope for i in instances),
                'Explicit Toggle instance list conflicts')
        result[scope] = dict(module=dict(hierarchy[scope].attrib),
                            shape=ET.tostring(matches[0], encoding='unicode'))
    return checks, result


def collect(config_path, seal, scopes):
    require(digest(config_path) == seal, 'Frozen raw740 config seal differs')
    c = json.loads(Path(config_path).read_bytes())
    require(c['schema'] == 'FINAL_RAW740_DVE_PREPARED_V1' and c['population'] == 740 and
            c['waiver_mode'] == 'off', 'Not raw740')
    ledger = c['input_ledger']
    require(len(ledger) == len(set(ledger)) == 741, 'Not exact740 population')
    require(scopes and len(scopes) == len(set(scopes)) and all(
        s.startswith('ara_tb.dut.i_ara_soc.i_system.') for s in scopes), 'Explicit product scopes required')
    pins = {str(Path(config_path).absolute()): seal}

    def bound(p):
        require(p.resolve(strict=True) == p and not p.is_symlink(), 'Aliased input')
        require(str(p) in c['pins'], 'Unbound Toggle input: ' + str(p))
        sha = c['pins'][str(p)]
        require(digest(p) == sha, 'Frozen input drift')
        pins[str(p)] = sha

    db = Path(ledger[0]) / 'snps/coverage/db'
    paths = [db / 'design/verilog.design.xml', db / 'shape/tgl.verilog.info.xml',
             db / 'shape/tgl.verilog.shape.xml']
    for p in paths:
        bound(p)
    checks, defs = definitions(*(xml(p) for p in paths), scopes)
    merged, selected = None, []
    for index, name in enumerate(ledger[1:], 1):
        vdb = Path(name)
        require(vdb.resolve(strict=True) == vdb, 'Aliased member VDB')
        files = list((vdb / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files) == 1, 'Ambiguous test Toggle data')
        p = files[0]
        bound(p)
        sample, sha = rows(p, scopes)
        require(sha == pins[str(p)] and all(sample[s]['checksum'] == checks[s] for s in scopes),
                'Info/data seal or checksum mismatch')
        merged = sample if merged is None else union(merged, sample)
        selected.append(str(vdb.with_suffix('') / p.parent.name))
        if index % 100 == 0:
            print('Toggle targeted union %d/740' % index, flush=True)
    require(selected == c['selected_tests'] and len(set(selected)) == 740, 'Native740 identity differs')
    for path, sha in pins.items():
        require(digest(path) == sha, 'Phase-end input drift')
    return dict(schema='TARGETED_RAW740_TOGGLE_DIAGNOSTIC_V2', tests=ledger[1:],
                selected_tests=selected, metrics=merged, compiled_definitions=defs, input_pins=pins,
                direction_binding_verified=False, official_percentage=False, coverage_admitted=False,
                coordinate_semantics='zero-based left-to-right serialized value positions')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--seal', required=True)
    p.add_argument('--scope', action='append', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    require(not a.output.exists(), 'Fresh output required')
    result = collect(a.config, a.seal, a.scope)
    with a.output.open('x') as stream:
        json.dump(result, stream, sort_keys=True)
        stream.write('\n')


if __name__ == '__main__':
    main()
