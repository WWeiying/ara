"""Scoped VCS raw Toggle evidence. No direction inference or DVE percentages."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def rows(path, scopes):
    before = digest(path)
    result = {}
    with gzip.open(path, 'rb') as stream:
        for _, node in ET.iterparse(stream, events=('end',)):
            if node.tag == 'instance_data':
                name = node.get('name')
                if name in scopes:
                    value = node.get('value', '')
                    require(name not in result and value and not set(value) - {'0', '1'},
                            'Duplicate/empty/nonbinary targeted data')
                    require(node.get('chksum') is not None, 'Missing Toggle checksum')
                    result[name] = dict(width=len(value), checksum=node.get('chksum'),
                                        bits=hex(int(value, 2)))
                node.clear()
    require(set(result) == set(scopes), 'Missing targeted scope')
    require(digest(path) == before, 'Toggle data changed during read')
    return result, before


def union(left, right):
    require(set(left) == set(right), 'Scope universe differs')
    result = {}
    for scope, old in left.items():
        new = right[scope]
        require((old['width'], old['checksum']) == (new['width'], new['checksum']),
                'Toggle width/checksum differs')
        result[scope] = dict(old, bits=hex(int(old['bits'], 16) | int(new['bits'], 16)))
    return result


def gains(before, after):
    require(set(before) == set(after), 'Scope universe differs')
    result = {}
    for scope, old in before.items():
        new = after[scope]
        require((old['width'], old['checksum']) == (new['width'], new['checksum']),
                'Toggle width/checksum differs')
        a, b = int(old['bits'], 16), int(new['bits'], 16)
        require(not a & ~b, 'Previously hit Toggle position lost')
        require(b.bit_length() <= old['width'], 'Bitmap overflow')
        result[scope] = [i for i in range(old['width'])
                         if (b & ~a) >> (old['width'] - 1 - i) & 1]
    return result


def collect(config_path, config_sha, scopes):
    require(digest(config_path) == config_sha, 'Frozen raw740 config seal differs')
    config = json.loads(Path(config_path).read_bytes())
    require(config['schema'] == 'FINAL_RAW740_DVE_PREPARED_V1' and
            config['population'] == 740 and config['waiver_mode'] == 'off', 'Not raw740')
    ledger = config['input_ledger']
    require(len(ledger) == len(set(ledger)) == 741, 'Not exact740 population')
    require(scopes and len(scopes) == len(set(scopes)) and all(
        s.startswith('ara_tb.dut.i_ara_soc.i_system.') for s in scopes), 'Explicit product scopes required')
    pins = {str(Path(config_path).absolute()): config_sha}

    def bound(path):
        key = str(path)
        require(path.resolve(strict=True) == path and not path.is_symlink(), 'Aliased input')
        require(key in config['pins'], 'Unbound Toggle input: ' + key)
        require(digest(path) == config['pins'][key], 'Frozen input drift: ' + key)
        pins[key] = config['pins'][key]

    db = Path(ledger[0]) / 'snps/coverage/db'
    shape_path = db / 'shape/tgl.verilog.shape.xml'
    info_path = db / 'shape/tgl.verilog.info.xml'
    for path in (shape_path, info_path):
        bound(path)
    with gzip.open(info_path, 'rb') as stream:
        info = ET.parse(stream).getroot()
    checks = {}
    for node in info.iter('instance_data'):
        if node.get('name') in scopes:
            require(node.get('name') not in checks, 'Ambiguous Toggle info')
            checks[node.get('name')] = node.get('chksum')
    require(set(checks) == set(scopes), 'Missing compiled Toggle scope')
    with gzip.open(shape_path, 'rb') as stream:
        shape = ET.parse(stream).getroot()
    definitions = {}
    for scope in scopes:
        matches = [d for d in shape.findall('tgldef') if d.get('chksum') == checks[scope]
                   and any(i.get('name') == scope for i in d.iter('tglinst'))]
        require(len(matches) == 1, 'Ambiguous/missing exact Toggle definition: ' + scope)
        definitions[scope] = ET.tostring(matches[0], encoding='unicode')
    merged, selected = None, []
    for index, name in enumerate(ledger[1:], 1):
        vdb = Path(name)
        files = list((vdb / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files) == 1, 'Ambiguous test Toggle data')
        path = files[0]
        selected.append(str(vdb.with_suffix('') / path.parent.name))
        bound(path)
        sample, sha = rows(path, scopes)
        require(sha == pins[str(path)], 'Changed sealed Toggle input')
        require(all(sample[s]['checksum'] == checks[s] for s in scopes), 'Info/data mismatch')
        merged = sample if merged is None else union(merged, sample)
        if index % 100 == 0:
            print('Toggle targeted union %d/740' % index, flush=True)
    require(selected == config['selected_tests'] and len(set(selected)) == 740,
            'Selected native740 identities differ')
    for path, sha in pins.items():
        require(digest(path) == sha, 'Phase-end input drift: ' + path)
    return dict(schema='TARGETED_RAW740_TOGGLE_DIAGNOSTIC_V1', tests=ledger[1:],
                selected_tests=selected, metrics=merged, compiled_definitions=definitions,
                input_pins=pins, direction_binding_verified=False,
                coordinate_semantics='zero-based left-to-right serialized value positions',
                official_percentage=False, coverage_admitted=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--seal', required=True)
    parser.add_argument('--scope', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'Fresh output required')
    result = collect(args.config, args.seal, args.scope)
    with args.output.open('x') as stream:
        json.dump(result, stream, sort_keys=True)
        stream.write('\n')


if __name__ == '__main__':
    main()
